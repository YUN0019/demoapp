import asyncio
import logging
import json
import os
from crawler import AntiDetectionCrawler

# 設定 Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class DiscoveryEngine:
    """
    自動化發掘引擎：
    輸入關鍵字 -> 搜尋引擎 -> 連鎖爬取 -> 相關性評分 -> 產出名單
    """
    
    def __init__(self, keywords: list, max_depth: int = 2):
        self.keywords = keywords
        self.max_depth = max_depth
        self.crawler = AntiDetectionCrawler(headless=True)
        self.visited_urls = set()
        self.results = []

    def calculate_score(self, text: str):
        """
        簡易關鍵字相關性評分。未來可對接到 BERT 模型。
        """
        score = 0
        text_lower = text.lower()
        for kw in self.keywords:
            score += text_lower.count(kw.lower())
        return score

    async def run_discovery(self):
        """
        啟動全自動發掘流程。
        """
        query = " ".join(self.keywords)
        logging.info(f"💡 啟動發掘任務，關鍵字: {query}")
        
        # 1. 第一步：搜尋引擎發起
        initial_urls = await self.crawler.search_keywords(query, max_results=5)
        
        # 2. 第二步：遞迴爬取與鏈接發現 (BFS)
        queue = [(url, 0) for url in initial_urls] # (url, depth)
        
        while queue:
            url, depth = queue.pop(0)
            if url in self.visited_urls or depth > self.max_depth:
                continue
            
            self.visited_urls.add(url)
            logging.info(f"🔍 正在發掘第 {depth} 層: {url}")
            
            # 使用新版 crawler 執行爬取
            prefix = f"discover_{len(self.results)}"
            res = await self.crawler.crawl(url, prefix=prefix)
            
            if res.get("status") == "success":
                # 簡化邏輯：不讀取 metadata (因為已被移除)，直接紀錄成果
                score = self.calculate_score(url)
                
                self.results.append({
                    "url": url,
                    "depth": depth,
                    "relevance_score": score,
                    "html_path": res.get("html_path"),
                    "jpg_count": res.get("jpg_count")
                })
                
        logging.info(f"✅ 發掘完成，共發現 {len(self.results)} 個相關頁面")
        return self.results

if __name__ == "__main__":
    # 測試腳本：假設追蹤相關關鍵字
    test_keywords = ["毒品", "咖啡包", "冷酷"] # 範例關鍵字
    engine = DiscoveryEngine(keywords=test_keywords, max_depth=1)
    asyncio.run(engine.run_discovery())
