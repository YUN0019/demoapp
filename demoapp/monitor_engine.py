import asyncio
import logging
import json
import os
import random
import sys
from datetime import datetime
from typing import List, Dict, Set
from crawler import AntiDetectionCrawler

# 配置日誌
os.makedirs("Record", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("Record/operation.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# V45.0: 自然語言範本池 (去機械化，模擬美國真實買家口吻，繞過 Shadow Ban)
NL_TEMPLATES = [
    "buy {product} online discreet shipping",
    "order {product} with {payment} no prescription",
    "{product} for sale accept {payment}",
    "where to buy {product} discreetly online",
    "best {product} online shop {payment}",
    "{product} anonymous shipping trusted vendor",
    "shop {product} fast delivery USA {payment}",
    "{product} quality trusted plug {payment}",
    "legit {product} ship anywhere {payment}",
    "stealth {product} worldwide delivery {payment}",
    "{product} vendor reviews {payment}",
    "cheap {product} real deal {payment}",
]

# V45.0: 已訪問 URL 記憶體上限，防止長時間運行 OOM
MAX_VISITED_URLS = 100_000


class DualTrackEngine:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.config = self._load_config()
        self.crawler = AntiDetectionCrawler(
            headless=self.config.get("headless", True),
            config=self.config
        )

        self.to_visit_queue = asyncio.Queue()
        self.visited_urls_path = "Record/visited_urls.txt"
        self.visited_urls = self._load_visited()
        self.learned_fingerprints = set()
        self.found_shops = []

        self.discovery_queue_path = "discovery_queue.txt"
        self.shop_file = "Record/Potential_Shops.txt"
        self.report_file = "Record/intel_report.json"

        self._seed_queue_from_file()

    def _load_config(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logging.error(f"Error loading config: {e}")
            return {}

    def _load_visited(self) -> Set[str]:
        """從檔案載入已訪問網址，只保留最後 MAX_VISITED_URLS 筆防止 OOM"""
        if os.path.exists(self.visited_urls_path):
            try:
                with open(self.visited_urls_path, "r", encoding="utf-8") as f:
                    lines = [line.strip() for line in f if line.strip()]
                    # V45.0: 只取最後 N 筆，防止爬很久後啟動時記憶體爆炸
                    return set(lines[-MAX_VISITED_URLS:])
            except Exception as e:
                logging.error(f"Error loading visited URLs: {e}")
                return set()
        return set()

    def _mark_visited(self, url: str):
        """標記並持久化網址，並限制記憶體集合大小"""
        if url not in self.visited_urls:
            # V45.0: 防止記憶體集合無限膨脹，超過上限後隨機淘汰 10%
            if len(self.visited_urls) >= MAX_VISITED_URLS:
                to_remove = random.sample(list(self.visited_urls), MAX_VISITED_URLS // 10)
                self.visited_urls -= set(to_remove)
                logging.debug(f"[MEMORY] visited_urls 清理 {len(to_remove)} 筆舊記錄，目前: {len(self.visited_urls)}")
            self.visited_urls.add(url)
            try:
                with open(self.visited_urls_path, "a", encoding="utf-8") as f:
                    f.write(f"{url}\n")
            except Exception as e:
                logging.error(f"Error saving visited URL {url}: {e}")

    def _seed_queue_from_file(self):
        if os.path.exists(self.discovery_queue_path):
            with open(self.discovery_queue_path, "r", encoding="utf-8") as f:
                for line in f:
                    u = line.strip()
                    if u and u not in self.visited_urls:
                        self.to_visit_queue.put_nowait(u)

    def _save_intel(self, res: Dict):
        self.found_shops.append(res)
        for fp in res.get("fingerprints", []):
            self.learned_fingerprints.add(fp)
        with open(self.report_file, "w", encoding="utf-8") as f:
            json.dump(self.found_shops, f, indent=2, ensure_ascii=False)

    def _gen_queries(self) -> List[str]:
        """V45.0: 合成去機械化自然語言搜尋句 + 技術 Dorks + 動態指紋組合"""
        products = self.config.get("keyword_groups", {}).get("A_Product", [])
        payments = self.config.get("keyword_groups", {}).get("C_Payment_Contact", [])
        dorks = self.config.get("keyword_groups", {}).get("E_Advanced_Dorks", [])

        queries = list(dorks)

        # 自然語言範本生成（模擬真人搜尋，繞過搜尋引擎機器人偵測）
        product_samples = random.sample(products, min(8, len(products)))
        payment_samples = random.sample(payments, min(5, len(payments)))
        for product in product_samples:
            template = random.choice(NL_TEMPLATES)
            payment = random.choice(payment_samples)
            q = template.format(product=product, payment=payment)
            queries.append(q)

        # 動態指紋組合（基於已發現的 WordPress/WooCommerce 技術特徵）
        if self.learned_fingerprints:
            for fp in random.sample(list(self.learned_fingerprints), min(len(self.learned_fingerprints), 3)):
                queries.append(f'inurl:"{fp}" "{random.choice(products)}"')

        return queries

    async def harvester_track(self):
        max_workers = self.config.get("max_workers", 5)
        logging.info("[TRACK A] Harvester 啟動：執行多語義智能搜尋...")
        try:
            while True:
                try:
                    queries = self._gen_queries()
                    if not queries:
                        await asyncio.sleep(60)
                        continue
                    q = random.choice(queries)
                    found = await self.crawler.search_harvester(q, max_results=10)
                    for u in found:
                        if u not in self.visited_urls:
                            await self.to_visit_queue.put(u)
                            self._mark_visited(u)
                    logging.info(f"[TRACK A] 搜尋完成。當前隊列長度: {self.to_visit_queue.qsize()}")
                    # V46.0: 使用動態間隔設定，避免單一 IP 遭封鎖
                    interval = self.config.get("search_interval_seconds", 300)
                    # 加入 10% 的隨機抖動，避免機械化規律
                    jitter = random.uniform(0.9, 1.1)
                    await asyncio.sleep(interval * jitter)
                except Exception as e:
                    logging.error(f"[TRACK A] 循環錯誤: {e}")
                    await asyncio.sleep(60)
        finally:
            logging.info("[TRACK A] Harvester 停止，正在發送毒丸...")
            # 向每一個 Worker 發送毒丸讓它們正常退出
            for _ in range(max_workers):
                await self.to_visit_queue.put(None)

    async def investigator_track(self):
        # V45.0: 從 config 動態讀取 Worker 數量，對齊 Proxy Pool 規模（預設 8）
        max_workers = self.config.get("max_workers", 5)
        logging.info(f"[TRACK B] Investigator 啟動：執行 {max_workers} 軌非同步採集...")
        investigate_sem = asyncio.Semaphore(max_workers)

        async def work(worker_id):
            while True:
                url = await self.to_visit_queue.get()
                if url is None:
                    logging.info(f"   [Worker {worker_id}] 接收毒丸，完成任務。")
                    self.to_visit_queue.task_done()
                    break

                async with investigate_sem:
                    try:
                        res = await self.crawler.crawl(url, lightweight=False)
                        if res and res.get("tier") != "SKIP":
                            self._save_intel(res)
                            for link in res.get("links", []):
                                if link not in self.visited_urls:
                                    if not any(se in link.lower() for se in ["google.", "bing.", "duckduckgo."]):
                                        await self.to_visit_queue.put(link)
                                        self._mark_visited(link)
                    except Exception as e:
                        logging.error(f"[TRACK B] 處理失敗 {url}: {e}")
                    finally:
                        self.to_visit_queue.task_done()

        workers = [asyncio.create_task(work(i)) for i in range(max_workers)]
        await asyncio.gather(*workers)

    async def run(self):
        try:
            await self.crawler.init()
            max_workers = self.config.get("max_workers", 5)
            logging.info(f"V45.0 Fully Optimized Dual-Track Predator Engine Active. Workers: {max_workers}")
            await asyncio.gather(
                self.harvester_track(),
                self.investigator_track()
            )
        except asyncio.CancelledError:
            logging.info("Shutting down workers...")
        finally:
            await self.crawler.close()
            logging.info("Crawler resources released.")


async def main():
    engine = DualTrackEngine()
    try:
        await engine.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Mission Aborted. All processes terminated.")
