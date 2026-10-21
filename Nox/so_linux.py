"""
Control del sistema en Linux (probado en KDE Plasma sobre Wayland).

Es la mitad Linux de una interfaz que tambien implementa so_windows.py. sistema.py elige
cual usar segun el sistema en que corra, y el resto de Nox no sabe cual es. Lo que
exporta cada modulo:

    AGRUPA_MISMA_APP     si varias ventanas de un mismo programa se cierran juntas
    ACCIONES_MULTIMEDIA  acciones validas de control_multimedia
    validar_destino      comprueba una entrada del catalogo y devuelve que se va a lanzar
    abrir                lanza una entrada del catalogo
    ventanas_abiertas    ventanas visibles: [{"id", "titulo", "app"}]
    cerrar_ventanas      pide el cierre normal (como apretar la X)
    cerrar_a_la_fuerza   termina los procesos del programa
    juego_corriendo      nombre del juego en curso, o None
    tecla_multimedia     volumen y reproduccion (devuelve un error, o None si salio bien)
    ejecutar_consulta    corre un comando de consulta ya validado por seguridad.py
"""
import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path

import escanear_programas
import plataforma
import seguridad
from seguridad import Rechazado

_normalizar = seguridad.normalizar

# En Linux cada ventana se cierra por separado: una terminal puede tener algo corriendo.
AGRUPA_MISMA_APP = False


# --- Abrir programas ---

def validar_destino(datos: dict) -> list[str]:
    """
    Traduce una entrada del catalogo al comando que la abre. Lanza Rechazado si el
    destino no tiene una de las dos formas esperadas.

    El catalogo es la lista blanca, pero igual se vuelve a verificar aca: un lanzador
    .desktop que este en las carpetas de aplicaciones del sistema, o una URL de Steam.
    Asi, si alguien editara programas.json a mano para apuntar a un .desktop en
    Descargas, no se convierte en via libre.
    """
    destino = datos["destino"]

    if destino.startswith("steam://"):
        if not re.fullmatch(r"steam://rungameid/\d+", destino):
            raise Rechazado("Ese destino de Steam no tiene el formato esperado. No lo abro.")
        # Si Steam ya esta abierto, "steam <url>" se la pasa a la instancia que corre.
        steam = shutil.which("steam")
        return [steam, destino] if steam else ["xdg-open", destino]

    # Se normaliza sin seguir enlaces: los lanzadores de Flatpak son symlinks a la
    # carpeta de la app, y lo que importa es DONDE esta el lanzador, no a que apunta.
    ruta = Path(os.path.normpath(Path(destino).expanduser()))
    if ruta.suffix.lower() != ".desktop":
        raise Rechazado(f"El destino de '{datos['nombre']}' no es un lanzador .desktop. No lo abro.")
    if not seguridad.dentro_de(ruta.parent, escanear_programas.carpetas_aplicaciones()):
        raise Rechazado(
            f"El lanzador de '{datos['nombre']}' no esta en una carpeta de aplicaciones "
            "del sistema. No lo abro."
        )
    if not ruta.exists():
        raise Rechazado(
            f"'{datos['nombre']}' esta en el catalogo pero ya no existe en disco. "
            "Se puede actualizar corriendo escanear_programas.py."
        )
    # gio lee el .desktop y lo lanza como lo haria el menu (campo Exec, terminal, etc.).
    return ["gio", "launch", str(ruta)]


def abrir(datos: dict):
    plataforma.lanzar(validar_destino(datos))


# --- Procesos y ventanas ---

def _procesos_propios() -> list[dict]:
    """
    Procesos del usuario: pid, nombre corto (comm) y argumentos. Se lee /proc directo,
    sin depender de ps ni de librerias.

    Ojo: el kernel recorta el nombre corto a 15 caracteres ("org_kde_powerde"), por
    eso tambien se guarda el nombre completo del ejecutable, sacado de los argumentos.
    """
    uid = os.getuid()
    procesos = []
    for entrada in Path("/proc").iterdir():
        if not entrada.name.isdigit():
            continue
        try:
            if entrada.stat().st_uid != uid:
                continue
            comm = (entrada / "comm").read_text().strip()
            args = (entrada / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue  # el proceso termino mientras se leia
        args = [a.decode(errors="ignore") for a in args if a]
        procesos.append({
            "pid": int(entrada.name),
            "comm": comm,
            "exe": Path(args[0]).name if args else "",
            "args": args,
        })
    return procesos


def _busctl(*argumentos: str) -> dict | None:
    """Llamada D-Bus a la sesion del usuario, con la respuesta en JSON."""
    try:
        r = subprocess.run(
            ["busctl", "--user", "--json=short", "call", *argumentos],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return None
        return json.loads(r.stdout) if r.stdout.strip() else {}
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def ventanas_abiertas() -> list[dict]:
    """
    Ventanas abiertas, segun KWin (el compositor de KDE). Es lo que un humano llamaria
    'lo que tengo abierto'.

    En Wayland ningun programa puede ver las ventanas de otro (es parte de su diseño de
    seguridad), asi que no hay equivalente directo al MainWindowTitle de Windows. La via
    es preguntarle a KWin por D-Bus, a traves del mismo buscador de ventanas que usa
    KRunner: con la palabra clave "ventana" ("window" si el sistema esta en ingles)
    devuelve todas, con su titulo y el icono de la aplicacion.

    Fuera de KDE no hay KWin y la lista sale vacia: abrir programas sigue andando, pero
    Nox no puede ver ni cerrar ventanas.
    """
    ventanas = {}
    for palabra in ("ventana", "window"):
        r = _busctl("org.kde.KWin", "/WindowsRunner", "org.kde.krunner1", "Match", "s", palabra)
        try:
            coincidencias = r["data"][0] if r else []
        except (KeyError, IndexError, TypeError):
            continue
        for m in coincidencias:
            # Formato del id: "<accion>_{uuid}". La accion se elige al ejecutarla.
            uuid = m[0].split("_", 1)[-1]
            ventanas.setdefault(uuid, {"id": uuid, "titulo": m[1].strip(), "app": m[2]})
    return list(ventanas.values())


def cerrar_ventanas(ventanas: list[dict]) -> str | None:
    """
    Le pide a KWin que cierre las ventanas. La accion 1 del buscador de ventanas es
    "cerrar": la misma peticion que manda la X de la barra de titulo. Devuelve un error
    o None si salio bien.
    """
    for v in ventanas:
        r = _busctl("org.kde.KWin", "/WindowsRunner", "org.kde.krunner1", "Run",
                    "ss", f"1_{v['id']}", "")
        if r is None:
            return f"No pude pedirle a KWin que cierre '{v['titulo']}'."
    return None


def _pids_del_programa(nombres: set[str]) -> list[int]:
    """
    Procesos cuyo nombre coincide con alguno de 'nombres', sin tocar nunca los
    intocables ni al propio Nox.
    """
    yo = {os.getpid(), os.getppid()}
    pids = []
    for p in _procesos_propios():
        if p["pid"] in yo:
            continue
        propios = {_normalizar(p["comm"]), _normalizar(p["exe"])} - {""}
        if any(seguridad.es_intocable(x) for x in propios):
            continue
        for n in nombres:
            # Igual, o el nombre recortado a 15 caracteres por el kernel.
            if any(x == n or (len(x) == 15 and n.startswith(x)) for x in propios):
                pids.append(p["pid"])
                break
    return pids


def cerrar_a_la_fuerza(ventanas: list[dict], nombres: set[str]) -> tuple[int, int]:
    """
    Termina los procesos que se llamen como alguno de 'nombres': SIGTERM primero y, si
    a los 3 segundos siguen vivos, SIGKILL. Devuelve (procesos, los que hubo que matar);
    (0, 0) si no se identifico ninguno.
    """
    pids = _pids_del_programa(nombres)
    if not pids:
        return 0, 0

    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)  # primero el pedido amable a nivel de proceso
        except OSError:
            pass
    limite = time.time() + 3
    while time.time() < limite and any(Path(f"/proc/{p}").exists() for p in pids):
        time.sleep(0.2)
    rebeldes = [p for p in pids if Path(f"/proc/{p}").exists()]
    for pid in rebeldes:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    return len(pids), len(rebeldes)


# --- Deteccion de juegos en curso ---

def juego_corriendo(catalogo: dict) -> str | None:
    """
    Nombre del juego en curso, o None.

    - Steam (nativos y Proton) lanza cada juego bajo un proceso "reaper" con
      "SteamLaunch AppId=<id>" en sus argumentos. Es la señal mas fiable.
    - Lo de afuera de Steam (Heroic, Lutris, Faugus) corre con Wine, que siempre
      levanta un "wineserver".
    Se ignora Wallpaper Engine, que tambien corre por Steam con Proton.
    """
    juegos_por_appid = {}
    for datos in catalogo.values():
        m = re.fullmatch(r"steam://rungameid/(\d+)", datos.get("destino", ""))
        if m:
            juegos_por_appid[m.group(1)] = datos["nombre"]

    excluidos = escanear_programas.APPS_STEAM_QUE_NO_SON_JUEGOS
    encontrado = None
    hay_wine = False

    for p in _procesos_propios():
        if p["comm"] == "reaper":
            m = re.search(r"SteamLaunch AppId=(\d+)", " ".join(p["args"]))
            if m and m.group(1) not in excluidos:
                encontrado = juegos_por_appid.get(m.group(1), f"un juego de Steam (id {m.group(1)})")
                break
        elif p["comm"] == "wineserver" and not hay_wine:
            try:
                entorno = Path(f"/proc/{p['pid']}/environ").read_bytes().decode(errors="ignore")
            except OSError:
                continue
            prefijo = next(
                (v for v in entorno.split("\0") if v.startswith("WINEPREFIX=")), ""
            )
            if not any(f"/compatdata/{e}/" in prefijo for e in excluidos):
                hay_wine = True

    if encontrado is None and hay_wine:
        encontrado = "un juego de Windows (Wine/Proton)"
    return encontrado


# --- Volumen y multimedia ---

# Se disparan los mismos atajos globales que las teclas multimedia del teclado, a
# traves de kglobalaccel (el gestor de atajos de KDE). Asi se comporta exactamente
# igual que apretar la tecla: Plasma elige que reproductor controlar (YouTube Music en
# Brave incluido) y muestra el indicador de volumen en pantalla.
ATAJOS_KDE = {
    "subir_volumen": ("kmix", "increase_volume"),
    "bajar_volumen": ("kmix", "decrease_volume"),
    "silenciar": ("kmix", "mute"),
    "reproducir_pausar": ("mediacontrol", "playpausemedia"),
    "siguiente": ("mediacontrol", "nextmedia"),
    "anterior": ("mediacontrol", "previousmedia"),
}
ACCIONES_MULTIMEDIA = tuple(ATAJOS_KDE)

# Respaldo si Plasma no responde (o no es KDE): PipeWire directo para el volumen (5% por
# paso, sin pasar de 100%) y playerctl para la reproduccion, si esta instalado.
RESPALDO_MULTIMEDIA = {
    "subir_volumen": ["wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", "5%+"],
    "bajar_volumen": ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%-"],
    "silenciar": ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"],
    "reproducir_pausar": ["playerctl", "play-pause"],
    "siguiente": ["playerctl", "next"],
    "anterior": ["playerctl", "previous"],
}


def _atajo_kde(componente: str, atajo: str) -> bool:
    r = _busctl("org.kde.kglobalaccel", f"/component/{componente}",
                "org.kde.kglobalaccel.Component", "invokeShortcut", "s", atajo)
    return r is not None


def tecla_multimedia(accion: str, repeticiones: int) -> str | None:
    componente, atajo = ATAJOS_KDE[accion]

    for i in range(repeticiones):
        if _atajo_kde(componente, atajo):
            time.sleep(0.05)  # que Plasma registre cada paso por separado
            continue
        # Plasma no respondio: el respaldo para lo que falte.
        comando = RESPALDO_MULTIMEDIA[accion]
        if shutil.which(comando[0]) is None:
            return f"No pude: Plasma no respondio y no esta instalado {comando[0]}."
        try:
            for _ in range(repeticiones - i):
                subprocess.run(comando, capture_output=True, timeout=5)
        except subprocess.SubprocessError as e:
            return f"No pude: {e}"
        break
    return None


# --- Consultas del sistema (solo lectura) ---

def ejecutar_consulta(comando: str) -> str:
    """
    Ejecuta un comando de consulta. La validacion vive en seguridad.py: lista blanca de
    programas, opciones peligrosas revisadas una por una, y rutas sensibles bloqueadas.

    No hay shell de por medio: cada tramo del pipeline es un proceso aparte y la salida
    de uno se le pasa como entrada al siguiente.
    """
    try:
        tramos = seguridad.validar_consulta_linux(comando)
    except Rechazado as e:
        return str(e)

    # Sin paginadores ni colores: la salida la lee el modelo, no una terminal.
    entorno = {**os.environ, "PAGER": "cat", "SYSTEMD_PAGER": "", "SYSTEMD_COLORS": "0"}
    entrada = None
    error = b""
    limite = time.time() + 30

    try:
        for argv in tramos:
            r = subprocess.run(
                argv, input=entrada, capture_output=True, cwd=Path.home(), env=entorno,
                stdin=None if entrada is not None else subprocess.DEVNULL,
                timeout=max(1.0, limite - time.time()),
            )
            entrada, error = r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return "El comando tardo mas de 30 segundos."
    except OSError as e:
        return f"No pude ejecutarlo: {e}"

    salida = (entrada or b"").decode(errors="ignore").strip() \
        or error.decode(errors="ignore").strip()
    return salida[:3000] if salida else "(sin salida)"
