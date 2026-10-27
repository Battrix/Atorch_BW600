@echo off
cd /d "%~dp0.."
echo Verific selectarea modurilor (nu porneste sarcina).
py tools\probe_select.py
echo.
pause
