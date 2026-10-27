@echo off
cd /d "%~dp0.."
echo Instalez dependentele (USB + certificat PDF)...
py -m pip install -e .[usb,report]
echo.
pause
