"""
Vocabulario para que Whisper entienda mejor.

Whisper acepta un `initial_prompt` que sesga la transcripcion hacia ciertas palabras.
Sin eso, "Phasmophobia" sale como "fasmofobia", "Baldur's Gate" como "balders geit" y
"Nox" como "nos". Con las palabras adelante, acierta.

El vocabulario se arma solo de lo que Brian realmente tiene: sus juegos instalados, sus
programas, los temas de su boveda y sus proyectos. Asi no hay que mantener una lista a
mano, y crece con el.
"""
import re
import sys
from pathlib import Path

import config

if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

_cache = None          # (momento, texto)
VIDA_CACHE = 30        # segundos: lo que tienes abierto cambia

# Palabras que Nox escucha seguido y no salen de ningun catalogo.
BASE = [
    "Nox", "Obsidian", "Ollama", "OpenRouter", "Steam", "Discord", "Spotify",
    "YouTube", "WhatsApp", "Brave", "Chrome", "Windows", "Python", "Java",
    "bóveda",
]


# Entradas del menu que casi nadie dice en voz alta: herramientas de mantenimiento, de desarrollo
# interno del sistema y nombres de iconos. Ocupan el poco espacio que tiene el prompt.
_RUIDO = re.compile(
    r"assistant|console|shell\b|designer|linguist|hello|instalar|restore|lstopo|chuleta|update|openjdk|"
    r"kvantum|^qt |cachy|btrfs|limine|hardware locality|^utilities-|^accessories-|^applications-|^preferences-|^system-",
    re.I)


def _util(nombre: str) -> bool:
    return bool(nombre) and not _RUIDO.search(nombre)


def _de_programas(limite: int = 60) -> list[str]:
    """
    Nombres de juegos y programas, en el orden en que importan para el oido de Whisper:
    primero lo que MAS usas (se aprende de lo que abres y cierras), despues lo que tienes
    abierto AHORA (es lo que probablemente vas a nombrar), despues los juegos y al final el
    resto. El prompt de Whisper tiene poco espacio: si el nombre que mas dices (ej. "Vesktop")
    queda al fondo de una lista alfabetica, se corta y Whisper escribe "desktop".
    """
    try:
        import sistema
        catalogo = sistema.cargar_catalogo()
    except Exception:
        return []

    frecuentes = sistema.programas_mas_usados(12)
    abiertos = []
    try:
        abiertos = [sistema.nombre_de_catalogo(v["app"]) for v in sistema.ventanas_abiertas()
                    if v.get("app") and not sistema.seguridad.es_intocable(sistema.seguridad.normalizar(v["app"]))]
    except Exception:
        pass
    juegos = [d["nombre"] for d in catalogo.values() if d.get("tipo") == "juego"]
    apps = [d["nombre"] for d in catalogo.values() if d.get("tipo") != "juego"]
    # Una sola entrada por familia ("LibreOffice Calc", "LibreOffice Draw"... -> "LibreOffice"):
    # siete veces la misma palabra gastan espacio que otros nombres necesitan.
    vistas, resultado = set(), []
    for n in frecuentes + abiertos + juegos + apps:
        familia = n.split()[0].lower()
        if _util(n) and familia not in vistas:
            vistas.add(familia)
            resultado.append(n.split()[0] if n.lower().startswith("libreoffice") else n)
    return resultado[:limite]


def _de_boveda(limite: int = 40) -> list[str]:
    """Titulos de las notas: dan los temas de los que Brian habla."""
    nombres = []
    for carpeta in ("Wiki",):
        base = config.BOVEDA / carpeta
        if not base.exists():
            continue
        for p in base.rglob("*.md"):
            titulo = p.stem
            # Quedarse con titulos cortos: los largos meten ruido en el prompt.
            if 3 <= len(titulo) <= 40:
                nombres.append(titulo)
    return nombres[:limite]


def construir(max_chars: int = 900) -> str:
    """
    Arma el initial_prompt para Whisper.

    Se recorta a ~900 caracteres: el prompt de Whisper compite con el audio por la
    ventana de contexto, y pasarse lo empeora en vez de mejorarlo.
    """
    global _cache
    import time
    if _cache is not None and time.time() - _cache[0] < VIDA_CACHE:
        return _cache[1]

    # Primero lo que mas pesa para el oido: lo que usas y tienes abierto; despues lo fijo.
    palabras = _de_programas(20) + BASE + _de_programas(60) + _de_boveda()

    # Sin duplicados, respetando el orden (lo importante primero).
    vistas, unicas = set(), []
    for p in palabras:
        clave = p.lower()
        if clave not in vistas:
            vistas.add(clave)
            unicas.append(p)

    texto = ""
    for palabra in unicas:
        candidato = f"{texto}, {palabra}" if texto else palabra
        if len(candidato) > max_chars:
            break
        texto = candidato

    resultado = f"Conversacion en español con Nox sobre: {texto}."
    _cache = (time.time(), resultado)
    return resultado


def refrescar():
    """Vuelve a armarlo (despues de instalar juegos o agregar notas)."""
    global _cache
    _cache = None
    return construir()


if __name__ == "__main__":
    v = construir()
    print(f"Vocabulario ({len(v)} caracteres):\n")
    print(v)
