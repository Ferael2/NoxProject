#!/bin/sh
# Lanza Nox con su interfaz grafica (Linux).
# Es la forma recomendada de usarlo en el dia a dia: arranca al instante y toma los
# cambios que le hagas al codigo sin recompilar nada. Lo que Nox imprime queda en el
# diario: journalctl --user -t nox
cd "$(dirname "$(readlink -f "$0")")" || exit 1

# Entorno de Python: el que crea instalar.sh dentro del proyecto (.venv); si no existe,
# el de siempre (~/.venvs/nox); y si tampoco, el Python del sistema.
if [ -x ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
elif [ -x "$HOME/.venvs/nox/bin/python" ]; then
    PYTHON="$HOME/.venvs/nox/bin/python"
else
    PYTHON="python3"
fi

if command -v systemd-cat >/dev/null 2>&1; then
    exec systemd-cat -t nox "$PYTHON" gui.py
fi
exec "$PYTHON" gui.py
