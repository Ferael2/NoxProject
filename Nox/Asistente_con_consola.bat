@echo off
REM Igual que Asistente.bat, pero con la consola abierta: aca se ven los errores.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" gui.py
) else (
    python.exe gui.py
)
pause
