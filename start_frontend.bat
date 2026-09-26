@echo off
title GridShield AI - Dashboard
cd /d "%~dp0frontend"
echo ============================================
echo   GridShield AI - Dashboard (port 5173)
echo   Keep this window OPEN while demoing.
echo   Stop: press Ctrl+C or close this window.
echo ============================================
npm run dev
pause
