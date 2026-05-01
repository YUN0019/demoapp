import asyncio
import logging
import random
import os
import re
import urllib.parse
from datetime import datetime
from typing import List, Dict, Optional
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
_stealth = Stealth()
from urllib.parse import urlparse
import csv
import hashlib
import json

# 同時開啟的 Context 上限（搜尋 + 採集共用）
GLOBAL_CONTEXT_SEMAPHORE: Optional[asyncio.Semaphore] = None


def get_global_sem() -> asyncio.Semaphore:
    global GLOBAL_CONTEXT_SEMAPHORE
    if GLOBAL_CONTEXT_SEMAPHORE is None:
        GLOBAL_CONTEXT_SEMAPHORE = asyncio.Semaphore(12)
    return GLOBAL_CONTEXT_SEMAPHORE


class HeuristicAnalyzer:
    def __init__(self, config):
        self.config = config or {}
        self.weights = self.config.get("scoring_weights", {
            "core_keywords": 60,
            "supporting_keywords": 40,
            "blacklist_penalty": -500,
            "min_total_score": 75
        })
        self.keyword_groups = self.config.get("keyword_groups", {})
        self.entity_regex = {
            "Telegram": r"(?:t\.me/|@|telegram\.me/)([a-zA-Z0-9_]{5,32})",
            "BTC": r"[13][a-km-zA-HJ-NP-Z1-9]{25,34}|bc1[ac-hj-np-z02-9]{11,71}",
            "XMR": r"4[0-9AB][1-9A-HJ-NP-Za-km-z]{93}",
            "USDT_TRC20": r"T[A-Za-z1-9]{33}"
        }

    def analyze(self, text: str, html: str, url: str) -> Dict:
        score = 0
        matched_keywords = []
        text_lower = text.lower()
        html_lower = html.lower()

        for kw in self.keyword_groups.get("A_Product", []):
            if kw.lower() in text_lower:
                score += self.weights["core_keywords"]
                matched_keywords.append(kw)

        for kw in self.keyword_groups.get("C_Payment_Contact", []):
            if kw.lower() in text_lower:
                score += self.weights["supporting_keywords"]
                matched_keywords.append(kw)

        # V45.0: 使用精確的 X_Content_Blacklist，避免誤殺含 "research" 的合法商店
        for kw in self.keyword_groups.get("X_Content_Blacklist", []):
            if kw.lower() in text_lower:
                score += self.weights["blacklist_penalty"]

        # 彈性電商 / 地下商店邏輯
        has_cart = any(c in text_lower for c in ["add to cart", "proceed to checkout", "checkout", "shopping cart"])
        has_crypto = any(c in text_lower for c in ["monero", "bitcoin", "btc", "cryptocurrency", "xmr", "usdt"])
        has_private_contact = any(p in text_lower for p in ["telegram link", "signal me", "@plug", "wickr me", "join our channel"])

        if has_cart and has_crypto:
            score = max(score, 100)  # 有購物車 + 有幣種 → HIGH
        elif (has_crypto or has_private_contact) and score >= 60:
            score = max(score, 80)   # 展示型地下商店（無購物車但有加密 / 私密聯絡）

        if not has_cart and not has_private_contact:
            score = 0  # 既無購物車也無私密聯繫，視為新聞/百科/平台

        # 指紋提取
        fingerprints = []
        wp_plugins = re.findall(r"/wp-content/plugins/([a-zA-Z0-9\-_]+)/", html_lower)
        fingerprints.extend([f"/wp-content/plugins/{p}/" for p in set(wp_plugins)])
        if "woo-crypto" in html_lower:
            fingerprints.append("woo-crypto-gateway")

        # 實體提取（只掃純文字，防止 Base64 HTML 造成 CPU 耗盡與誤判）
        entities = {}
        for name, pattern in self.entity_regex.items():
            found = re.findall(pattern, text, re.IGNORECASE)
            if found:
                entities[name] = list(set(found))

        min_score = self.weights.get("min_total_score", 75)
        tier = "SKIP"
        if score >= 150:
            tier = "HIGH"
        elif score >= 100:
            tier = "MEDIUM"
        elif score >= min_score:
            tier = "NORMAL"

        return {
            "url": url, "score": score, "tier": tier,
            "matched": list(set(matched_keywords)),
            "fingerprints": fingerprints,
            "entities": entities
        }


class AntiDetectionCrawler:
    def __init__(self, headless=True, config=None):
        self.headless = headless
        self.config = config or {}
        self.analyzer = HeuristicAnalyzer(self.config)

        # V45.0: 使用 X_Domain_Blacklist，只在 URL 層過濾，不干涉內文計分
        self.blacklist = self.config.get("keyword_groups", {}).get("X_Domain_Blacklist", [])

        output_dirs = self.config.get("output_dirs", {})
        self.jpg_dir = output_dirs.get("test_jpg", "testjpg")
        self.html_dir = output_dirs.get("test_html", "testHTML")
        self.record_dir = output_dirs.get("record", "Record")
        
        os.makedirs(self.jpg_dir, exist_ok=True)
        os.makedirs(self.html_dir, exist_ok=True)
        os.makedirs(self.record_dir, exist_ok=True)

        self.hash_registry_path = os.path.join(self.record_dir, "seen_images.json")
        self.seen_hashes = self._load_hash_registry()

        self.url_registry_path = os.path.join(self.record_dir, "seen_urls.json")
        self.seen_urls = self._load_url_registry()

        self.manifest_path = os.path.join(self.jpg_dir, "data_manifest.csv")
        if not os.path.exists(self.manifest_path):
            with open(self.manifest_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Image_Name", "Class_Label", "Source_URL", "Timestamp"])

        self._pw_instance = None
        self._browser = None

    def _load_hash_registry(self) -> set:
        if os.path.exists(self.hash_registry_path):
            try:
                with open(self.hash_registry_path, "r", encoding="utf-8") as f:
                    return set(json.load(f))
            except:
                return set()
        return set()

    def _save_hash_registry(self):
        try:
            with open(self.hash_registry_path, "w", encoding="utf-8") as f:
                json.dump(list(self.seen_hashes), f, indent=2)
        except Exception as e:
            logging.error(f"Failed to save hash registry: {e}")

    def _load_url_registry(self) -> set:
        if os.path.exists(self.url_registry_path):
            try:
                with open(self.url_registry_path, "r", encoding="utf-8") as f:
                    return set(json.load(f))
            except:
                return set()
        return set()

    def _save_url_registry(self):
        try:
            with open(self.url_registry_path, "w", encoding="utf-8") as f:
                json.dump(list(self.seen_urls), f, indent=2)
        except Exception as e:
            logging.error(f"Failed to save URL registry: {e}")

    async def init(self):
        if self._pw_instance is None:
            self._pw_instance = await async_playwright().start()
            self._browser = await self._pw_instance.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"]
            )
            logging.info("V45.0 Browser Core Initialized.")

    def _setup_dialog_handler(self, page):
        """自動接受所有 JS Alert / Confirm / Prompt 對話框，防止爬蟲卡住"""
        page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.accept()))

    def _build_context_options(self) -> Dict:
        """建立 Context 設定，每次隨機挑選一個地理位置建立，增強偽裝"""
        import random
        locations = self.config.get("locations", [])
        if locations:
            loc = random.choice(locations)
            geo = {"latitude": loc["latitude"], "longitude": loc["longitude"], "accuracy": 100}
            timezone_id = loc.get("timezone", "America/New_York")
            locale = loc.get("locale", "en-US")
        else:
            geo = self.config.get("geolocation", {"latitude": 37.7749, "longitude": -122.4194, "accuracy": 100})
            timezone_id = self.config.get("timezone", "America/Los_Angeles")
            locale = self.config.get("locale", "en-US")

        opts: Dict = {
            "ignore_https_errors": True,
            "viewport": {"width": 1280, "height": 720},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "geolocation": geo,
            "permissions": ["geolocation"],
            "timezone_id": timezone_id,
            "locale": locale,
        }
        # Bug Fix: proxy=None 會讓 Playwright 報錯，必須在有值時才加入
        proxy_pool = self.config.get("proxy_pool", [])
        if proxy_pool:
            opts["proxy"] = random.choice(proxy_pool)
        return opts

    async def _simulate_human(self, page):
        """模擬真人行為：滑鼠抖動 + 分段捲動"""
        try:
            for _ in range(3):
                x, y = random.randint(100, 800), random.randint(100, 600)
                await page.mouse.move(x, y, steps=10)
                await asyncio.sleep(random.uniform(0.1, 0.3))
            await page.evaluate("""async () => {
                await new Promise((resolve) => {
                    let total = 0, dist = 400;
                    let t = setInterval(() => {
                        window.scrollBy(0, dist); total += dist;
                        if (total >= document.body.scrollHeight) { clearInterval(t); resolve(); }
                    }, 200);
                });
            }""")
            await asyncio.sleep(2)
            # 混回頂部再截圖，避免截到頁面最底的空白
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(0.8)
        except:
            pass

    async def _dismiss_all_overlays(self, page):
        """
        全自動彈窗清除系統 V45.0:
        1. Cookie 同意橫幅 (GDPR)
        2. 年齡驗證壁壘
        3. 廣告 / 電子報訂閱彈窗
        4. JS 重力清除 (強制移除遮罩)
        """
        # === 第一階段：點擊常見的同意 / 關閉按鈕 ===
        dismiss_keywords = [
            # Cookie 同意
            "Accept All", "Accept all cookies", "Accept Cookies",
            "Allow All", "Allow all cookies", "Allow Cookies",
            "I Accept", "I Agree", "Agree & Proceed",
            "Got it", "OK", "Okay", "Close",
            # 年齡驗證
            "I am 21", "I am 21+", "I am 18", "Yes, I am",
            "Enter Site", "Enter", "Confirm Age",
            # 廣告 / 電子報彈窗
            "No thanks", "No, thanks", "No Thank You",
            "Skip", "Dismiss", "Not now", "Maybe later",
            "Continue", "Continue to site",
        ]
        for kw in dismiss_keywords:
            try:
                # 同時匹配 button、a、div 標籤
                selector = f"button:has-text('{kw}'), a:has-text('{kw}'), [role='button']:has-text('{kw}')"
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=1500):
                    await btn.click()
                    logging.info(f"   [POPUP] 已自動點擊: '{kw}'")
                    await asyncio.sleep(1)
            except:
                continue

        # === 第二階段：嘗試按 ESC 關閉殘留彈窗 ===
        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
        except:
            pass

        # === 第三階段：JS 重力清除（強制移除遮罩層） ===
        try:
            await page.evaluate("""
                () => {
                    // 移除常見的 overlay / modal / cookie banner
                    const selectors = [
                        '[class*="cookie"]', '[class*="consent"]', '[class*="gdpr"]',
                        '[class*="overlay"]', '[class*="modal"]', '[class*="popup"]',
                        '[class*="banner"]', '[class*="age-gate"]', '[class*="age_gate"]',
                        '[id*="cookie"]', '[id*="consent"]', '[id*="overlay"]',
                        '[id*="modal"]', '[id*="popup"]', '[id*="age"]',
                        '.fc-dialog-container', '.qc-cmp2-container',
                        '#onetrust-banner-sdk', '#cookiebanner'
                    ];
                    selectors.forEach(sel => {
                        document.querySelectorAll(sel).forEach(el => el.remove());
                    });
                    // 解除 body 的 overflow:hidden（避免滾動被鎖死）
                    document.body.style.overflow = 'auto';
                    document.documentElement.style.overflow = 'auto';
                }
            """)
        except:
            pass

    async def _optimize_html(self, html: str) -> str:
        html = re.sub(r'<style.*?>.*?</style>', '', html, flags=re.DOTALL)
        html = re.sub(r'<link.*?rel="stylesheet".*?>', '', html)
        html = re.sub(r'<svg.*?>.*?</svg>', '[SVG_REMOVED]', html, flags=re.DOTALL)
        html = re.sub(r'data:image/.*?;base64,.*?"', '"[B64_REMOVED]"', html)
        return html

    async def _extract_product_images(self, page, domain: str, url: str):
        """
        產品圖片單獨擷取系統 V45.0 (方案 A: 精準屬性比對)
        - 挑選頁面上寬度≥ 200px 的 img 元素
        - 擷取圖片的 src 與 alt 特徵與毒品字典匹配，各自歸類
        - 取消了圖片上的文字浮水印，保持原圖乾淨
        """
        try:
            raw_img_data = await page.evaluate("""
                () => Array.from(document.querySelectorAll('img'))
                    .filter(img => img.naturalWidth >= 200 && img.naturalHeight >= 200)
                    .map(img => {
                        return {
                            src: img.src,
                            alt: (img.alt || img.title || "").toLowerCase()
                        };
                    })
                    .filter(item => item.src && item.src.startsWith('http'))
            """)

            if not raw_img_data:
                return

            # V46.0: URL 層次去重
            img_data_list = []
            seen_urls = set()
            for item in raw_img_data:
                if item['src'] not in seen_urls:
                    seen_urls.add(item['src'])
                    img_data_list.append(item)
            
            img_data_list = img_data_list[:12] # 最多 12 個

            if not img_data_list:
                return

            saved = 0
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            a_products = self.config.get("keyword_groups", {}).get("A_Product", [])

            for i, data in enumerate(img_data_list):
                img_url = data['src']
                img_alt = data['alt']
                
                # 比對圖片的 alt 或網址內是否含有毒品專有名詞
                img_label = "Unknown"
                search_text = (img_alt + " " + img_url).lower()
                for kw in a_products:
                    if kw.lower() in search_text:
                        img_label = kw
                        break
                        
                # 建立該毒品的安全資料夾
                safe_label = re.sub(r"[^\w\-]", "_", img_label)
                class_dir = os.path.join(self.jpg_dir, f"class_{safe_label}")
                os.makedirs(class_dir, exist_ok=True)

                try:
                    # 使用 Playwright 的 request API，帶著對象網站的 cookie 下載
                    response = await page.request.get(img_url, timeout=8000)
                    if response.ok:
                        img_binary = await response.body()
                        
                        # V46.0: 內容指紋比對 (MD5) 確保全域去重
                        img_hash = hashlib.md5(img_binary).hexdigest()
                        if img_hash in self.seen_hashes:
                            logging.debug(f"      [SKIP] 影像內容已存在 ({img_hash[:8]})")
                            continue
                        
                        content_type = response.headers.get("content-type", "")
                        ext = "jpg"
                        if "png" in content_type: ext = "png"
                        elif "gif" in content_type: ext = "gif"
                        elif "webp" in content_type: ext = "webp"
                        
                        img_filename = f"{domain}_{timestamp_str}_{i+1:02d}.{ext}"
                        img_path = os.path.join(class_dir, img_filename)
                        
                        with open(img_path, "wb") as f:
                            f.write(img_binary)
                            
                        # 紀錄指紋，防重複抓取
                        self.seen_hashes.add(img_hash)
                        self._save_hash_registry()
                            
                        # 寫入 CSV 索引
                        with open(self.manifest_path, "a", encoding="utf-8", newline="") as mf:
                            csv.writer(mf).writerow([img_filename, img_label, url, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                            
                        saved += 1
                except:
                    continue

            if saved > 0:
                logging.info(f"      [IMAGES] 擷取 {saved} 張產品圖並自動精確分類")
        except Exception as e:
            logging.debug(f"      [IMAGES] 擷取失敗: {e}")

    async def crawl(self, url: str, lightweight: bool = False, retry_count: int = 1) -> Dict:
        if not self._browser:
            await self.init()
        
        # 正規化網址：去除末端錨點 (#)
        normalized_url = url.split('#')[0]
        
        if any(black in normalized_url.lower() for black in self.blacklist):
            return {"url": normalized_url, "score": 0, "tier": "SKIP", "links": []}

        sem = get_global_sem()

        for attempt in range(retry_count + 1):
            context = None
            try:
                async with sem:
                    context = await self._browser.new_context(**self._build_context_options())
                    page = await context.new_page()

                    try:
                        await _stealth.apply_stealth_async(page)
                    except Exception as e:
                        logging.debug(f"   [STEALTH] 套用失敗（非致命）: {e}")

                    if lightweight:
                        await page.route("**/*.{png,jpg,jpeg,gif,svg,ico,webp,woff,woff2,ttf,eot,mp4,mov,avi,webm,css}", lambda route: route.abort())
                    else:
                        # 即使在完整模式，也封鎖影片和字體以節省流量（圖片保留給產品圖擷取）
                        await page.route("**/*.{woff,woff2,ttf,eot,mp4,mov,avi,webm}", lambda route: route.abort())

                    # 設定 JS 對話框自動接受
                    self._setup_dialog_handler(page)

                    logging.info(f"   Investigating ({'Light' if lightweight else 'Full'}) [Attempt {attempt+1}]: {url}")
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    await asyncio.sleep(2)

                    if not lightweight:
                        # 先清除所有彈窗，再模擬真人行為
                        await self._dismiss_all_overlays(page)
                        await self._simulate_human(page)

                    html_raw = await page.content()
                    text = await page.evaluate("document.body.innerText")
                    res = self.analyzer.analyze(text, html_raw, url)

                    if not lightweight and res["score"] >= 80:
                        domain = urlparse(url).netloc
                        # 截圖前混回頂部，確保擷到首屏的完整內容
                        await page.evaluate("window.scrollTo(0, 0)")
                        await asyncio.sleep(0.5)
                        # 全頁截圖（包含頁面所有內容，不是只截視窗圖）
                        await page.screenshot(
                            path=os.path.join(self.jpg_dir, f"{domain}.jpg"),
                            type="jpeg",
                            quality=75,
                            full_page=True
                        )
                        
                        # 單獨擷取產品圖片並且按照圖片內容精細歸類存檔 + CSV 索引紀錄
                        await self._extract_product_images(page, domain, url=normalized_url)
                        
                        # V46.0: URL 紀錄去重
                        if normalized_url not in self.seen_urls:
                            urls_txt_path = os.path.join(self.html_dir, "urls.txt")
                            with open(urls_txt_path, "a", encoding="utf-8") as f:
                                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                f.write(f"[{timestamp}] Score: {res['score']} | {normalized_url}\n")
                            
                            self.seen_urls.add(normalized_url)
                            self._save_url_registry()
                            logging.info(f"      [DATA SAVED] {domain} (Score: {res['score']})")
                        else:
                            logging.info(f"      [SKIP LOG] URL 已紀錄過: {normalized_url}")

                    # 深度爬取：限定在同網域內，防止爬蟲迷路引發 OOM
                    links = await page.evaluate("""() => {
                        return Array.from(document.querySelectorAll('a'))
                            .map(a => a.href)
                            .filter(h => h.startsWith('http') && h.includes(location.hostname));
                    }""")
                    res["links"] = list(set(links))[:15]
                    return res

            except Exception as e:
                logging.error(f"      [RETRY] 嘗試 {attempt + 1} 失敗 {url}: {e}")
                if attempt < retry_count:
                    continue  # Bug Fix: 不在這裡 close，統一在 finally 處理
                return {"url": url, "score": 0, "tier": "SKIP", "links": []}
            finally:
                # Bug Fix: 統一在 finally 關閉，避免 Double Close 報錯
                if context:
                    try:
                        await context.close()
                    except:
                        pass

    async def _search_single_engine(self, query: str, engine: dict) -> List[str]:
        """對單一引擎執行搜尋，受全域 Semaphore 限制"""
        sem = get_global_sem()
        context = None
        try:
            async with sem:
                context = await self._browser.new_context(**self._build_context_options())
                page = await context.new_page()
                try:
                    await _stealth.apply_stealth_async(page)
                except:
                    pass
                await page.route("**/*.{png,jpg,jpeg,gif,svg}", lambda route: route.abort())
                search_url = engine.get('url', '').format(urllib.parse.quote(query))
                logging.info(f"   -> [HARVESTER:{engine.get('name','?')}] 檢索: {query[:25]}...")
                await page.goto(search_url, timeout=30000)
                await asyncio.sleep(random.uniform(3, 5))
                hrefs = await page.evaluate("() => Array.from(document.querySelectorAll('a')).map(a => a.href)")
                return hrefs if hrefs else []
        except Exception as e:
            logging.warning(f"   -> [HARVESTER:{engine.get('name','?')}] 失敗: {str(e)[:60]}")
            return []
        finally:
            if context:
                try:
                    await context.close()
                except:
                    pass

    async def search_harvester(self, query: str, max_results: int) -> List[str]:
        """V45.0: 全引擎並發搜尋，合併去重"""
        if not self._browser:
            await self.init()
        engines = self.config.get("search_engines", [])

        tasks = [self._search_single_engine(query, engine) for engine in engines]
        results_per_engine = await asyncio.gather(*tasks, return_exceptions=True)

        all_hrefs = []
        for result in results_per_engine:
            if isinstance(result, list):
                all_hrefs.extend(result)

        noise_domains = [
            "google.", "bing.", "duckduckgo.", "swisscows.", "searx.", "startpage.",
            "mojeek.", "yandex.", "facebook.com", "linkedin.com", "instagram.com",
            "twitter.com", "tiktok.com", "github.com", "youtube.com"
        ]
        filtered = []
        for h in all_hrefs:
            if h and h.startswith('http') and not any(black in h.lower() for black in self.blacklist):
                if not any(noise in h.lower() for noise in noise_domains):
                    if not any(p in h.lower() for p in ["/privacy", "/settings", "/accounts", "/preferences", "/search?", "/login"]):
                        filtered.append(h)

        # Bug Fix: 使用引擎數量倍數作為上限，不丟棄有效結果
        per_engine_limit = max_results * len(engines)
        unique = list(set(filtered))[:per_engine_limit]
        logging.info(f"   -> [HARVESTER] 全引擎合併: {len(unique)} 個有效 URL（共 {len(engines)} 個引擎）")
        return unique

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._pw_instance:
            await self._pw_instance.stop()
