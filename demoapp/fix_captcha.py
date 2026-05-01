import asyncio
from playwright.async_api import async_playwright

async def fix_captcha():
    """
    手動驗證應急工具
    當發現搜尋引擎一直沒結果時，執行此腳本，
    在跳出的瀏覽器視窗中手動點選「我不是機器人」。
    """
    print("="*50)
    print("🚀 啟動手動驗證應急工具 (Captcha Fixer)")
    print("說明：請在跳出的瀏覽器視窗中完成 Google/Bing 的人機驗證。")
    print("完成後，請回到這裡按 Enter 鍵關閉瀏覽器。")
    print("="*50)
    
    async with async_playwright() as p:
        # 使用有介面模式 (headless=False)
        browser = await p.firefox.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        # 依序開啟可能被擋的搜尋引擎
        targets = [
            "https://www.google.com/search?q=test",
            "https://www.bing.com/search?q=test",
            "https://html.duckduckgo.com/html/?q=test"
        ]
        
        for url in targets:
            print(f"正在導航至: {url}")
            await page.goto(url)
            print(f"請檢查 {url} 是否需要驗證...")
            await asyncio.sleep(2) # 留一點時間加載
            
        input("\n✅ [請在瀏覽器中操作完畢後] 按下 Enter 鍵結束並重啟自動監控...")
        await browser.close()
        print("應急工具已關閉。現在你可以重新啟動 monitor_engine.py 了。")

if __name__ == "__main__":
    asyncio.run(fix_captcha())
