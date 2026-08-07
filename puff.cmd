@echo off
REM DEEPSEEK_API_KEY 请在环境变量中设置，不要硬编码在此文件
set "DEEPSEEK_BASE_URL=https://api.deepseek.com"
set "PUFF_MODEL=deepseek-v4-flash"
set "MEMORY_HUB_URL=http://127.0.0.1:8921"
cd /d "%~dp0"

if "%1"=="serve" (
    echo [Puff] Starting server...
    for /f "tokens=*" %%p in ('where python') do set "PUFF_PYTHON=%%p"
    if defined PUFF_PYTHON (start "Puff Server" %PUFF_PYTHON% puff.py serve 8920) else (echo Python not found && pause && exit /b 1)
    timeout /t 2 /nobreak >nul
    start msedge --app="http://127.0.0.1:8920" --window-size=900,700
    echo [Puff] Ready.
) else (
    python puff.py %*
)
