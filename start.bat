@echo off
:: ─────────────────────────────────────────────
::   AI Arena — Windows Launcher
:: ─────────────────────────────────────────────
title AI Arena

cd /d "%~dp0backend"

:: Create .env if missing
if not exist .env (
    copy .env.example .env
    echo.
    echo   Created backend\.env from .env.example
    echo   Add your OpenRouter key to backend\.env
    echo   OR use the in-app Settings panel after launch.
    echo.
)

:: Install dependencies
echo Installing Python dependencies...
pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo.
    echo   ERROR: pip install failed.
    echo   Make sure Python is installed: https://python.org/downloads
    echo   Check "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo.
echo   ==========================================
echo    AI Arena - OpenRouter Edition
echo   ==========================================
echo    App:      http://localhost:3001
echo    API docs: http://localhost:3001/docs
echo    Press Ctrl+C to stop
echo   ==========================================
echo.

python main.py
pause
