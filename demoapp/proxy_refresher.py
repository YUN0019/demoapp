import asyncio
import json
import os
import sys
import re
from playwright.async_api import async_playwright

# 強制輸出為 UTF-8
if sys.stdout.encoding != 'utf-8' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

async def check_proxy_validity(proxy_url):
    """測試代理是否真的能用 (訪問 Google)"""
    async with async_playwright() as p:
        try:
            print(f"   [TEST] 正在驗證: {proxy_url}...", end=" ", flush=True)
            browser = await p.chromium.launch(headless=True, proxy={"server": proxy_url})
            context = await browser.new_context()
            page = await context.new_page()
            # 測試訪問一個輕量站點
            res = await page.goto("http://purl.org/", timeout=10000)
            await browser.close()
            if res and res.status < 400:
                print("通過")
                return True
        except:
            pass
        print("失敗")
        return False

async def fetch_us_proxies_with_playwright():
    print("--- [REFRESH] 正在獲獲美國專用 (US Only) 代理 ---")
    sources = [
        "https://www.us-proxy.org/",
        "https://www.socks-proxy.net/"
    ]
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        all_raw_proxies = []
        for url in sources:
            try:
                print(f"正在掃描來源: {url}...")
                await page.goto(url, timeout=60000)
                
                is_socks = "socks" in url
                
                raw_proxies = await page.evaluate(f"""() => {{
                    const tables = Array.from(document.querySelectorAll('table'));
                    const proxyTable = tables.find(t => t.innerText.includes('IP Address'));
                    if (!proxyTable) return [];
                    
                    const rows = Array.from(proxyTable.querySelectorAll('tbody tr'));
                    return rows
                        .map(row => {{
                            const cells = row.querySelectorAll('td');
                            if (cells.length < 2) return null;
                            const ip = cells[0].innerText.trim();
                            const port = cells[1].innerText.trim();
                            if (/^\\d+\\.\\d+\\.\\d+\\.\\d+$/.test(ip)) {{
                                return `{'socks5' if is_socks else 'http'}://${{ip}}:${{port}}`;
                            }}
                            return null;
                        }})
                        .filter(p => p !== null);
                }}""")
                all_raw_proxies.extend(raw_proxies)
            except Exception as e:
                print(f"抓取 {url} 失敗: {e}")

        valid_proxies = []
        # 去重
        unique_proxies = list(dict.fromkeys(all_raw_proxies))
        print(f"共發現 {len(unique_proxies)} 個潛在代理，開始驗證...")
        
        for p_url in unique_proxies[:30]: # 擴大驗證範圍
            if await check_proxy_validity(p_url):
                valid_proxies.append(p_url)
                if len(valid_proxies) >= 10: break # 需要 10 個

        print(f"最終獲得 {len(valid_proxies)} 個已驗證可用的美國代理。")
        return valid_proxies

def update_config(new_proxies):
    config_path = "config.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        # [V28] 如果沒抓到新的，保留舊的 (或清空讓它走直連)
        if new_proxies:
            config["proxy_pool"] = new_proxies
            print(f"已更新 {len(new_proxies)} 個可用 IP。")
        else:
            print("警告：未抓到任何可用代理，系統將進入「直連模式」。")
            config["proxy_pool"] = []
            
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"更新失敗: {e}")

async def main():
    proxies = await fetch_us_proxies_with_playwright()
    update_config(proxies)

if __name__ == "__main__":
    asyncio.run(main())
