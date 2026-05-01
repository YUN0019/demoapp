@echo off
echo 🚀 正在啟動環境自動安裝程序...
echo -----------------------------------

echo [1/3] 正在安裝 Python 依賴套件...
pip install -r requirements.txt

echo.
echo [2/3] 正在安裝 Playwright 瀏覽器核心...
playwright install chromium

echo.
echo [3/3] 正在安裝 Playwright 系統相依庫 (Linux/Server 適用)...
playwright install-deps

echo -----------------------------------
echo ✅ 環境安裝完成！現在你可以安心執行 monitor_engine.py 了。
echo 紅色底線應該也會在 VS Code 重新索引後消失。
pause
