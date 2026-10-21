"""
Corre todas las pruebas de Nox, una tras otra, y dice cual falla.

    python probar_todo.py

Hay que correrlo con el Python del entorno de Nox (el mismo que usa Asistente.sh / .bat).
No necesita Ollama ni internet: son pruebas de seguridad, privacidad y compatibilidad.
"""
import subprocess
import sys
from pathlib import Path

PROYECTO = Path(__file__).resolve().parent
PRUEBAS = [
    ("seguridad", "test_seguridad.py"),
    ("barreras (limites firmes)", "test_barreras.py"),
    ("privacidad", "test_privacidad.py"),
    ("Linux / Windows", "test_plataforma.py"),
    ("nombre de usuario", "test_usuario.py"),
    ("deteccion de voz (VAD)", "test_voz.py"),
    ("evaluador de modelos", "test_evaluador.py"),
    ("ajustes desde la interfaz", "test_ajustes.py"),
    ("herramientas externas (MCP)", "test_mcp.py"),
    ("interfaz (Ajustes y bienvenida)", "test_interfaz.py"),
    ("nombres mal escuchados", "test_nombres.py"),
    ("iniciativa (recordatorios)", "test_iniciativa.py"),
    ("memoria", "test_memoria.py"),
    ("vista (mirar la pantalla)", "test_vista.py"),
]

resultados = []
for nombre, archivo in PRUEBAS:
    r = subprocess.run([sys.executable, archivo], cwd=PROYECTO, capture_output=True,
                       text=True, encoding="utf-8", errors="ignore")
    ok = r.returncode == 0 and "[FALLA]" not in r.stdout
    resultados.append((nombre, ok, r.stdout))
    print(f"  [{'OK ' if ok else 'FALLA'}] {nombre}")

fallidas = [(n, s) for n, ok, s in resultados if not ok]
for nombre, salida in fallidas:
    print(f"\n--- {nombre}: lineas con problema ---")
    print("\n".join(l for l in salida.splitlines() if "[FALLA]" in l or l.startswith("  - ")))

print()
print("TODO EN ORDEN" if not fallidas else f"FALLARON {len(fallidas)} de {len(PRUEBAS)} grupos")
sys.exit(1 if fallidas else 0)
