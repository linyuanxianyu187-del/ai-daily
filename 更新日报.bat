@echo off
cd /d "D:\AI\AI日报"
C:\"Program Files"\Python310\python.exe generate_daily.py
echo.
echo ✅ 更新完成！正在打开日报...
start "" "D:\AI\AI日报\index.html"
