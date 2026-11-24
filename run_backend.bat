@echo off
title Video AI - Core & Automation Backend (Port 8001)
chcp 65001 >nul
echo =====================================================================
echo    KHOI DONG BACKEND CORE: AUTOMATION, CRAWL, PUBLISH & ADMIN
echo                         Cổng (Port): 8001
echo =====================================================================
echo.
cd /d "%~dp0"
python -m uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
pause
