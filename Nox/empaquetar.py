"""
Arma un .zip de Nox listo para compartir, sin nada personal.

    python empaquetar.py

La carpeta de trabajo tiene cosas que NO se deben mandar a nadie:
  - openrouter.key   una clave de API real (con ella se gastan tus peticiones)
  - memoria.db       lo que Nox recuerda de ti
  - config_local.json  rutas de tu equipo
  - programas.json   el catalogo de TUS programas (cada maquina arma el suyo)
  - PENDIENTES_BOVEDA.md  notas personales de trabajo
  - mcp_servidores.json  tus servidores de herramientas externas y sus permisos
  - voces/*.onnx     63 MB que el instalador vuelve a descargar
  - resultados_busqueda/  preguntas y nombres de notas de TU boveda (lo genera evaluar_busqueda.py)
  - .venv, __pycache__  basura que cada maquina regenera

Antes de cerrar el zip se comprueba que la clave de OpenRouter no aparezca dentro de
ningun archivo incluido; si aparece, no se crea nada.
"""
import fnmatch
import sys
import zipfile
from pathlib import Path

PROYECTO = Path(__file__).resolve().parent
DESTINO = PROYECTO.parent / "Nox_para_compartir.zip"

EXCLUIR_NOMBRES = ("openrouter.key", "memoria.db", "config_local.json", "programas.json",
                   "PENDIENTES_BOVEDA.md", "mcp_servidores.json", ".directory")
EXCLUIR_PATRONES = ("*.onnx", "*.onnx.json", "*.pyc", "*.zip")
EXCLUIR_CARPETAS = {".venv", "__pycache__", ".git", "respaldos", "cache", "resultados_busqueda"}


def incluir(ruta: Path) -> bool:
    relativa = ruta.relative_to(PROYECTO)
    if any(parte in EXCLUIR_CARPETAS for parte in relativa.parts):
        return False
    if ruta.name in EXCLUIR_NOMBRES:
        return False
    return not any(fnmatch.fnmatch(ruta.name, p) for p in EXCLUIR_PATRONES)


def main() -> int:
    archivos = sorted(p for p in PROYECTO.rglob("*") if p.is_file() and incluir(p))

    # Comprobacion: ni la clave ni su contenido pueden estar en lo que se va a mandar.
    clave_archivo = PROYECTO / "openrouter.key"
    if clave_archivo.exists():
        clave = clave_archivo.read_text(encoding="utf-8", errors="ignore").strip().encode()
        if len(clave) >= 8:
            for p in archivos:
                if clave in p.read_bytes():
                    print(f"ABORTADO: la clave de OpenRouter aparece dentro de {p.relative_to(PROYECTO)}")
                    return 1

    if DESTINO.exists():
        DESTINO.unlink()
    with zipfile.ZipFile(DESTINO, "w", zipfile.ZIP_DEFLATED) as z:
        for p in archivos:
            z.write(p, Path("Nox") / p.relative_to(PROYECTO))

    mb = DESTINO.stat().st_size / 1024 / 1024
    print(f"Listo: {DESTINO}  ({len(archivos)} archivos, {mb:.1f} MB)")
    print("Dejados afuera a proposito: " + ", ".join(EXCLUIR_NOMBRES) + ", voces, .venv")
    print("Quien lo reciba corre instalar.sh (Linux) o instalar.bat (Windows).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
