import asyncio
from playwright.async_api import async_playwright
import os

async def manual_verify():
    user_data_dir = os.path.abspath("User_Profile")
    print(f"[*] 啟動手動驗證模式...")
    print(f"[*] 設定檔路徑: {user_data_dir}")
    print("[!] 請在開啟的瀏覽器中執行以下操作：")
    print("    1. 解決 Google/Bing 的機器人驗證 (如有)")
    print("    2. 點擊進入 Weedmaps 或 Leafly 並完成年齡驗證")
    print("    3. 登入您認為必要的任何帳號")
    print("\n[!] 完成後請直接關閉瀏覽器視窗，本程式會自動結束。")
    
    import json, random
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)
    proxy_pool = config.get("proxy_pool", [])
    proxy = random.choice(proxy_pool) if proxy_pool else None

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            args=["--disable-blink-features=AutomationControlled"],
            geolocation={"latitude": 37.7749, "longitude": -122.4194, "accuracy": 100},
            permissions=["geolocation"],
            timezone_id="America/Los_Angeles",
            locale="en-US",
            proxy=proxy
        )
        page = await context.new_page()
        await page.goto("https://www.google.com")
        
        # 等待使用者手動操作直至視窗關閉
        print("[*] 瀏覽器已開啟，等待手動操作中...")
        while True:
            await asyncio.sleep(5)
            if not context.pages: break
            
    print("[+] 驗證完成！Persistent Context 已更新。")

if __name__ == "__main__":
    try:
        asyncio.run(manual_verify())
    except KeyboardInterrupt:
        print("\n[!] 已手動中止。")
