import os
import json
import logging

# 設定 Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class AIBridge:
    """
    AI 橋接層：負責根據爬蟲抓取的 Metadata 準備 AI 模型所需的輸入。
    預留介面供未來 YOLO (影像) 與 BERT (語意) 整合。
    """
    
    def __init__(self):
        self.jpg_dir = "testjpg"
        self.html_dir = "testHTML"

    def list_pending_images(self, prefix):
        """列出指定任務中所有待分析的圖片檔案 (YOLO 預用)。"""
        if not os.path.exists(self.jpg_dir):
            return []
        return [os.path.join(self.jpg_dir, f) for f in os.listdir(self.jpg_dir) 
                if f.startswith(prefix) and f.endswith('.jpg')]

    def list_pending_html(self, prefix):
        """列出指定任務中的網頁數據 (BERT/LLM 預用)。"""
        if not os.path.exists(self.html_dir):
            return []
        return [os.path.join(self.html_dir, f) for f in os.listdir(self.html_dir) 
                if f.startswith(prefix) and f.endswith('.html')]

    async def run_yolo_inference_stub(self, image_paths):
        """
        YOLO 識別預留介面。
        """
        logging.info(f"YOLO 預留介面呼叫：準備分析 {len(image_paths)} 張圖片...")
        # TODO: 整合訓練好的 .pt 模型
        return {"status": "placeholder", "detected_objects": []}

    async def run_bert_analysis_stub(self, text):
        """
        BERT 語意分析預留介面。
        """
        logging.info("BERT 預留介面呼叫：準備進行敏感詞語意分析...")
        # TODO: 整合 BERT 模型進行分類
        return {"status": "placeholder", "is_suspicious": False}

if __name__ == "__main__":
    # 測試腳本
    bridge = AIBridge()
    images = bridge.list_pending_images("ig_automated")
    print(f"待分析圖片數量: {len(images)}")
