@echo off
cd /d "%~dp0.."
echo Pornesc Atorch Lab (USB, jurnal detaliat). Ctrl+C = oprire.
py -m atorch --usb --debug --port 8787
echo.
pause
