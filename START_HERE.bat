@echo off
title GridShield AI - Launcher
cd /d "%~dp0"
echo Launching backend and dashboard...
start "GridShield Backend" cmd /k "%~dp0start_backend.bat"
timeout /t 6 /nobreak >nul
start "GridShield Dashboard" cmd /k "%~dp0start_frontend.bat"
echo.
echo Both windows opened.
echo   Dashboard:  http://localhost:5173  (opens automatically)
echo   API health: http://localhost:8000/health
echo Close both windows to stop.
start "" http://localhost:5173
