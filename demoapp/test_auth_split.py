import asyncio
from playwright.async_api import async_playwright

async def test_single_proxy():
    # 測試第一個代理，拆分 auth
    proxy_info = {
        "server": "http://31.59.20.176:6754",
        "username": "xqxrqlqu",
        "password": "t37jpm1sb44c"
    }
    
    print(f"--- [TEST] 嘗試分離認證資訊測試: {proxy_info['server']} ---")
    
    async with async_playwright() as p:
        try:
            # 嘗試在 launch 或 context 中使用
            browser = await p.chromium.launch(headless=True, proxy=proxy_info)
            context = await browser.new_context()
            page = await context.new_page()
            
            print("正在訪問 ipinfo.io...")
            await page.goto("https://ipinfo.io/json", timeout=20000)
            content = await page.inner_text("body")
            print(f"成功連線！回傳內容: {content}")
            await browser.close()
            return True
        except Exception as e:
            print(f"失敗: {e}")
            return False

if __name__ == "__main__":
    asyncio.run(test_single_proxy())
