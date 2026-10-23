@echo off
title ScreenStash Desktop Installer
echo ========================================================
echo   ScreenStash Desktop Installer
echo ========================================================
echo.
echo [1/3] Checking and installing dependencies...
python -m pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [!] Failed to install dependencies. Please ensure Python is on your PATH.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [2/3] Registering Desktop shortcuts and brand icons...
python setup_app.py

echo.
echo [3/3] Launching ScreenStash Desktop...
python run_desktop.py
