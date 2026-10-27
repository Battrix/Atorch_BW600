@echo off
cd /d "%~dp0.."
echo Ascult pasiv aparatul (doar citire, toti octetii) 30 min. Porneste CDC de pe aparat. Ctrl+C = oprire.
py tools\probe_modes.py --all --seconds 1800
echo.
pause
