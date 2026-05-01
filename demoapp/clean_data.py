import os
import shutil
import logging

# 設定 Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def cleanup_system():
    """
    一鍵清理系統：刪除所有爬取的數據與去重紀錄
    """
    targets = {
        "dirs": ["testjpg", "testHTML"],
        "files": ["visited_urls.txt", "monitor.log"]
    }
    
    print("\n⚠️  正在準備清理系統數據...")
    confirm = input("確定要刪除所有已爬取的圖片、網頁與去重紀錄嗎？(y/n): ")
    
    if confirm.lower() != 'y':
        print("❌ 清理已取消。\n")
        return

    # 清理資料夾
    for d in targets["dirs"]:
        if os.path.exists(d):
            # 刪除資料夾內的所有檔案，但保留資料夾本身
            for filename in os.listdir(d):
                file_path = os.path.join(d, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print(f"無法刪除 {file_path}: {e}")
            print(f"✅ 已清空資料夾: {d}")

    # 清除特定檔案
    for f in targets["files"]:
        if os.path.exists(f):
            try:
                os.remove(f)
                print(f"✅ 已刪除檔案: {f}")
            except Exception as e:
                print(f"無法刪除 {f}: {e}")

    print("\n✨ 系統已恢復至純淨狀態！現在你可以重新啟動 monitor_engine.py 開始新的採集。\n")

if __name__ == "__main__":
    cleanup_system()
