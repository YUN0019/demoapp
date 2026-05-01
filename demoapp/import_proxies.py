import json
import os

def format_proxy(line):
    # 格式: ip:port:user:pass
    parts = line.strip().split(':')
    if len(parts) == 4:
        ip, port, user, password = parts
        return f"http://{user}:{password}@{ip}:{port}"
    return None

def main():
    proxy_file = "Webshare 10 proxies.txt"
    config_file = "config.json"
    
    if not os.path.exists(proxy_file):
        print(f"找不到檔案: {proxy_file}")
        return

    with open(proxy_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    proxy_pool = []
    for line in lines:
        p = format_proxy(line)
        if p:
            proxy_pool.append({"server": p})
    
    if not proxy_pool:
        print("未在檔案中找到任何有效的代理伺服器格式。")
        return

    print(f"成功格式化 {len(proxy_pool)} 個代理伺服器。")

    # 讀取並更新 config.json
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"讀取 {config_file} 失敗: {e}")
        return

    config["proxy_pool"] = proxy_pool
    # 為了讓 proxy_test.py 也能用到，我們也補上單一 proxy 欄位（選第一個）
    if proxy_pool:
        config["proxy"] = proxy_pool[0]["server"]

    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    print(f"已成功更新 {config_file} 的 proxy_pool。")

if __name__ == "__main__":
    main()
