@echo off
cd /d "%~dp0.."
echo Pornesc Atorch Lab (USB). Lasa aceasta fereastra deschisa. Ctrl+C = oprire.
py -m atorch --usb --port 8787
echo.
pause
