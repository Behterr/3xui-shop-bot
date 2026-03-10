@echo off
setlocal
for /f "tokens=2 delims==" %%p in ('wmic process where "name='python.exe'" get ProcessId /value ^| find "="') do (
  for /f "delims=" %%c in ('wmic process where "ProcessId=%%p" get CommandLine /value ^| find "="') do (
    echo %%c | find /I "src\main.py" >nul
    if not errorlevel 1 taskkill /PID %%p /F >nul
    echo %%c | find /I "uvicorn" >nul
    if not errorlevel 1 taskkill /PID %%p /F >nul
  )
)
endlocal
