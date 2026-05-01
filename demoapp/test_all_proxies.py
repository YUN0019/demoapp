import asyncio
import json
import os
from playwright.async_api import async_playwright

async def test_proxy(proxy_str):
    parts = proxy_str.strip().split(':')
    if len(parts) != 4:
        return False, "無效格式"
    
    ip, port, user, password = parts
    proxy_info = {
        "server": f"http://{ip}:{port}",
        "username": user,
        "password": password
    }
    
    async with async_playwright() as p:
        try:
            print(f"   [TEST] 正在驗證: {ip}:{port}...", end=" ", flush=True)
            browser = await p.chromium.launch(headless=True, proxy=proxy_info)
            context = await browser.new_context()
            page = await context.new_page()
            res = await page.goto("http://purl.org/", timeout=10000)
            await browser.close()
            if res and res.status < 400:
                print("通過")
                return True, "OK"
        except Exception as e:
            pass
        print("失敗")
        return False, "Fail"

async def main():
    proxy_file = "Webshare 10 proxies.txt"
    if not os.path.exists(proxy_file):
        print(f"Missing {proxy_file}")
        return

    with open(proxy_file, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]
    
    print(f"--- [DIAGNOSTIC] 正在逐一驗證 Webshare 10 個代理 ---")
    valid_proxies = []
    for line in lines:
        is_valid, msg = await test_proxy(line)
        if is_valid:
            valid_proxies.append(line)
    
    print(f"\n驗證結束。可用數量: {len(valid_proxies)} / {len(lines)}")
    if valid_proxies:
        print("可用以下代理:")
        for v in valid_proxies:
            print(f" - {v}")
    else:
        print("遺憾：所有輸入的 Webshare 代理目前皆無法使用。")

if __name__ == "__main__":
    asyncio.run(main())
