@echo off
title ScreenStash Installer & Setup
echo ========================================================
echo   ScreenStash Desktop Installer
echo ========================================================
echo.
echo [1/3] Installing dependencies...
python -m pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [!] Failed to install dependencies. Please ensure Python is on your PATH.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [2/3] Configuring application, database, and shortcuts...
python screenstash.py install

echo.
echo [3/3] Installation Complete!
echo Complete the short onboarding screen to start ScreenStash.
echo.
pause
