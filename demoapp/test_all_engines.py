import asyncio
import json
from playwright.async_api import async_playwright

async def test_engine(page, engine_name, url_template):
    print(f"   [TEST] 正在驗證引擎: {engine_name}...", end=" ", flush=True)
    try:
        test_query = "buy THC-A flower online"
        target_url = url_template.format(test_query)
        await page.goto(target_url, timeout=20000)
        await asyncio.sleep(3)
        
        content = await page.content()
        if "captcha" in content.lower() or "robot" in content.lower() or "verification" in content.lower():
            print("失敗 (遭封鎖/驗證碼)")
            return False
        
        # 簡單檢查是否有結果連結
        results = await page.query_selector_all("a")
        if len(results) > 10: # 正常頁面通常有很多連結
             print("成功 (可存取)")
             return True
        else:
             print("警告 (結果過少)")
             return False
    except Exception as e:
        print(f"出錯: {str(e)[:50]}")
        return False

async def main():
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)
    
    engines = config.get("search_engines", [])
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print("--- [DIAGNOSTIC] 正在測試各搜尋引擎是否可用 (不帶代理) ---")
        results = {}
        for engine in engines:
            name = engine["name"]
            url = engine["url"]
            results[name] = await test_engine(page, name, url)
        
        available = [name for name, ok in results.items() if ok]
        print(f"\n診斷結束。可用引擎: {available}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
