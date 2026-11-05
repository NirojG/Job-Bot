@echo off
title Niroj JobFlow - Live scraper
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo See README.md to set up Niroj JobFlow.
    pause
    exit /b 1
)
"venv\Scripts\python.exe" -X utf8 -u dashboard.py %*
if errorlevel 1 pause
