@echo off
chcp 65001 >nul
echo ========================================
echo   kefuxitong - Start Backend ^& Frontend
echo ========================================
echo.
echo [1/2] Starting backend  http://localhost:8000 ...
start "kefuxitong-backend" cmd /k "cd /d %~dp0\..\backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo [2/2] Starting frontend http://localhost:5173 ...
start "kefuxitong-frontend" cmd /k "cd /d %~dp0\..\frontend && npm run dev"

echo.
echo ----------------------------------------
echo  Backend API :  http://localhost:8000
echo  API Docs    :  http://localhost:8000/docs
echo  Frontend    :  http://localhost:5173
echo ----------------------------------------
echo  Default admin: admin / admin123
echo ----------------------------------------
echo.
echo Close this window will NOT stop the servers.
echo To stop, close the backend ^& frontend windows.
echo.
pause
