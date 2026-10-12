@echo off
title VaultFather Launcher
cd /d "%~dp0"

echo ===================================================
echo             Launching VaultFather...
echo ===================================================
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found on your system PATH!
    echo Please install Python 3.10 or higher from:
    echo https://www.python.org/downloads/
    echo.
    echo IMPORTANT: Make sure to check "Add Python to PATH"
    echo at the bottom of the Python installer window!
    echo.
    pause
    exit /b 1
)

python -c "import PySide6" >nul 2>&1
if %errorlevel% neq 0 (
    echo First-time setup: Installing required libraries...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo.
        echo [ERROR] Failed to install dependencies. Please run:
        echo pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
)

echo Starting VaultFather Command Interface...
python main.py
if %errorlevel% neq 0 (
    echo.
    echo VaultFather exited with code: %errorlevel%
    pause
)
