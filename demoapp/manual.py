import asyncio
import json
import os
import re
import random
import hashlib
import base64
from datetime import datetime
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# 從 crawler 引入現有的分析器，以保持標準一致
from crawler import HeuristicAnalyzer

_stealth = Stealth()

class ManualInvestigator:
    def __init__(self):
        # 讀取系統設定 (同 24H 引擎的標準)
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                self.config = json.load(f)
        except:
            self.config = {}
            
        self.analyzer = HeuristicAnalyzer(self.config)
        
        # 建立輸出的資料夾結構
        output_dirs = self.config.get("output_dirs", {})
        self.jpg_dir = output_dirs.get("test_jpg", "testjpg")
        self.html_dir = output_dirs.get("test_html", "testHTML")
        os.makedirs(self.jpg_dir, exist_ok=True)
        os.makedirs(self.html_dir, exist_ok=True)

    def _build_context_options(self):
        """建構高匿名的瀏覽器設定 (針對單次深度檢視最佳化)"""
        if self.config.get("locations"):
            loc = random.choice(self.config["locations"])
            geo = {"latitude": loc["latitude"], "longitude": loc["longitude"], "accuracy": 100}
            timezone_id = loc.get("timezone", "America/New_York")
            locale = loc.get("locale", "en-US")
        else:
            geo = {"latitude": 37.7749, "longitude": -122.4194, "accuracy": 100}
            timezone_id = "America/Los_Angeles"
            locale = "en-US"

        opts = {
            "ignore_https_errors": True,
            "viewport": {"width": 1920, "height": 1080}, # 手動檢測使用更大的視窗
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "geolocation": geo,
            "permissions": ["geolocation"],
            "timezone_id": timezone_id,
            "locale": locale,
        }
        
        proxy_pool = self.config.get("proxy_pool", [])
        if proxy_pool:
            p = random.choice(proxy_pool)
            opts["proxy"] = {"server": p} if isinstance(p, str) else p
            
        return opts

    async def _deep_simulate_human(self, page):
        """更深度的真人行為模擬，確保 Lazy Load 圖片完全載入"""
        try:
            # 隨機抖動
            for _ in range(4):
                x, y = random.randint(100, 1000), random.randint(100, 800)
                await page.mouse.move(x, y, steps=15)
                await asyncio.sleep(random.uniform(0.2, 0.4))
                
            # 慢慢捲動到底部，確保所有觸發載入的元素都被啟動
            await page.evaluate("""async () => {
                await new Promise((resolve) => {
                    let total = 0, dist = 250;
                    let t = setInterval(() => {
                        window.scrollBy(0, dist); total += dist;
                        if (total >= document.body.scrollHeight) { clearInterval(t); resolve(); }
                    }, 300);
                });
            }""")
            await asyncio.sleep(3)
            # 慢慢捲回中間，最後回頂部
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            await asyncio.sleep(1)
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1.5)
        except:
            pass

    async def _extract_images_for_ai(self, page, domain):
        """將產品圖抓下"""
        try:
            raw_img_data = await page.evaluate("""
                () => Array.from(document.querySelectorAll('img'))
                    .filter(img => img.naturalWidth >= 250 && img.naturalHeight >= 250)
                    .map(img => {
                        return {
                            src: img.src,
                            alt: (img.alt || img.title || "").toLowerCase()
                        };
                    })
                    .filter(item => item.src && item.src.startsWith('http'))
            """)
            
            if not raw_img_data:
                return 0

            # 去重
            seen_urls = set()
            img_list = []
            for item in raw_img_data:
                if item['src'] not in seen_urls:
                    seen_urls.add(item['src'])
                    img_list.append(item)
                    
            img_list = img_list[:15] # 擷取前 15 張大圖
            
            saved = 0
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_dir = os.path.join(self.jpg_dir, f"manual_{domain}")
            os.makedirs(target_dir, exist_ok=True)
            
            for i, data in enumerate(img_list):
                try:
                    response = await page.request.get(data['src'], timeout=8000)
                    if response.ok:
                        img_binary = await response.body()
                        content_type = response.headers.get("content-type", "")
                        ext = "jpg"
                        if "png" in content_type: ext = "png"
                        elif "webp" in content_type: ext = "webp"
                        
                        img_filename = f"{timestamp_str}_{i+1:02d}.{ext}"
                        img_path = os.path.join(target_dir, img_filename)
                        
                        with open(img_path, "wb") as f:
                            f.write(img_binary)
                        saved += 1
                except:
                    continue
                    
            return saved
        except Exception as e:
            print(f"提取圖片出錯: {e}")
            return 0

    async def process_query(self, url: str) -> dict:
        """主函式：接收外部 URL 請求，進行深度爬取並回傳乾淨的 JSON 報告。無資料庫牽涉。"""
        print(f"[MANUAL] 啟動純爬蟲深度調查 ({url})...")
        
        normalized_url = url.split('#')[0]
        domain = urlparse(normalized_url).netloc
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.config.get("headless", True),
                args=["--disable-blink-features=AutomationControlled"]
            )
            
            context = await browser.new_context(**self._build_context_options())
            page = await context.new_page()
            
            try:
                await _stealth.apply_stealth_async(page)
                
                # 自動同意所有的 JS 對話框
                page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.accept()))
                
                # 攔截影音，但放行圖片供後續分析
                await page.route("**/*.{woff,woff2,ttf,eot,mp4,mov,avi,webm}", lambda route: route.abort())
                
                await page.goto(normalized_url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(2)
                
                # 深度真人模擬與彈窗移除
                try:
                    await page.evaluate("""
                        () => {
                            const selectors = ['[class*="cookie"]', '[class*="consent"]', '[class*="modal"]', '[class*="popup"]', '#onetrust-banner-sdk'];
                            selectors.forEach(sel => document.querySelectorAll(sel).forEach(el => el.remove()));
                            document.body.style.overflow = 'auto';
                        }
                    """)
                except:
                    pass
                    
                await self._deep_simulate_human(page)
                
                # 文字特徵分析 (關聯性算分)
                html_raw = await page.content()
                text = await page.evaluate("document.body.innerText")
                score_res = self.analyzer.analyze(text, html_raw, normalized_url)
                
                # 儲存 HTML 供後評估
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                html_path = os.path.join(self.html_dir, f"manual_{domain}_{timestamp_str}.html")
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_raw)
                
                # 截取全畫面存檔
                jpg_path = os.path.join(self.jpg_dir, f"manual_{domain}_{timestamp_str}_full.jpg")
                await page.screenshot(path=jpg_path, type="jpeg", quality=80, full_page=True)
                
                # 電商圖片提取 (獨立抓取商品圖)
                jpg_count = await self._extract_images_for_ai(page, domain)
                
                # 將截圖與產品圖轉為 Base64 放入 JSON
                screenshot_b64 = ""
                if os.path.exists(jpg_path):
                    with open(jpg_path, "rb") as img_file:
                        screenshot_b64 = base64.b64encode(img_file.read()).decode('utf-8')
                        
                product_b64_list = []
                prod_dir = os.path.join(self.jpg_dir, f"manual_{domain}")
                if os.path.exists(prod_dir):
                    for pf in os.listdir(prod_dir):
                        if pf.endswith((".jpg", ".png", ".webp")):
                            with open(os.path.join(prod_dir, pf), "rb") as img_file:
                                product_b64_list.append({
                                    "filename": pf,
                                    "base64_data": base64.b64encode(img_file.read()).decode('utf-8')
                                })
                
                report = {
                    "composite_score": score_res["score"],
                    "threat_tier": score_res["tier"],
                    "crawler_data": {
                        "captured_images_count": jpg_count,
                        "page_title": await page.title(),
                        "extracted_keywords": score_res["matched"],
                        "hidden_entities": score_res["entities"]
                    },
                    "assets": {
                        "full_screenshot_path": jpg_path,
                        "raw_html_path": html_path,
                        "product_images_dir": prod_dir
                    },
                    "base64_images": {
                        "full_screenshot_base64": screenshot_b64,
                        "product_images_base64": product_b64_list
                    }
                }
                
                return report
                
            except Exception as e:
                err_msg = f"網站無法存取或連線超時: {str(e)[:100]}"
                return {
                    "composite_score": 0,
                    "threat_tier": "SKIP",
                    "crawler_data": {
                        "error_message": err_msg
                    }
                }
            finally:
                await context.close()
                await browser.close()

# 獨立測試腳本
if __name__ == "__main__":
    async def test():
        investigator = ManualInvestigator()
        
        print(">> 執行深度單點爬取測試:")
        res = await investigator.process_query("https://www.wikipedia.org/")
        
        # 移除過長的 Base64 數據以利終端機顯示測試結果
        if "base64_images" in res:
            res["base64_images"]["full_screenshot_base64"] = "<BASE64_DATA_HIDDEN>"
            for p in res["base64_images"]["product_images_base64"]:
                p["base64_data"] = "<BASE64_DATA_HIDDEN>"
                
        print("詳細結果:", json.dumps(res, indent=2, ensure_ascii=False))
        
    asyncio.run(test())
