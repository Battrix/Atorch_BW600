@echo off
cd /d "%~dp0.."
echo Pornesc Atorch Lab (SIMULAT, fara aparat). Ctrl+C = oprire.
py -m atorch --sim --port 8788
echo.
pause
