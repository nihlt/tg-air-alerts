@echo off
setlocal
cd /d "%~dp0"

echo Stopping previous listener instances...
python stop_listener.py
if errorlevel 1 (
    echo Failed to stop previous listener.
    pause
    exit /b 1
)

echo.
echo Starting listener...
python listen_tg_channels.py

echo.
echo Listener exited.
pause
