@echo off
cd /d "%~dp0"
python cleanup_listener.py --leave-channels
echo.
pause
