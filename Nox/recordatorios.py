"""
Recordatorios y rutinas: lo que permite que Nox te AVISE sin que lo llames.

Hay dos cosas:

  - Recordatorios: "recuérdame llamar a mamá en 20 minutos" / "mañana a las 9". Se guardan en un
    archivo (recordatorios.json, en la carpeta de trabajo de Nox) y la ventana principal revisa
    cada pocos segundos si alguno ya toca. Sobreviven a cerrar Nox: si estaba cerrado cuando
    tocaba, avisa al abrirlo.
  - El saludo de la mañana: la primera vez que abres Nox cada día, un resumen corto con la fecha y
    lo que tienes pendiente hoy. Es OPCIONAL y viene apagado: Nox no empieza a hablarte solo hasta
    que lo activas en Ajustes.

Reglas para no ser molesto ni peligroso:
  - Nada se programa que no hayas pedido tú (o activado tú): no hay avisos "por iniciativa del
    modelo".
  - Mientras juegas, los avisos esperan (se entregan al terminar), igual que Nox cede la tarjeta
    de video.
  - Un tope de recordatorios pendientes y de largo de texto, para que un error no llene el archivo.
  - Esto no ejecuta nada: solo muestra y dice un texto. Nunca abre programas ni toca archivos.
"""
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import config

MAX_PENDIENTES = 50
MAX_TEXTO = 200
MAX_DIAS_ADELANTE = 365
REPETICIONES = ("", "diario", "semanal")

DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre")


class RecordatorioInvalido(ValueError):
    """Algo no se puede programar. El mensaje esta escrito para mostrarselo a la persona."""


def archivo() -> Path:
    return config.CARPETA_TRABAJO / "recordatorios.json"


def archivo_estado() -> Path:
    return config.CARPETA_TRABAJO / "rutinas.json"


# --- Fechas en español, sin depender del idioma del sistema ---

def fecha_larga(dt: datetime) -> str:
    """'martes 20 de octubre de 2026'"""
    return f"{DIAS[dt.weekday()]} {dt.day} de {MESES[dt.month - 1]} de {dt.year}"


def ahora_texto(dt: datetime | None = None) -> str:
    """'martes 20 de octubre de 2026, 22:45'. Es lo que se le dice al modelo en cada turno."""
    dt = dt or datetime.now()
    return f"{fecha_larga(dt)}, {dt:%H:%M}"


def describir_cuando(dt: datetime, ahora: datetime | None = None) -> str:
    """'hoy a las 18:30', 'mañana a las 9:00', 'el viernes 23 de octubre a las 18:30'."""
    ahora = ahora or datetime.now()
    hora = f"{dt.hour}:{dt:%M}"
    dias = (dt.date() - ahora.date()).days
    if dias == 0:
        return f"hoy a las {hora}"
    if dias == 1:
        return f"mañana a las {hora}"
    if 1 < dias < 7:
        return f"el {DIAS[dt.weekday()]} a las {hora}"
    return f"el {DIAS[dt.weekday()]} {dt.day} de {MESES[dt.month - 1]} a las {hora}"


# --- Guardar y leer ---

def _leer() -> list[dict]:
    try:
        datos = json.loads(archivo().read_text(encoding="utf-8"))
        return [r for r in datos if isinstance(r, dict) and {"id", "texto", "cuando"} <= set(r)]
    except (OSError, ValueError, TypeError):
        return []


def _escribir(recordatorios: list[dict]):
    destino = archivo()
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=destino.parent, prefix=destino.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(recordatorios, f, ensure_ascii=False, indent=1)
        os.replace(tmp, destino)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _momento(texto: str) -> datetime:
    return datetime.fromisoformat(texto)


def crear(texto: str, en_minutos: int | None = None, fecha_iso: str | None = None,
          repetir: str = "", ahora: datetime | None = None) -> dict:
    """
    Programa un recordatorio. Se da UNA de las dos formas de decir cuando:
      en_minutos  cuantos minutos desde ahora (1 a 525600)
      fecha_iso   'AAAA-MM-DDTHH:MM' (hora local)
    Lanza RecordatorioInvalido con un mensaje claro si algo no cuadra.
    """
    ahora = ahora or datetime.now()
    texto = " ".join(str(texto or "").split())
    if not texto:
        raise RecordatorioInvalido("¿Qué quieres que te recuerde?")
    if len(texto) > MAX_TEXTO:
        raise RecordatorioInvalido(f"Es demasiado largo (máximo {MAX_TEXTO} caracteres).")
    if repetir not in REPETICIONES:
        raise RecordatorioInvalido(f"Solo se repite 'diario' o 'semanal', no {repetir!r}.")

    if (en_minutos is None) == (not fecha_iso):
        raise RecordatorioInvalido("Dime cuándo: en cuántos minutos, o una fecha y hora.")
    if en_minutos is not None:
        try:
            minutos = int(en_minutos)
        except (TypeError, ValueError):
            raise RecordatorioInvalido("Los minutos deben ser un número.")
        if not 1 <= minutos <= MAX_DIAS_ADELANTE * 24 * 60:
            raise RecordatorioInvalido("Los minutos deben estar entre 1 y un año.")
        cuando = (ahora + timedelta(minutes=minutos)).replace(second=0, microsecond=0)
    else:
        try:
            cuando = datetime.fromisoformat(str(fecha_iso).strip().replace(" ", "T"))
        except ValueError:
            raise RecordatorioInvalido(f"No entiendo la fecha {fecha_iso!r}. Debe ser AAAA-MM-DDTHH:MM.")
        if cuando.tzinfo is not None:
            cuando = cuando.astimezone().replace(tzinfo=None)
        if cuando < ahora - timedelta(minutes=1):
            raise RecordatorioInvalido(f"Esa hora ya pasó ({describir_cuando(cuando, ahora)}).")
        if cuando > ahora + timedelta(days=MAX_DIAS_ADELANTE):
            raise RecordatorioInvalido("Solo programo hasta un año hacia adelante.")

    existentes = _leer()
    if len([r for r in existentes if not r.get("avisado")]) >= MAX_PENDIENTES:
        raise RecordatorioInvalido(f"Ya hay {MAX_PENDIENTES} recordatorios pendientes. Cancela alguno antes.")

    nuevo = {"id": max([r["id"] for r in existentes], default=0) + 1, "texto": texto,
             "cuando": cuando.isoformat(timespec="minutes"), "repetir": repetir,
             "creado": ahora.isoformat(timespec="seconds"), "avisado": False}
    existentes.append(nuevo)
    _escribir(existentes)
    return nuevo


def listar(pendientes: bool = True) -> list[dict]:
    """Los recordatorios, del mas proximo al mas lejano."""
    rs = [r for r in _leer() if not (pendientes and r.get("avisado"))]
    return sorted(rs, key=lambda r: r["cuando"])


def cancelar(id_recordatorio: int) -> dict | None:
    """Borra un recordatorio. Devuelve el que se cancelo, o None si no existia."""
    todos = _leer()
    quedan = [r for r in todos if r["id"] != id_recordatorio]
    if len(quedan) == len(todos):
        return None
    _escribir(quedan)
    return next(r for r in todos if r["id"] == id_recordatorio)


def vencidos(ahora: datetime | None = None) -> list[dict]:
    """Los pendientes que ya tocan (o se pasaron mientras Nox estaba cerrado)."""
    ahora = ahora or datetime.now()
    return [r for r in listar() if _momento(r["cuando"]) <= ahora]


def marcar_avisado(id_recordatorio: int, ahora: datetime | None = None):
    """
    Da por entregado un recordatorio. Los que se repiten se reprograman para la proxima vez
    (saltando las que se pasaron mientras Nox estaba cerrado); los demas quedan como avisados.
    """
    ahora = ahora or datetime.now()
    todos = _leer()
    for r in todos:
        if r["id"] != id_recordatorio:
            continue
        paso = {"diario": timedelta(days=1), "semanal": timedelta(days=7)}.get(r.get("repetir", ""))
        if paso:
            cuando = _momento(r["cuando"])
            while cuando <= ahora:
                cuando += paso
            r["cuando"] = cuando.isoformat(timespec="minutes")
        else:
            r["avisado"] = True
    _escribir(todos)


def de_hoy(ahora: datetime | None = None) -> list[dict]:
    ahora = ahora or datetime.now()
    return [r for r in listar() if _momento(r["cuando"]).date() == ahora.date()]


def describir(r: dict, ahora: datetime | None = None) -> str:
    rep = f" (se repite {r['repetir']})" if r.get("repetir") else ""
    return f"#{r['id']} {r['texto']} — {describir_cuando(_momento(r['cuando']), ahora)}{rep}"


# --- El saludo de la manana ---

def _estado() -> dict:
    try:
        return json.loads(archivo_estado().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def saludo_matutino(ahora: datetime | None = None, marcar: bool = True) -> str | None:
    """
    El resumen de la mañana, o None si no toca: esta apagado, ya se dio hoy, o no es de mañana
    (de 5:00 a 12:00). Deterministico y sin internet: la fecha y lo que tienes pendiente hoy.
    """
    if not getattr(config, "SALUDO_MATUTINO", False):
        return None
    ahora = ahora or datetime.now()
    if not 5 <= ahora.hour < 12:
        return None
    estado = _estado()
    if estado.get("ultimo_saludo") == ahora.date().isoformat():
        return None

    lineas = [f"Buenos días, {config.USUARIO}. Hoy es {fecha_larga(ahora)}."]
    hoy = de_hoy(ahora)
    if hoy:
        lineas.append("Para hoy tienes: " + "; ".join(
            f"{r['texto']} ({_momento(r['cuando']).hour}:{_momento(r['cuando']):%M})" for r in hoy) + ".")
    else:
        lineas.append("No tienes recordatorios para hoy.")
    if marcar:
        estado["ultimo_saludo"] = ahora.date().isoformat()
        try:
            archivo_estado().parent.mkdir(parents=True, exist_ok=True)
            archivo_estado().write_text(json.dumps(estado), encoding="utf-8")
        except OSError:
            pass
    return " ".join(lineas)
