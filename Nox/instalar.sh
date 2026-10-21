#!/bin/sh
# Instala Nox en Linux: crea el entorno de Python dentro del proyecto, instala las
# dependencias, baja la voz y revisa que todo este en orden.
#
#     ./instalar.sh
cd "$(dirname "$(readlink -f "$0")")" || exit 1

echo "=== Instalando Nox (Linux) ==="

if ! command -v python3 >/dev/null 2>&1; then
    echo "No encuentro python3. Instalalo con el gestor de paquetes de tu distro."
    exit 1
fi

# Tk lo trae el sistema, no pip: sin el la interfaz no abre.
if ! python3 -c "import tkinter" >/dev/null 2>&1; then
    echo "Falta Tk (la libreria de ventanas de Python). Instalala y vuelve a correr esto:"
    echo "  Arch/CachyOS:   sudo pacman -S tk"
    echo "  Debian/Ubuntu:  sudo apt install python3-tk"
    echo "  Fedora:         sudo dnf install python3-tkinter"
    exit 1
fi

if [ ! -d .venv ]; then
    python3 -m venv .venv || {
        echo "No pude crear el entorno. En Debian/Ubuntu: sudo apt install python3-venv"
        exit 1
    }
fi

.venv/bin/python -m pip install --upgrade pip || exit 1
.venv/bin/python -m pip install -r requirements.txt || {
    echo
    echo "Fallo la instalacion. Si el error menciona portaudio, instalalo:"
    echo "  Arch/CachyOS:   sudo pacman -S portaudio"
    echo "  Debian/Ubuntu:  sudo apt install libportaudio2"
    exit 1
}

if [ ! -f voces/es_MX-claude-high.onnx ]; then
    echo "Descargando la voz de Nox..."
    .venv/bin/python -m piper.download_voices es_MX-claude-high --data-dir voces \
        || echo "No pude bajar la voz: Nox usara la del sistema (instala espeak-ng)."
fi

echo "Armando el catalogo de programas..."
.venv/bin/python escanear_programas.py

if command -v ollama >/dev/null 2>&1; then
    printf "¿Descargar los modelos de Ollama ahora (unos 5.5 GB)? [s/N] "
    read -r respuesta
    case "$respuesta" in
        s|S|si|SI|Si)
            ollama pull qwen3:8b
            ollama pull nomic-embed-text
            ;;
    esac
else
    echo "Falta Ollama: https://ollama.com/download  (despues: ollama pull qwen3:8b y ollama pull nomic-embed-text)"
fi

echo
.venv/bin/python chequeo.py
echo
echo "Para abrir Nox:  ./Asistente.sh"
