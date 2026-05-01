import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_crawl(url, prefix):
    print(f"\n--- 測試爬取: {url} ---")
    payload = {
        "url": url,
        "output_prefix": prefix
    }
    try:
        response = requests.post(f"{BASE_URL}/api/crawl", json=payload)
        print(f"狀態碼: {response.status_code}")
        res_data = response.json()
        print(f"訊息: {res_data.get('msg')}")
        if response.status_code == 200:
            print(f"HTML 路徑: {res_data.get('details', {}).get('html_path')}")
            print(f"JPG 數量: {res_data.get('details', {}).get('captured_jpgs')}")
    except Exception as e:
        print(f"測試發生錯誤: {e}")

if __name__ == "__main__":
    # 測試正常網址
    test_crawl("https://www.wikipedia.org/", "api_test_wiki")
    
    # 測試白名單 (台大)
    test_crawl("https://www.ntu.edu.tw", "api_test_edu")
