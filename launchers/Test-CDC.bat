@echo off
cd /d "%~dp0.."
echo Test CDC pe celula 18650 (sursa OWON 4.20 V / 0.5 A pe intrarea CHARGER).
py tools\probe_cdc.py
echo.
pause
