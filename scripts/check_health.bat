@echo off
chcp 65001 >nul
title kefuxitong 服务体检
cd /d "%~dp0\.."

set "PY=backend\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo.
"%PY%" scripts\check_health.py

echo.
pause
