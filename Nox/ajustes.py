"""
Los ajustes de Nox, para leerlos y guardarlos desde la interfaz.

Antes, elegir el perfil de equipo, el nombre o el tono obligaba a editar config_local.json a
mano. Ahora la ventana de Ajustes (y el asistente de bienvenida) usan este modulo: valida lo
que escribe la persona, guarda el archivo de forma segura y le avisa a config.py para que
aplique los cambios al momento.

Que vive aca y que no:
  - config_local.json  → ajustes de la persona (nombre, tono, equipo, voz...). El .exe de
                         Windows los guarda en AppData; tambien lee el archivo antiguo junto
                         al ejecutable si aun no existe el de AppData.
  - openrouter.key     → la clave de la nube. Un archivo aparte, nunca dentro de los ajustes.
  - mcp_servidores.json → herramientas externas. Lo gestiona mcp_cliente.py.
"""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import config
import plataforma

ARCHIVO = config.archivo_ajustes()

WHISPER_MODELOS = ("tiny", "base", "small", "medium", "large-v3")
WHISPER_DISPOSITIVOS = ("cpu", "cuda")

LIMITES_TEXTO = {"usuario": 60, "estilo": 600, "perfil": 2500, "boveda": 400, "modelo_chat": 80, "modelo_vision": 80}


class AjusteInvalido(ValueError):
    """Un valor que no se puede guardar. El mensaje esta escrito para mostrarselo a la persona."""


# --- Leer y validar ---

def _archivo_para_leer() -> Path:
    """Usa el archivo persistente y, si falta, lee los ajustes antiguos junto al programa."""
    if ARCHIVO.exists():
        return ARCHIVO
    anterior = config.PROYECTO / "config_local.json"
    if anterior != ARCHIVO and anterior.exists():
        return anterior
    return ARCHIVO


def cargar() -> dict:
    """Lo que hay guardado ahora (vacio si no hay archivo o esta roto)."""
    try:
        datos = json.loads(_archivo_para_leer().read_text(encoding="utf-8"))
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        return {}


def _texto(clave: str, valor) -> str:
    """Texto limpio: sin caracteres de control (salvo saltos de linea) y con largo acotado."""
    limpio = re.sub(r"[^\S\n]+", " ", str(valor or "")).strip()
    limpio = "".join(c for c in limpio if c == "\n" or c.isprintable())
    if clave == "usuario":
        limpio = limpio.replace("\n", " ")
    if len(limpio) > LIMITES_TEXTO[clave]:
        raise AjusteInvalido(f"'{clave}' es demasiado largo (maximo {LIMITES_TEXTO[clave]} caracteres).")
    return limpio


def validar(cambios: dict) -> dict:
    """
    Revisa y limpia los cambios. Devuelve un dict con las mismas claves, ya normalizadas, o
    lanza AjusteInvalido. Las claves desconocidas se rechazan: asi un error de tipeo en la
    interfaz no se guarda en silencio.
    """
    limpio = {}
    for clave, valor in cambios.items():
        if clave in ("usuario", "estilo", "perfil", "boveda"):
            limpio[clave] = _texto(clave, valor)
        elif clave in ("modelo_chat", "modelo_vision"):
            from modelos import nombre_valido
            texto = _texto(clave, valor)
            if texto and not nombre_valido(texto):
                raise AjusteInvalido(f"'{texto}' no parece un nombre de modelo (ej. qwen3:8b).")
            limpio[clave] = texto
        elif clave == "trato":
            if valor not in config.TRATOS:
                raise AjusteInvalido(f"Trato desconocido: {valor!r}.")
            limpio[clave] = valor
        elif clave == "tono":
            if valor not in config.TONOS:
                raise AjusteInvalido(f"Tono desconocido: {valor!r}.")
            limpio[clave] = valor
        elif clave == "equipo":
            if valor not in config.PERFILES_EQUIPO:
                raise AjusteInvalido(f"Perfil de equipo desconocido: {valor!r}.")
            limpio[clave] = valor
        elif clave in ("modelo_whisper", "modelo_whisper_escucha"):
            if valor and valor not in WHISPER_MODELOS:
                raise AjusteInvalido(f"Modelo de voz desconocido: {valor!r}.")
            limpio[clave] = valor or ""
        elif clave == "whisper_device":
            if valor and valor not in WHISPER_DISPOSITIVOS:
                raise AjusteInvalido("El dispositivo de voz debe ser 'cpu' o 'cuda'.")
            limpio[clave] = valor or ""
        elif clave == "velocidad_voz":
            try:
                v = float(valor)
            except (TypeError, ValueError):
                raise AjusteInvalido("La velocidad de la voz debe ser un numero.")
            if not 0.5 <= v <= 2.0:
                raise AjusteInvalido("La velocidad de la voz debe estar entre 0.5 y 2.0.")
            limpio[clave] = round(v, 2)
        elif clave in ("usar_nube", "usar_vad", "voz_activa", "ceder_gpu_al_jugar", "bienvenida_hecha",
                       "avisar_recordatorios", "avisos_en_voz", "saludo_matutino", "memoria_resumen_sesion", "vista_activa", "vista_preguntar"):
            limpio[clave] = bool(valor)
        else:
            raise AjusteInvalido(f"Ajuste desconocido: {clave!r}.")
    return limpio


# --- Guardar ---

def _escribir_atomico(ruta: Path, contenido: str, privado: bool = False):
    """Escribe a un archivo temporal y lo renombra: nunca queda a medio escribir."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix=ruta.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(contenido)
        if privado and not plataforma.ES_WINDOWS:
            os.chmod(tmp, 0o600)
        os.replace(tmp, ruta)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# Lo que se guarda vacio es lo mismo que no estar: asi el perfil de equipo vuelve a mandar.
_VACIOS_SE_BORRAN = ("usuario", "estilo", "perfil", "boveda", "modelo_chat", "modelo_vision",
                     "modelo_whisper", "modelo_whisper_escucha", "whisper_device")


def guardar(cambios: dict, aplicar: bool = True) -> dict:
    """
    Valida los cambios, los mezcla con lo que ya habia y los guarda. Con 'aplicar', config.py
    los toma al momento. Devuelve lo guardado. Lanza AjusteInvalido si algo no sirve (y en ese
    caso no se guarda NADA).
    """
    nuevos = validar(cambios)
    actuales = cargar()
    actuales.update(nuevos)
    for clave in _VACIOS_SE_BORRAN:
        if actuales.get(clave) == "":
            actuales.pop(clave)
    _escribir_atomico(ARCHIVO, json.dumps(actuales, ensure_ascii=False, indent=2) + "\n")
    if aplicar:
        config.recargar()
    return actuales


def necesita_bienvenida() -> bool:
    """True la primera vez: cuando nadie ha pasado por el asistente de bienvenida."""
    return not cargar().get("bienvenida_hecha")


# --- La clave de la nube ---

def _archivo_key() -> Path:
    import nube
    return nube.ARCHIVO_KEY


def hay_key() -> bool:
    import nube
    return nube.leer_key() is not None


def guardar_key(clave: str):
    """Guarda la clave de OpenRouter en su archivo (solo lectura para el dueño en Linux)."""
    clave = (clave or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-]{16,200}", clave):
        raise AjusteInvalido("Esa clave no parece valida: son letras, numeros, - y _, sin espacios.")
    _escribir_atomico(_archivo_key(), clave + "\n", privado=True)
    import nube
    nube._key = None  # que la proxima consulta la vuelva a leer


def borrar_key():
    try:
        _archivo_key().unlink()
    except FileNotFoundError:
        pass
    import nube
    nube._key = None


# --- Detectar el equipo ---

def _ejecutar(comando: list[str]) -> str:
    try:
        r = subprocess.run(comando, capture_output=True, text=True, timeout=8,
                           **plataforma.kwargs_sin_ventana())
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _gpu_nvidia() -> tuple[str, float] | None:
    salida = _ejecutar(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
    for linea in salida.strip().splitlines():
        nombre, _, mib = linea.rpartition(",")
        try:
            return nombre.strip(), round(float(mib) / 1024, 1)
        except ValueError:
            continue
    return None


def _gpu_amd_linux() -> tuple[str, float] | None:
    for tarjeta in sorted(Path("/sys/class/drm").glob("card[0-9]")):
        dispositivo = tarjeta / "device"
        try:
            if (dispositivo / "vendor").read_text().strip() != "0x1002":
                continue
            vram = int((dispositivo / "mem_info_vram_total").read_text())
        except (OSError, ValueError):
            continue
        nombre = "AMD Radeon"
        for linea in _ejecutar(["lspci", "-mm"]).splitlines():
            if "VGA" in linea and "AMD" in linea:
                # Formato: slot "clase" "fabricante" "dispositivo" ... -> el 3er campo entre comillas
                partes = linea.split('"')[1::2]
                if len(partes) >= 3:
                    entre_corchetes = re.findall(r"\[([^\]]+)\]", partes[2])
                    nombre = (entre_corchetes[-1] if entre_corchetes else partes[2]).strip()
                break
        return nombre, round(vram / 1024 ** 3, 1)
    return None


def _gpu_windows() -> tuple[str, float | None] | None:
    salida = _ejecutar(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        "Get-CimInstance Win32_VideoController | Select-Object -First 1 -ExpandProperty Name"])
    nombre = salida.strip().splitlines()[0].strip() if salida.strip() else ""
    return (nombre, None) if nombre else None


def detectar_equipo() -> dict:
    """
    Mira la tarjeta de video y la RAM y sugiere un perfil de equipo. Es una SUGERENCIA: la
    persona decide. Devuelve {gpu, vram_gb, ram_gb, sugerido, motivo}.
    """
    gpu = _gpu_nvidia()
    if gpu is None and not plataforma.ES_WINDOWS:
        gpu = _gpu_amd_linux()
    if gpu is None and plataforma.ES_WINDOWS:
        gpu = _gpu_windows()
    nombre, vram = gpu if gpu else (None, None)
    ram = plataforma.memoria_ram_gb()

    if vram is not None and vram < 5:
        sugerido = "basico"
        motivo = f"Con {vram} GB de memoria de video, el modelo de 8B no cabe entero."
    elif vram is None and (ram is not None and ram < 12):
        sugerido = "basico"
        motivo = "No encontre una tarjeta de video dedicada y tienes poca RAM."
    elif nombre and "4060" in nombre and vram and vram >= 7:
        sugerido = "laptop_rtx4060"
        motivo = f"Con {vram} GB de memoria de video, esta tarjeta tiene perfil propio."
    elif vram is None:
        sugerido = "estandar_8gb"
        motivo = "No pude leer la memoria de video; propongo el perfil estandar."
    else:
        sugerido = "estandar_8gb"
        motivo = f"Con {vram} GB de memoria de video, el perfil estándar es el adecuado."
    return {"gpu": nombre, "vram_gb": vram, "ram_gb": ram, "sugerido": sugerido, "motivo": motivo}
