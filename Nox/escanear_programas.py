"""
Arma el catalogo de programas que Nox puede abrir.

En Linux lee los lanzadores .desktop (los mismos que muestra el menu de KDE); en Windows,
los accesos directos del menu inicio. En los dos casos suma la biblioteca de Steam. El
resultado se guarda en programas.json, que es la lista blanca: Nox solo puede abrir lo que
este ahi.

Correr de nuevo cuando instales algo nuevo (con el Python del entorno de Nox):
    python escanear_programas.py

El catalogo es propio de cada maquina. Si falta, o es de otro sistema operativo, Nox lo
vuelve a armar solo al arrancar.
"""
import configparser
import json
import os
import re
import shlex
import sys
import unicodedata
from pathlib import Path

import plataforma

plataforma.configurar_salida()

SALIDA = Path(__file__).resolve().parent / "programas.json"

# Windows: donde el sistema deja un acceso directo de casi todo lo instalado. Tambien es la
# lista blanca de sitios desde donde Nox acepta abrir un acceso directo.
MENUS_INICIO = [
    Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "Microsoft" / "Windows" / "Start Menu" / "Programs",
]

# Lanzadores que no sirven de nada como "programa para abrir".
RUIDO = (
    "uninstall", "desinstalar", "readme", "leame", "help", "ayuda", "manual",
    "documentation", "license", "changelog", "website", "sitio web", "support",
    "report a", "crash", "config file", "settings file", "modo seguro", "safe mode",
    "url handler",
    "avahi",  # exploradores de red de Avahi: herramientas de diagnostico, no programas
)

# Componentes internos que Steam instala como si fueran juegos.
NO_SON_JUEGOS = (
    "steamworks common redistributables", "steam linux runtime", "proton",
    "steamvr", "steam controller", "directx", "vc redist",
)

# Cosas de Steam que se abren igual que un juego pero no lo son. Importa para que Nox
# no crea que estas jugando (y no te quite el modelo local de la grafica) cuando solo
# esta corriendo el fondo animado.
APPS_STEAM_QUE_NO_SON_JUEGOS = {
    "431960",  # Wallpaper Engine
}


def normalizar(texto: str) -> str:
    """Minusculas y sin tildes, para poder buscar sin preocuparse por como se escribio."""
    texto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


# --- Windows: menu inicio ---

def escanear_menu_inicio() -> dict[str, dict]:
    encontrados = {}
    for base in MENUS_INICIO:
        if not base.exists():
            continue
        for lnk in base.rglob("*.lnk"):
            nombre = lnk.stem
            if any(r in normalizar(nombre) for r in RUIDO):
                continue
            clave = normalizar(nombre)
            if clave not in encontrados:
                encontrados[clave] = {
                    "nombre": nombre,
                    "destino": str(lnk),
                    "tipo": "programa",
                }
    return encontrados


# --- Linux: lanzadores .desktop ---

def carpetas_aplicaciones() -> list[Path]:
    """
    Donde viven los .desktop, en orden de prioridad: el usuario pisa al sistema, igual
    que en el menu de KDE (especificacion XDG).

    Es tambien la lista blanca de sitios desde donde Nox acepta abrir un lanzador: son
    carpetas que solo tocan el gestor de paquetes o Brian, nunca Nox.
    """
    datos_usuario = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    datos_sistema = (os.environ.get("XDG_DATA_DIRS") or "").split(":")

    bases = [datos_usuario]
    bases += [Path(p) for p in datos_sistema if p]
    # Fijas ademas de las del entorno: si Nox arranca con otro XDG_DATA_DIRS que el
    # escaner, un lanzador del catalogo no puede quedar de golpe "fuera de lugar".
    bases += [
        Path("/usr/local/share"), Path("/usr/share"),
        datos_usuario / "flatpak" / "exports" / "share",
        Path("/var/lib/flatpak/exports/share"),
    ]

    carpetas = []
    for base in bases:
        carpeta = base / "applications"
        if carpeta not in carpetas:
            carpetas.append(carpeta)
    return carpetas


def leer_desktop(ruta: Path) -> dict | None:
    """La seccion [Desktop Entry] de un lanzador, o None si no se puede leer."""
    lector = configparser.RawConfigParser(strict=False, interpolation=None)
    lector.optionxform = str  # las claves distinguen mayusculas: Name, NoDisplay...
    try:
        lector.read(ruta, encoding="utf-8")
    except (configparser.Error, UnicodeDecodeError, OSError):
        return None
    if not lector.has_section("Desktop Entry"):
        return None
    return dict(lector["Desktop Entry"])


def _lista(valor: str) -> list[str]:
    return [x for x in (valor or "").split(";") if x]


def es_visible(entrada: dict) -> bool:
    """True si el lanzador aparece en el menu de KDE (mismas reglas que usa el menu)."""
    if entrada.get("Type") != "Application" or not entrada.get("Exec"):
        return False
    if entrada.get("NoDisplay", "").lower() == "true":
        return False
    if entrada.get("Hidden", "").lower() == "true":
        return False

    escritorios = os.environ.get("XDG_CURRENT_DESKTOP", "KDE").split(":")
    solo_en = _lista(entrada.get("OnlyShowIn"))
    if solo_en and not any(e in escritorios for e in solo_en):
        return False
    return not any(e in escritorios for e in _lista(entrada.get("NotShowIn")))


def ejecutable_de(exec_linea: str) -> str:
    """
    Nombre del programa que corre un lanzador ("brave", "konsole"...). Se usa para
    reconocer su proceso al cerrarlo a la fuerza.
    """
    try:
        partes = shlex.split(exec_linea)
    except ValueError:
        partes = exec_linea.split()
    # Saltar "env VAR=valor ..." que algunos lanzadores ponen adelante.
    while partes and (Path(partes[0]).name == "env" or "=" in partes[0]):
        partes.pop(0)
    return Path(partes[0]).name if partes else ""


def escanear_lanzadores() -> dict[str, dict]:
    encontrados = {}
    vistos = set()  # id del lanzador (nombre de archivo): el primero en prioridad gana

    for carpeta in carpetas_aplicaciones():
        if not carpeta.is_dir():
            continue
        for ruta in sorted(carpeta.rglob("*.desktop")):
            id_lanzador = str(ruta.relative_to(carpeta)).replace("/", "-")
            if id_lanzador in vistos:
                continue
            vistos.add(id_lanzador)

            entrada = leer_desktop(ruta)
            if entrada is None or not es_visible(entrada):
                continue

            # Los juegos de Steam se toman de la biblioteca de Steam, no de su acceso
            # directo: asi quedan con su appid y no aparecen duplicados.
            if "steam://rungameid/" in entrada["Exec"]:
                continue

            nombre = (entrada.get("Name[es]") or entrada.get("Name") or "").strip()
            if not nombre or any(r in normalizar(nombre) for r in RUIDO):
                continue

            clave = normalizar(nombre)
            if clave in encontrados:
                continue

            # Otras formas de llamarlo: el nombre en ingles y el generico
            # ("Navegador web", "Terminal"), para que "abri el navegador" funcione.
            alias = {
                normalizar(entrada.get(k, "")).strip()
                for k in ("Name", "GenericName[es]", "GenericName")
            }
            alias.discard("")
            alias.discard(clave)

            encontrados[clave] = {
                "nombre": nombre,
                "destino": str(ruta),
                "tipo": "programa",
                "ejecutable": ejecutable_de(entrada["Exec"]),
                "alias": sorted(alias),
            }
    return encontrados


# --- Steam ---

def ruta_steam() -> Path | None:
    """Carpeta de Steam: la del registro en Windows; la nativa o la de Flatpak en Linux."""
    if plataforma.ES_WINDOWS:
        import winreg
        for hive, sub in [
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        ]:
            try:
                with winreg.OpenKey(hive, sub) as k:
                    p = Path(winreg.QueryValueEx(k, "SteamPath")[0])
                    if p.exists():
                        return p
            except OSError:
                continue
        return None

    candidatas = [
        Path.home() / ".local" / "share" / "Steam",
        Path.home() / ".steam" / "steam",
        Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
    ]
    for p in candidatas:
        if (p / "steamapps").is_dir():
            return p.resolve()
    return None


def escanear_steam() -> dict[str, dict]:
    """Lee los appmanifest de cada biblioteca de Steam para sacar los juegos."""
    steam = ruta_steam()
    if steam is None:
        return {}

    bibliotecas = [steam / "steamapps"]

    # Otras bibliotecas (discos secundarios) estan listadas en libraryfolders.vdf
    vdf = steam / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        texto = vdf.read_text(encoding="utf-8", errors="ignore")
        for ruta in re.findall(r'"path"\s+"([^"]+)"', texto):
            carpeta = (Path(ruta.replace("\\\\", "\\")) / "steamapps").resolve()
            if carpeta.exists() and carpeta not in [b.resolve() for b in bibliotecas]:
                bibliotecas.append(carpeta)

    juegos = {}
    for biblioteca in bibliotecas:
        for manifest in biblioteca.glob("appmanifest_*.acf"):
            texto = manifest.read_text(encoding="utf-8", errors="ignore")
            appid = re.search(r'"appid"\s+"(\d+)"', texto)
            nombre = re.search(r'"name"\s+"([^"]+)"', texto)
            if not (appid and nombre):
                continue

            # Steam instala componentes internos como si fueran juegos. No lo son.
            if any(x in normalizar(nombre.group(1)) for x in NO_SON_JUEGOS):
                continue

            es_juego = appid.group(1) not in APPS_STEAM_QUE_NO_SON_JUEGOS
            juegos[normalizar(nombre.group(1))] = {
                "nombre": nombre.group(1),
                "destino": f"steam://rungameid/{appid.group(1)}",
                "tipo": "juego" if es_juego else "programa",
            }
    return juegos


def escanear_programas() -> dict[str, dict]:
    """Los programas instalados, segun el sistema en que corra."""
    return escanear_menu_inicio() if plataforma.ES_WINDOWS else escanear_lanzadores()


def catalogo_es_de_este_so(catalogo: dict) -> bool:
    """
    False si el catalogo se armo en otro sistema operativo. Se nota en los destinos de los
    programas: .desktop en Linux, .lnk/.url/.exe en Windows (los de Steam valen en ambos).
    """
    esperados = (".lnk", ".url", ".exe") if plataforma.ES_WINDOWS else (".desktop",)
    destinos = [
        d.get("destino", "") for d in catalogo.values()
        if not d.get("destino", "").startswith("steam://")
    ]
    return all(Path(d).suffix.lower() in esperados for d in destinos)


def generar_catalogo(guardar: bool = True) -> dict[str, dict]:
    """Escanea el equipo y arma el catalogo. Si 'guardar', lo escribe en programas.json."""
    programas = escanear_programas()
    juegos = escanear_steam()

    # Los juegos pisan a un programa del mismo nombre: es mas util lanzarlo por Steam.
    catalogo = {**programas, **juegos}
    if guardar:
        SALIDA.write_text(json.dumps(catalogo, ensure_ascii=False, indent=2), encoding="utf-8")
    return catalogo


def main():
    programas = escanear_programas()
    juegos = escanear_steam()
    catalogo = generar_catalogo()

    print(f"Programas del menu:        {len(programas)}")
    print(f"De Steam:                  {len(juegos)}")
    print(f"Total en el catalogo:      {len(catalogo)}")
    print(f"Guardado en {SALIDA}")

    if juegos:
        print("\nDe Steam:")
        for j in juegos.values():
            print(f"  - {j['nombre']}" + ("" if j["tipo"] == "juego" else "  (programa)"))


if __name__ == "__main__":
    main()
