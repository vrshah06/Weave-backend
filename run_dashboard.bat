@echo off
echo ==================================================
echo STARTING WEAVE AUTOMATION DASHBOARD
echo ==================================================

start "Weave Backend (Port 5000)" cmd /k "cd backend && npm start"
start "Weave Frontend Dashboard (Port 3000)" cmd /k "cd frontend && npm run dev"

timeout /t 3 /nobreak >nul
start http://localhost:3000

echo.
echo Dashboard launched!
echo Backend:  http://localhost:5000
echo Frontend: http://localhost:3000
echo ==================================================

