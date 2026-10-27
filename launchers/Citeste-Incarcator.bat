@echo off
cd /d "%~dp0.."
echo Cautare tensiune incarcator (doar citire).
py tools\probe_charger.py
echo.
pause
