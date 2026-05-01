import asyncio
import json
import os
import sys
import random
from playwright.async_api import async_playwright

# 強制輸出為 UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# 讀取現有配置
def load_config():
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {
            "geolocation": {"latitude": 37.7749, "longitude": -122.4194},
            "locale": "en-US",
            "timezone": "America/Los_Angeles",
            "proxy": None
        }

async def run_health_check():
    config = load_config()
    geo = config.get("geolocation")
    locale = config.get("locale", "en-US")
    tz = config.get("timezone", "America/Los_Angeles")
    proxy_url = config.get("proxy")
    
    print(f"--- [DIAGNOSTIC] San Francisco Mode ---")
    if proxy_url:
        print(f"Detected Proxy in Config: {proxy_url}")
    else:
        print("No Primary Proxy detected. Testing direct connection (or Pool if configured).")

    async with async_playwright() as p:
        # 在 launch 時套用代理
        launch_args = {"headless": False}
        if proxy_url:
            launch_args["proxy"] = {"server": proxy_url}
        
        browser = await p.chromium.launch(**launch_args)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            locale=locale,
            timezone_id=tz,
            geolocation=geo,
            permissions=["geolocation"]
        )
        page = await context.new_page()
        
        try:
            # 1. IP 屬性檢查
            print("\n[STEP 1] Checking Egress IP via Proxy...")
            try:
                await page.goto("https://ipinfo.io/json", timeout=30000)
                content = await page.inner_text("body")
                ip_data = json.loads(content)
                
                print(f"Actual Egress IP: {ip_data.get('ip')}")
                print(f"Detected City: {ip_data.get('city')}")
                print(f"Detected Country: {ip_data.get('country')}")
                
                if ip_data.get('country') != 'US':
                    print(f"[CRITICAL] IP is NOT in US! (Found: {ip_data.get('country')})")
                else:
                    print(f"[SUCCESS] Proxy identity confirmed: US Location.")
            except Exception as e:
                print(f"[ERROR] IP Detection failed: {e}")

            # 2. 搜尋測試
            print("\n[STEP 2] Testing Search Engine Reachability...")
            test_query = "buy THC-A flower menu San Francisco"
            await page.goto(f"https://www.google.com/search?q={test_query}")
            await asyncio.sleep(5)
            
            if await page.query_selector("iframe[src*='captcha']") or "captcha" in page.url:
                print("[ERROR] BANNED: Still facing CAPTCHA. Proxy IP reputation might be low.")
            else:
                results = await page.query_selector_all("div.g")
                if len(results) > 0:
                    print(f"[SUCCESS] Received {len(results)} results via Proxy.")
                    title = await page.evaluate("document.querySelector('h3') ? document.querySelector('h3').innerText : 'No Title Found'")
                    print(f"Sample Result: {title}")
                else:
                    print("[WARNING] ZERO results. IP shadow-banned even via Proxy.")
                    
        except Exception as e:
            print(f"[ERROR] Diagnostic process failed: {e}")
        finally:
            print("\n--- Diagnostic End ---")
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run_health_check())
