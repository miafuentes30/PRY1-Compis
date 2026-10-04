@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 verificar_proyecto.py
) else (
  python verificar_proyecto.py
)
pause
