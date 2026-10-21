"""
Control del sistema en Windows (10 y 11), con PowerShell para lo que Python no trae.

Es la otra mitad de la interfaz que implementa so_linux.py: ahi esta la lista de lo que
exporta cada modulo, y sistema.py elige cual usar. Este modulo se puede importar en
cualquier sistema (no usa nada exclusivo de Windows al importarse), asi las pruebas de
seguridad pueden revisar sus validaciones tambien desde Linux.
"""
import json
import os
import re
import subprocess

import escanear_programas
import plataforma
import seguridad
from seguridad import Rechazado

_normalizar = seguridad.normalizar

# En Windows un programa con varias ventanas es un solo proceso (Chrome, Explorer...):
# se cierran juntas en vez de preguntar cual.
AGRUPA_MISMA_APP = True

# Procesos que no son juegos aunque vengan de Steam.
NO_CUENTAN = frozenset({
    "steam", "steamwebhelper", "steamservice", "gameoverlayui",
    "ollama", "ollama app", "explorer", "dwm",
})


def _powershell(script: str, timeout: int) -> subprocess.CompletedProcess:
    """
    Corre un script de PowerShell sin ventana. Se fuerza UTF-8 en la salida: por defecto
    PowerShell usa la pagina de codigos del sistema y las tildes llegan rotas.
    """
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         "[Console]::OutputEncoding = [Text.Encoding]::UTF8; " + script],
        capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="ignore", **plataforma.kwargs_sin_ventana(),
    )


# --- Abrir programas ---

def validar_destino(datos: dict) -> str:
    """
    Comprueba una entrada del catalogo y devuelve lo que se va a abrir. Lanza Rechazado
    si el destino no es de una de las dos formas esperadas: un acceso directo del menu
    inicio, o una URL de Steam. Asi, si alguien editara programas.json a mano, no se
    convierte en via libre.
    """
    destino = datos["destino"]

    if destino.startswith("steam://"):
        if not re.fullmatch(r"steam://rungameid/\d+", destino):
            raise Rechazado("Ese destino de Steam no tiene el formato esperado. No lo abro.")
        return destino

    ruta = seguridad.resolver(destino)
    if ruta.suffix.lower() not in (".lnk", ".url", ".exe"):
        raise Rechazado(f"El destino de '{datos['nombre']}' no es un acceso directo. No lo abro.")
    if not seguridad.dentro_de(ruta, escanear_programas.MENUS_INICIO):
        raise Rechazado(
            f"El acceso directo de '{datos['nombre']}' no esta en el menu inicio. No lo abro."
        )
    if not ruta.exists():
        raise Rechazado(
            f"'{datos['nombre']}' esta en el catalogo pero ya no existe en disco. "
            "Se puede actualizar corriendo escanear_programas.py."
        )
    return str(ruta)


def abrir(datos: dict):
    plataforma.abrir_con_predeterminado(validar_destino(datos))


# --- Ventanas ---

def ventanas_abiertas() -> list[dict]:
    """Programas con ventana abierta. Es lo que un humano llamaria 'lo que tengo abierto'."""
    try:
        r = _powershell(
            "Get-Process | Where-Object { $_.MainWindowTitle -ne '' } | "
            "Select-Object ProcessName, Id, MainWindowTitle | ConvertTo-Json -Compress",
            timeout=20,
        )
        datos = json.loads(r.stdout or "[]")
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    if isinstance(datos, dict):  # con una sola ventana, PowerShell devuelve un objeto suelto
        datos = [datos]

    yo = os.getpid()
    return [
        {"id": p["Id"], "titulo": (p.get("MainWindowTitle") or "").strip(),
         "app": p.get("ProcessName") or ""}
        for p in datos if p.get("Id") and p["Id"] != yo
    ]


def _ids(ventanas: list[dict]) -> list[int]:
    """Los pid como enteros: es lo unico que se mete en el script de PowerShell."""
    return sorted({int(v["id"]) for v in ventanas})


def cerrar_ventanas(ventanas: list[dict]) -> str | None:
    """
    Le pide a cada programa que cierre su ventana principal (CloseMainWindow), como el
    boton X: tiene la chance de preguntar si guardar. Devuelve un error o None.
    """
    ids = _ids(ventanas)
    try:
        r = _powershell(
            f"Get-Process -Id {','.join(map(str, ids))} | "
            "ForEach-Object { $null = $_.CloseMainWindow() }",
            timeout=25,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return f"No pude cerrar la ventana: {e}"
    if r.returncode != 0:
        return f"No pude cerrar la ventana: {(r.stderr or '').strip()[:200]}"
    return None


def cerrar_a_la_fuerza(ventanas: list[dict], nombres: set[str]) -> tuple[int, int]:
    """Termina los procesos de esas ventanas, sin preguntar. Devuelve (procesos, 0)."""
    ids = _ids([v for v in ventanas if not seguridad.es_intocable(_normalizar(v["app"]))])
    if not ids:
        return 0, 0
    try:
        _powershell(f"Stop-Process -Id {','.join(map(str, ids))} -Force", timeout=25)
    except (OSError, subprocess.SubprocessError):
        return 0, 0
    return len(ids), 0


# --- Deteccion de juegos en curso ---

def _appid_de_steam_en_curso() -> str | None:
    """
    Steam anota en el registro el juego que esta corriendo (RunningAppID, 0 si ninguno).
    Es mas fiable que adivinar por el nombre de los procesos.
    """
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            valor = int(winreg.QueryValueEx(k, "RunningAppID")[0])
        return str(valor) if valor else None
    except (ImportError, OSError, ValueError):
        return None


def juego_corriendo(catalogo: dict) -> str | None:
    """Nombre del juego en curso, o None."""
    excluidos = escanear_programas.APPS_STEAM_QUE_NO_SON_JUEGOS

    juegos_por_appid = {}
    for datos in catalogo.values():
        m = re.fullmatch(r"steam://rungameid/(\d+)", datos.get("destino", ""))
        if m:
            juegos_por_appid[m.group(1)] = datos["nombre"]

    appid = _appid_de_steam_en_curso()
    if appid and appid not in excluidos:
        return juegos_por_appid.get(appid, f"un juego de Steam (id {appid})")

    # Respaldo para lo que no pasa por Steam: nombres de proceso probables a partir del
    # catalogo. "Monster Hunter Wilds" -> "monsterhunterwilds"
    esperados = {}
    for datos in catalogo.values():
        if datos.get("tipo") != "juego":
            continue
        clave = re.sub(r"[^a-z0-9]", "", _normalizar(datos["nombre"]))
        if clave:
            esperados[clave] = datos["nombre"]

    try:
        r = _powershell("Get-Process | Select-Object -ExpandProperty ProcessName", timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    for linea in (r.stdout or "").splitlines():
        proceso = linea.strip().lower()
        if not proceso or proceso in NO_CUENTAN:
            continue
        limpio = re.sub(r"[^a-z0-9]", "", proceso)
        if not limpio:
            continue
        for clave, nombre in esperados.items():
            # Coincidencia por prefijo: el proceso suele llamarse como el juego.
            if limpio.startswith(clave[:12]) or clave.startswith(limpio[:12]):
                return nombre
    return None


# --- Volumen y multimedia ---

# Codigos de las teclas multimedia de Windows.
TECLAS = {
    "subir_volumen": 175,
    "bajar_volumen": 174,
    "silenciar": 173,
    "reproducir_pausar": 179,
    "siguiente": 176,
    "anterior": 177,
}
ACCIONES_MULTIMEDIA = tuple(TECLAS)


def tecla_multimedia(accion: str, repeticiones: int) -> str | None:
    envios = "".join([f"$w.SendKeys([char]{TECLAS[accion]});"] * repeticiones)
    try:
        _powershell(f"$w = New-Object -ComObject WScript.Shell; {envios}", timeout=15)
    except (OSError, subprocess.SubprocessError) as e:
        return f"No pude: {e}"
    return None


# --- Consultas del sistema (solo lectura) ---

def ejecutar_consulta(comando: str) -> str:
    """
    Ejecuta un comando de PowerShell de consulta. La validacion vive en seguridad.py:
    lista blanca de verbos aplicada a cada tramo del pipeline, mas tokens prohibidos.
    """
    try:
        limpio = seguridad.validar_consulta_powershell(comando)
    except Rechazado as e:
        return str(e)

    try:
        r = _powershell(limpio, timeout=30)
    except subprocess.TimeoutExpired:
        return "El comando tardo mas de 30 segundos."
    except (OSError, subprocess.SubprocessError) as e:
        return f"No pude ejecutarlo: {e}"

    salida = (r.stdout or "").strip() or (r.stderr or "").strip()
    return salida[:3000] if salida else "(sin salida)"
