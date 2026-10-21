"""
Configura Nox para quien lo va a usar: como llamarlo, que tipo de equipo es y, si tiene,
donde esta su boveda.

    python configurar.py

Lo corre el instalador, y se puede volver a correr cuando se quiera cambiar algo. Guarda
las respuestas en config_local.json (junto a este archivo) sin borrar lo que ya hubiera.
Apretar Enter deja cada valor como estaba.
"""
import json
import sys
from pathlib import Path

ARCHIVO = Path(__file__).resolve().parent / "config_local.json"


def preguntar(texto: str, actual: str = "") -> str:
    sufijo = f" [{actual}]" if actual else ""
    try:
        respuesta = input(f"{texto}{sufijo}: ").strip()
    except EOFError:  # sin teclado (instalacion automatica): se deja todo como esta
        return actual
    return respuesta or actual


def main() -> int:
    try:
        ajustes = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ajustes = {}

    print("=== Configurar Nox ===")
    ajustes["usuario"] = preguntar("¿Cómo quieres que te llame Nox?", ajustes.get("usuario", ""))

    print("\nSi usas una bóveda de Obsidian, escribe su ruta (es opcional, Enter para omitir).")
    boveda = preguntar("Ruta de la bóveda", ajustes.get("boveda", ""))
    if boveda and not Path(boveda).expanduser().is_dir():
        print(f"  Aviso: {boveda} no existe todavía. Se guarda igual; puedes corregirla en {ARCHIVO.name}.")
    ajustes["boveda"] = boveda

    import config  # los perfiles viven en config.py, para no repetirlos aqui
    print("\nTipo de equipo (define el modelo de IA y la voz que se usan):")
    nombres = list(config.PERFILES_EQUIPO)
    for i, nombre in enumerate(nombres, 1):
        print(f"  {i}) {nombre}: {config.PERFILES_EQUIPO[nombre]['descripcion']}")
    actual = ajustes.get("equipo", config.EQUIPO_POR_DEFECTO)
    eleccion = preguntar("Número o nombre", actual)
    if eleccion.isdigit() and 1 <= int(eleccion) <= len(nombres):
        eleccion = nombres[int(eleccion) - 1]
    if eleccion in config.PERFILES_EQUIPO:
        ajustes["equipo"] = eleccion
    else:
        print(f"  '{eleccion}' no es un perfil; se deja '{actual}'.")
        ajustes["equipo"] = actual

    # Lo vacio no se guarda: config.py ya sabe que hacer cuando falta.
    ajustes = {k: v for k, v in ajustes.items() if v}
    ARCHIVO.write_text(json.dumps(ajustes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nGuardado en {ARCHIVO.name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
