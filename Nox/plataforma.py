"""
Deteccion del sistema operativo y ayudas que cambian segun donde corra Nox.

Nox funciona en Linux y en Windows. Todo lo que es distinto entre los dos esta aislado en
tres lugares, para que el resto del codigo no tenga que preguntar "¿que sistema es?":

- este archivo: lo basico (carpetas del usuario, abrir un archivo, lanzar un proceso);
- so_linux.py y so_windows.py: abrir/cerrar programas, ventanas, multimedia, consultas;
- escanear_programas.py: de donde se arma el catalogo de programas.

macOS no esta soportado: caeria en el codigo de Linux y la mitad no funcionaria.
"""
import os
import subprocess
import sys
from pathlib import Path

ES_WINDOWS = sys.platform == "win32"
ES_LINUX = sys.platform.startswith("linux")
ES_MAC = sys.platform == "darwin"

NOMBRE_SO = "Windows" if ES_WINDOWS else ("macOS" if ES_MAC else "Linux")

# Banderas de Windows para subprocess (no existen en otros sistemas, por eso a mano).
_SIN_VENTANA = 0x08000000           # CREATE_NO_WINDOW: sin consola parpadeando
_DESPRENDIDO = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

# GUID de las carpetas conocidas de Windows. Preguntarle al sistema es mas fiable que
# armar la ruta a mano: con OneDrive el Escritorio y los Documentos viven en otro lado.
_GUID_CARPETAS = {
    "DOCUMENTS": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "DESKTOP": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
}


def _carpeta_windows(clave: str) -> Path | None:
    import ctypes
    from ctypes import wintypes
    import uuid

    guid_texto = _GUID_CARPETAS.get(clave)
    if guid_texto is None:
        return None
    guid = uuid.UUID(guid_texto)
    # Estructura GUID de Windows: 4 bytes, 2, 2 y 8 bytes.
    datos = (ctypes.c_ubyte * 16).from_buffer_copy(guid.bytes_le)
    ruta = ctypes.c_wchar_p()
    try:
        resultado = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(datos), 0, wintypes.HANDLE(0), ctypes.byref(ruta)
        )
        if resultado == 0 and ruta.value:
            return Path(ruta.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(ruta)
    return None


def carpeta_usuario(clave: str, por_defecto: str) -> Path:
    """
    Carpeta personal del usuario ("DOCUMENTS" o "DESKTOP") con el nombre que le da el
    sistema, que depende del idioma (Documentos/Escritorio en español, Documents/Desktop en
    ingles). Si no se puede averiguar se usa el nombre en ingles dentro del home.
    """
    try:
        if ES_WINDOWS:
            ruta = _carpeta_windows(clave)
            if ruta:
                return ruta
        else:
            r = subprocess.run(["xdg-user-dir", clave], capture_output=True, text=True, timeout=2)
            if r.returncode == 0 and r.stdout.strip():
                return Path(r.stdout.strip())
    except (OSError, subprocess.SubprocessError, AttributeError):
        pass
    return Path.home() / por_defecto


def kwargs_sin_ventana() -> dict:
    """
    Argumentos extra de subprocess para que no aparezca una consola. En Windows, Nox
    corre con pythonw (sin consola) y cada PowerShell que lance abriria una ventana negra.
    """
    return {"creationflags": _SIN_VENTANA} if ES_WINDOWS else {}


def kwargs_desprendido() -> dict:
    """Argumentos de subprocess para que el programa lanzado siga vivo si Nox se cierra."""
    if ES_WINDOWS:
        return {"creationflags": _DESPRENDIDO, "close_fds": True}
    return {"start_new_session": True}


def lanzar(comando: list[str]):
    """Arranca un programa desprendido de Nox, sin entrada ni salida compartidas."""
    subprocess.Popen(
        comando,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        **kwargs_desprendido(),
    )


def abrir_con_predeterminado(ruta) -> None:
    """Abre un archivo con el programa que el sistema tenga asociado a su tipo."""
    if ES_WINDOWS:
        os.startfile(str(ruta))  # noqa: S606 - solo existe en Windows
    elif ES_MAC:
        lanzar(["open", str(ruta)])
    else:
        lanzar(["xdg-open", str(ruta)])


def notificar(titulo: str, texto: str) -> bool:
    """
    Una notificacion del escritorio (aparece aunque Nox este detras de otras ventanas). Solo en
    Linux, con notify-send; en otros sistemas devuelve False y Nox se limita a avisar en su
    ventana y por voz. Nunca lanza: un aviso que falla no debe romper nada.
    """
    if ES_WINDOWS or ES_MAC:
        return False
    import shutil
    ruta = shutil.which("notify-send")
    if ruta is None:
        return False
    try:
        subprocess.run([ruta, "--app-name=Nox", titulo[:80], texto[:300]], timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def memoria_ram_gb() -> float | None:
    """Memoria RAM total del equipo en GB, o None si no se pudo averiguar."""
    try:
        if ES_WINDOWS:
            import ctypes

            class Estado(ctypes.Structure):
                _fields_ = [("largo", ctypes.c_ulong), ("carga", ctypes.c_ulong),
                            ("total", ctypes.c_ulonglong), ("libre", ctypes.c_ulonglong),
                            ("pag_total", ctypes.c_ulonglong), ("pag_libre", ctypes.c_ulonglong),
                            ("virt_total", ctypes.c_ulonglong), ("virt_libre", ctypes.c_ulonglong),
                            ("ext", ctypes.c_ulonglong)]
            estado = Estado()
            estado.largo = ctypes.sizeof(Estado)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(estado))
            return round(estado.total / 1024 ** 3, 1)
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3, 1)
    except (OSError, ValueError, AttributeError):
        return None


def configurar_salida():
    """UTF-8 en la salida estandar. Con pythonw no hay consola y stdout es None."""
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8")
