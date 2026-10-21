"""
Chequeo de arranque: dice si Nox esta listo para usarse y que le falta.

    python chequeo.py

No carga el modelo local en la grafica (para no molestar si estas jugando), solo
verifica que todo este en su lugar.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests

import config
import plataforma

plataforma.configurar_salida()

OK, MAL, AVISO = "  [OK ]", "  [MAL]", "  [ ! ]"
problemas = []


def revisar(descripcion, condicion, ayuda="", critico=True):
    if condicion:
        print(f"{OK} {descripcion}")
    else:
        print(f"{MAL if critico else AVISO} {descripcion}")
        if ayuda:
            print(f"        -> {ayuda}")
        if critico:
            problemas.append(descripcion)


print(f"=== {config.NOMBRE} — chequeo de arranque ({plataforma.NOMBRE_SO}) ===\n")

if config.MOTOR_CHAT == "openrouter":
    print(f"MOTOR DE CONVERSACIÓN: NUBE (OpenRouter — {config.MODELO_OPENROUTER})")
    import nube
    tiene_key = nube.disponible()
    revisar("Clave de OpenRouter configurada", tiene_key,
            f"Pega tu clave (sk-or-...) en {nube.ARCHIVO_KEY} o configúrala en Ajustes > Nube.", critico=True)
    if tiene_key:
        print(f"        modelo principal: {config.MODELO_OPENROUTER}")
        print(f"        respaldo: {len(config.MODELOS_NUBE_ALTERNATIVOS)} modelos alternativos")

    print("\nMODELO LOCAL (Ollama — opcional, no requerido en modo nube)")
    try:
        r = requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=2)
        instalados = [m["name"] for m in r.json().get("models", [])]
        revisar("Ollama está corriendo", True, critico=False)
    except requests.RequestException:
        print("  [ - ] Ollama no está activo (correcto: Nox usa OpenRouter directamente)")
else:
    print("MODELO LOCAL (Ollama)")
    try:
        r = requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=5)
        instalados = [m["name"] for m in r.json().get("models", [])]
        revisar("Ollama esta corriendo", True)
        for m in (config.MODELO_CHAT, config.MODELO_EMBED):
            base = m.split(":")[0]
            revisar(f"modelo {m}", any(x.startswith(base) for x in instalados),
                    f"instalalo con: ollama pull {m}")
    except requests.RequestException:
        revisar("Ollama esta corriendo", False,
                "abrilo desde el menu de aplicaciones, o corre: ollama serve")

print("\nBOVEDA (opcional: sin ella Nox funciona, pero sin wiki personal)")
revisar("la carpeta existe", config.BOVEDA.exists(),
        f"{config.BOVEDA} — se cambia en config_local.json (clave \"boveda\")", critico=False)
revisar("el indice RAG existe", config.INDICE_DB.exists(),
        "corre: python RAG/index_vault.py desde la boveda", critico=False)
if config.INDICE_DB.exists():
    import sqlite3
    con = sqlite3.connect(config.INDICE_DB)
    n = con.execute("SELECT COUNT(1) FROM chunks").fetchone()[0]
    con.close()
    print(f"        {n} fragmentos indexados")

print("\nVOZ")
revisar("voz Piper instalada", config.VOZ_PIPER.exists(),
        "python -m piper.download_voices es_MX-claude-high --data-dir voces "
        "(lo hace el instalador); mientras tanto usa la voz del sistema",
        critico=False)
print(f"        palabra de activacion: \"{config.PALABRA_ACTIVACION}\"")

print("\nCONTROL DE LA PC")
import sistema
catalogo = sistema.cargar_catalogo()
revisar(f"catalogo de programas ({len(catalogo)} entradas)", bool(catalogo),
        "corre: python escanear_programas.py")
juego = sistema.hay_juego_corriendo()
if juego:
    print(f"{AVISO} hay un juego abierto: {juego}")
    print("        Nox va a ceder la grafica y usar la nube donde pueda")

print("\nHERRAMIENTAS EXTERNAS (opcional)")
try:
    import mcp  # noqa: F401
    paquete_mcp = True
except ImportError:
    paquete_mcp = False
revisar("el paquete 'mcp' esta instalado", paquete_mcp, "pip install mcp", critico=False)
import shutil
revisar("Node.js (lo necesitan servidores como el navegador Playwright)", shutil.which("node") is not None,
        "instalalo desde https://nodejs.org (solo si vas a usar ese tipo de servidores)", critico=False)
import mcp_cliente
_externos = mcp_cliente.administrador().servidores
print(f"        {len(_externos)} servidor(es) configurado(s), {sum(1 for d in _externos.values() if d['activo'])} activo(s)")

print("\nHERRAMIENTAS")
import herramientas
print(f"        {len(herramientas.ESQUEMAS)} locales, "
      f"{len(nube.HERRAMIENTAS_PUBLICAS)} disponibles en la nube")

print("\n" + "=" * 58)
if problemas:
    print(f"FALTA RESOLVER {len(problemas)}:")
    for p in problemas:
        print("  -", p)
    sys.exit(1)
lanzador = "Asistente.bat" if plataforma.ES_WINDOWS else "Asistente.sh (o 'Nox' en el menu)"
print(f"{config.NOMBRE} esta listo. Arrancalo con {lanzador}.")
