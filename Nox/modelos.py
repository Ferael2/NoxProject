"""
Los modelos de Ollama vistos desde la interfaz: cuales hay, y descargar los que faltan.

Asi nadie tiene que abrir una terminal para escribir `ollama pull`: la ventana de bienvenida
y la de Ajustes usan esto, con barra de progreso.
"""
import json
import re

import requests

import config

# Nombre de modelo de Ollama: letras, numeros y ._-:/ (ej. "qwen3:8b", "usuario/modelo:tag").
_NOMBRE_VALIDO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-:/]{0,79}$")


def nombre_valido(modelo: str) -> bool:
    return bool(_NOMBRE_VALIDO.match(modelo or ""))


def ollama_activo() -> bool:
    try:
        return requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=3).ok
    except requests.RequestException:
        return False


def instalados() -> list[str]:
    """Nombres de los modelos descargados, o [] si Ollama no responde."""
    try:
        r = requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=5)
        return sorted(m["name"] for m in r.json().get("models", []))
    except (requests.RequestException, ValueError, KeyError):
        return []


def esta_instalado(modelo: str, lista: list[str] | None = None) -> bool:
    lista = instalados() if lista is None else lista
    return modelo in lista or f"{modelo}:latest" in lista


def necesarios() -> list[str]:
    """Los modelos que Nox necesita para funcionar con la configuracion actual."""
    return [config.MODELO_CHAT, config.MODELO_EMBED]


def faltantes() -> list[str]:
    lista = instalados()
    return [m for m in necesarios() if not esta_instalado(m, lista)]


def descargar(modelo: str, al_avanzar=None) -> tuple[bool, str]:
    """
    Descarga un modelo. 'al_avanzar(fraccion, texto)' recibe el progreso (0.0 a 1.0) para
    una barra. Devuelve (se_pudo, mensaje). Bloquea hasta terminar: llamarla desde un hilo.
    """
    if not nombre_valido(modelo):
        return False, f"'{modelo}' no parece un nombre de modelo valido."
    al_avanzar = al_avanzar or (lambda fraccion, texto: None)
    try:
        with requests.post(f"{config.OLLAMA_HOST}/api/pull", json={"model": modelo, "stream": True},
                           stream=True, timeout=(10, 300)) as r:
            r.raise_for_status()
            for linea in r.iter_lines():
                if not linea:
                    continue
                datos = json.loads(linea)
                if "error" in datos:
                    return False, datos["error"]
                total, hecho = datos.get("total"), datos.get("completed")
                fraccion = (hecho / total) if total and hecho is not None else 0.0
                al_avanzar(min(fraccion, 1.0), datos.get("status", ""))
                if datos.get("status") == "success":
                    return True, f"{modelo} listo."
    except (requests.RequestException, ValueError) as e:
        return False, f"No pude descargar {modelo}: {e}"
    return True, f"{modelo} listo."
