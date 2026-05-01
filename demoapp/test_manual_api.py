import requests
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')

def test_api():
    url = "http://127.0.0.1:8000/api/crawl"
    
    # 這是 Backend 將會傳給您的格式
    payload = {
        "url": "https://www.wikipedia.org/"
    }
    
    print(f"正在發送測試請求至 Crawler API ({url})...")
    print("目標網址:", payload["url"])
    print("-" * 50)
    
    try:
        # 模擬 Backend 發送 POST 請求給您的 API
        response = requests.post(url, json=payload, timeout=90)
        
        if response.status_code == 200:
            print("✅ 收到成功回傳！")
            result = response.json()
            
            # 因為 Base64 圖片資料字串極長，我們把圖片資料遮蔽掉以方便在終端查看結構
            if "data" in result and "base64_images" in result["data"]:
                result["data"]["base64_images"]["full_screenshot_base64"] = "<超長字串_已隱藏>"
                for prod in result["data"]["base64_images"].get("product_images_base64", []):
                    prod["base64_data"] = "<超長字串_已隱藏>"
                    
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"❌ 發生錯誤 (Status {response.status_code}):")
            print(response.text)
            
    except Exception as e:
        print(f"無法連線到 Crawler API。請確認是否已啟動 FastAPI 伺服器？\n ({e})")

if __name__ == "__main__":
    test_api()
