@echo off
cd /d "%~dp0.."
echo Observare pasiva a aparatului (doar citire). Navigheaza pe aparat prin meniu. Ctrl+C = oprire.
py tools\probe_modes.py
echo.
pause
