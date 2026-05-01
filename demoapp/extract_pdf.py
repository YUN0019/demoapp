import os
import sys
import logging

# 設定 Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

try:
    import fitz  # PyMuPDF
except ImportError:
    logging.warning("未偵測到 fitz (PyMuPDF)。")

def extract_text_from_pdf(pdf_path, output_path):
    """
    從 PDF 擷取文字，若 PDF 不存在則嘗試讀取同名的 txt 備援檔。
    """
    if not os.path.exists(pdf_path):
        logging.warning(f"找不到目標 PDF: '{pdf_path}'")
        alt_txt = "PDF企畫書.txt"
        if os.path.exists(alt_txt):
            logging.info(f"發現備援文字檔 '{alt_txt}'，正在進行內容複製...")
            with open(alt_txt, "r", encoding="utf-8") as f_in, open(output_path, "w", encoding="utf-8") as f_out:
                f_out.write(f_in.read())
            return True
        return False

    try:
        logging.info(f"正在使用 PyMuPDF {fitz.__version__} 解析: {pdf_path}")
        doc = fitz.open(pdf_path)
        text = "\n".join([page.get_text() for page in doc])
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
        logging.info(f"成功擷取 {len(text)} 字元至 {output_path}")
        return True
    except Exception as e:
        logging.error(f"PDF 解析失敗: {e}")
        return False

if __name__ == "__main__":
    success = extract_text_from_pdf("防毒計劃書文件V2026.pdf", "pdf_content.txt")
    if not success:
        logging.error("規格書解析失敗，請確認檔案是否存在。")
        sys.exit(1)
