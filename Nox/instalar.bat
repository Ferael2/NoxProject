@echo off
REM Instala Nox en Windows: crea el entorno de Python dentro del proyecto, instala las
REM dependencias, baja la voz y revisa que todo este en orden.
REM Hace falta Python 3.12 desde https://www.python.org (marcando "Add python.exe to PATH").
setlocal
cd /d "%~dp0"

echo === Instalando Nox (Windows) ===

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo No encuentro Python. Instalalo desde https://www.python.org y vuelve a correr esto.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    %PY% -m venv .venv
    if errorlevel 1 (
        echo No pude crear el entorno de Python.
        pause
        exit /b 1
    )
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Fallo la instalacion de las dependencias. Revisa el error de arriba.
    pause
    exit /b 1
)

if not exist "voces\es_MX-claude-high.onnx" (
    echo Descargando la voz de Nox...
    ".venv\Scripts\python.exe" -m piper.download_voices es_MX-claude-high --data-dir voces
    if errorlevel 1 echo No pude bajar la voz: Nox usara la voz de Windows.
)

echo Armando el catalogo de programas...
".venv\Scripts\python.exe" escanear_programas.py

echo.
echo Nox esta configurado para operar en la nube con OpenRouter.
echo No necesitas descargar modelos locales de 5.5 GB ni instalar Ollama.
if not exist "openrouter.key" (
    echo Recuerda pegar tu clave de OpenRouter (sk-or-...) en el archivo openrouter.key
    echo o ingresarla desde Ajustes ^> Nube al iniciar Nox.
) else (
    echo Clave openrouter.key detectada correctamente.
)

echo.
".venv\Scripts\python.exe" chequeo.py
echo.
echo Para abrir Nox: doble clic en Asistente.bat
pause
