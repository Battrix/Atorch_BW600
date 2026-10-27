@echo off
cd /d "%~dp0.."
echo Descarcare 3 A pana la 4.0 V, pauza 5 s, apoi incarcare (CDC). Sursa OWON PORNITA: 4.20 V / 0.5 A.
py tools\probe_dis_chg.py
echo.
pause
