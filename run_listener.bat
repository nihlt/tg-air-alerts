@echo off
cd /d "%~dp0"

echo Cleanup before start...
python cleanup_listener.py
if errorlevel 1 pause & exit /b 1

echo.
echo Starting listener. Stop with Ctrl+C.
echo.
python listen_tg_channels.py

echo.
pause
