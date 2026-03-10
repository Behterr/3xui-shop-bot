@echo off
setlocal
cd /d "%~dp0"
start "XUI Bot" "%CD%\.venv\Scripts\python.exe" "%CD%\src\main.py"
start "XUI Admin" "%CD%\.venv\Scripts\python.exe" -m uvicorn src.admin_web:app --host 127.0.0.1 --port 8000
endlocal
