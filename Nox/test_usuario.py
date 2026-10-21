"""
Pruebas del nombre de usuario configurable.

    python test_usuario.py

Nox no debe tener cosas de su autor pegadas: cada persona que lo use tiene que ver su
nombre, y lo personal (perfil) no puede salir a la nube.
"""
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

import config
import nube
import nucleo

fallos = []


def check(descripcion, condicion):
    if not condicion:
        fallos.append(descripcion)
    print(f"  [{'OK ' if condicion else 'FALLA'}] {descripcion}")


print("=== Otra persona, sin boveda ===")
with mock.patch.object(config, "USUARIO", "Ana"), mock.patch.object(config, "HAY_BOVEDA", False), \
        mock.patch.object(config, "PERFIL_USUARIO", "Le gusta el ajedrez."), \
        mock.patch.object(config, "ESTILO_USUARIO", "Habla con frases cortas."):
    local = nucleo.construir_system_prompt()
    nube_ = nube._armar_prompt_nube()

check("el prompt local usa el nombre configurado", "Ana" in local and "ANA" in local)
check("el prompt local no menciona al autor (Brian)", "Brian" not in local)
check("el prompt de la nube no menciona al autor (Brian)", "Brian" not in nube_)
check("sin boveda, el prompt no manda a buscar en ella", "buscar_en_boveda" not in local and "crear_nota" not in local)
check("sin boveda, internet queda como fuente", "buscar_en_internet" in local)
check("el perfil personal llega al modelo local", "ajedrez" in local)
check("el perfil personal NO llega a la nube", "ajedrez" not in nube_)
check("la regla de estilo llega a los dos", "frases cortas" in local and "frases cortas" in nube_)
check("la nube no menciona la boveda", "boveda" not in nube_.lower() and "bóveda" not in nube_.lower())
check("el prompt no asume el genero de la persona (sin 'él' ni 'ella')",
      " él " not in local.lower() and " ella " not in local.lower())

print("\n=== Con boveda ===")
with mock.patch.object(config, "USUARIO", "Ana"), mock.patch.object(config, "HAY_BOVEDA", True):
    con_boveda = nucleo.construir_system_prompt()
check("con boveda, la busca primero", "BÓVEDA PRIMERO" in con_boveda and "buscar_en_boveda" in con_boveda)
check("con boveda tampoco aparece el autor", "Brian" not in con_boveda)

print("\n=== Sin nombre configurado ===")
with mock.patch.object(config, "AJUSTES_LOCALES", {}), mock.patch("getpass.getuser", return_value="maria_lopez"):
    check("se usa el usuario del sistema, con formato de nombre", config._nombre_usuario() == "Maria Lopez")
with mock.patch.object(config, "AJUSTES_LOCALES", {"usuario": "  Luis "}):
    check("el nombre configurado se limpia", config._nombre_usuario() == "Luis")

print("\n=== Perfiles de equipo ===")
claves = {"descripcion", "modelo_chat", "num_ctx", "modelo_whisper", "modelo_whisper_escucha", "whisper_device"}
for nombre, perfil in config.PERFILES_EQUIPO.items():
    check(f"el perfil '{nombre}' tiene todas las claves", set(perfil) == claves)
check("el perfil por defecto existe", config.EQUIPO_POR_DEFECTO in config.PERFILES_EQUIPO)
check("existe un perfil para la laptop RTX 4060", "laptop_rtx4060" in config.PERFILES_EQUIPO)
with mock.patch.object(config, "AJUSTES_LOCALES", {}), \
        mock.patch.object(config, "_PERFIL", config.PERFILES_EQUIPO["basico"]):
    check("sin ajuste suelto, manda el perfil", config._ajuste("modelo_chat") == "qwen3:4b")
with mock.patch.object(config, "AJUSTES_LOCALES", {"modelo_chat": "otro:1b"}), \
        mock.patch.object(config, "_PERFIL", config.PERFILES_EQUIPO["basico"]):
    check("un ajuste suelto de config_local.json pisa al perfil", config._ajuste("modelo_chat") == "otro:1b")

print("\n" + "=" * 60)
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("TODAS LAS PRUEBAS DE USUARIO PASARON")
