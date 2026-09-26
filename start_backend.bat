@echo off
title GridShield AI - Backend
cd /d "%~dp0"
echo ============================================
echo   GridShield AI - Backend (port 8000)
echo   Keep this window OPEN while demoing.
echo   Stop: press Ctrl+C or close this window.
echo ============================================
.venv\Scripts\uvicorn.exe app.main:app --port 8000 --app-dir backend
pause
