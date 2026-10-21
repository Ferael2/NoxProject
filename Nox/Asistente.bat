@echo off
REM Lanza Nox sin ventana de consola (Windows).
REM Es la forma recomendada de usarlo en el dia a dia: arranca al instante y toma los
REM cambios que le hagas al codigo sin recompilar nada.
REM Si no abre, usa Asistente_con_consola.bat para ver el error.
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" gui.py
) else (
    start "" pythonw.exe gui.py
)
