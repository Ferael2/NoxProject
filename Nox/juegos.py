"""
Contexto de juegos: horas jugadas, cuando jugaste por ultima vez, que hay instalado.

Sale todo de archivos locales de Steam (localconfig.vdf), sin API key ni cuenta.
Se combina con el catalogo de programas para saber cuales estan instalados de verdad.

Esta PC es "full juegos y chilling", asi que esto es contexto de primera clase para
Nox: puede recomendar que jugar sabiendo lo que a Brian le gusta (de la boveda), lo
que tiene instalado, y hace cuanto que no lo toca.
"""
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import escanear_programas
import sistema

if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

_cache = None


def _ruta_localconfig() -> Path | None:
    """Encuentra el localconfig.vdf del usuario de Steam (tiene los tiempos de juego)."""
    steam = escanear_programas.ruta_steam()
    if steam is None:
        return None

    userdata = Path(steam) / "userdata"
    if not userdata.exists():
        return None

    # Si hay varias cuentas, la del config mas grande suele ser la principal.
    candidatos = [
        p / "config" / "localconfig.vdf"
        for p in userdata.iterdir()
        if p.is_dir() and (p / "config" / "localconfig.vdf").exists()
    ]
    if not candidatos:
        return None
    return max(candidatos, key=lambda p: p.stat().st_size)


def _nombres_instalados() -> dict[str, str]:
    """{appid: nombre} de los juegos que estan instalados, segun el catalogo."""
    nombres = {}
    for datos in sistema.cargar_catalogo().values():
        destino = datos.get("destino", "")
        m = re.fullmatch(r"steam://rungameid/(\d+)", destino)
        if m and datos.get("tipo") == "juego":  # Wallpaper Engine tambien va por Steam
            nombres[m.group(1)] = datos["nombre"]
    return nombres


def cargar(refrescar: bool = False) -> list[dict]:
    """
    Devuelve la lista de juegos con horas jugadas, ordenada de mas a menos.
    Solo incluye los que tienen tiempo registrado.
    """
    global _cache
    if _cache is not None and not refrescar:
        return _cache

    cfg = _ruta_localconfig()
    if cfg is None:
        _cache = []
        return _cache

    texto = cfg.read_text(encoding="utf-8", errors="ignore")

    # Recortar a la seccion "apps" para no confundirse con otras partes del archivo.
    inicio = texto.find('"apps"')
    seccion = texto[inicio:] if inicio != -1 else texto

    instalados = _nombres_instalados()
    ahora = datetime.now()
    juegos = []

    # Cada bloque: "appid" { ... "Playtime" "minutos" ... }
    patron = re.compile(
        r'"(\d+)"\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*?)\}', re.DOTALL
    )
    for m in patron.finditer(seccion):
        appid, cuerpo = m.group(1), m.group(2)

        minutos = re.search(r'"Playtime"\s*"(\d+)"', cuerpo)
        if not minutos or int(minutos.group(1)) == 0:
            continue

        ultima = re.search(r'"LastPlayed"\s*"(\d+)"', cuerpo)
        ts = int(ultima.group(1)) if ultima else 0
        fecha = datetime.fromtimestamp(ts) if ts else None

        juegos.append({
            "appid": appid,
            "nombre": instalados.get(appid, f"(desinstalado, id {appid})"),
            "instalado": appid in instalados,
            "horas": round(int(minutos.group(1)) / 60, 1),
            "ultima_vez": fecha,
            "dias_sin_jugar": (ahora - fecha).days if fecha else None,
        })

    juegos.sort(key=lambda j: -j["horas"])
    _cache = juegos
    return _cache


def _describir_cuando(dias: int | None) -> str:
    if dias is None:
        return "nunca registrado"
    if dias == 0:
        return "hoy"
    if dias == 1:
        return "ayer"
    if dias < 7:
        return f"hace {dias} dias"
    if dias < 31:
        return f"hace {dias // 7} semana(s)"
    if dias < 365:
        return f"hace {dias // 30} mes(es)"
    return f"hace {dias // 365} año(s)"


def resumen(solo_instalados: bool = True, limite: int = 25) -> str:
    """Texto con las horas y la ultima vez que jugo cada juego."""
    juegos = cargar()
    if not juegos:
        return "No pude leer los datos de Steam."

    if solo_instalados:
        juegos = [j for j in juegos if j["instalado"]]
    if not juegos:
        return "No hay juegos instalados con tiempo registrado."

    lineas = [
        f"{j['nombre']}: {j['horas']}h, ultima vez {_describir_cuando(j['dias_sin_jugar'])}"
        for j in juegos[:limite]
    ]
    total = sum(j["horas"] for j in juegos)
    return "\n".join(lineas) + f"\n\n(Total: {round(total)}h en {len(juegos)} juegos instalados)"


def abandonados(dias_minimos: int = 60, horas_minimas: float = 5) -> str:
    """Juegos que le gustaron (tienen horas) pero hace rato que no toca."""
    juegos = [
        j for j in cargar()
        if j["instalado"]
        and j["horas"] >= horas_minimas
        and (j["dias_sin_jugar"] or 0) >= dias_minimos
    ]
    if not juegos:
        return "No hay juegos instalados abandonados con ese criterio."

    juegos.sort(key=lambda j: -j["horas"])
    return "\n".join(
        f"{j['nombre']}: {j['horas']}h jugadas, sin tocar {_describir_cuando(j['dias_sin_jugar'])}"
        for j in juegos[:15]
    )


def recientes(dias: int = 14) -> str:
    """En que estuvo jugando ultimamente."""
    limite = datetime.now() - timedelta(days=dias)
    juegos = [
        j for j in cargar()
        if j["ultima_vez"] and j["ultima_vez"] >= limite
    ]
    if not juegos:
        return f"No jugo nada en los ultimos {dias} dias."

    juegos.sort(key=lambda j: j["ultima_vez"], reverse=True)
    return "\n".join(
        f"{j['nombre']}: {j['horas']}h totales, jugado {_describir_cuando(j['dias_sin_jugar'])}"
        for j in juegos
    )
