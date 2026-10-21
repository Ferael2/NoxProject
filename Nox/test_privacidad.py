"""
Verifica que nada personal pueda salir de la PC por el canal de OpenRouter.

Correr despues de tocar enrutador.py, nube.py o nucleo.py:
    python test_privacidad.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

import enrutador
import herramientas
import nube
import nucleo

fallos = []


def check(descripcion: str, condicion: bool):
    global fallos
    if not condicion:
        fallos.append(descripcion)
    print(f"  [{'OK ' if condicion else 'FALLA'}] {descripcion}")


print("=== Preguntas que NO deben salir de la PC ===")
personales = [
    "en que iba mi proyecto Sistema Financiero Personal y que conviene hacer",
    "por que me conviene ese enfoque para mi bóveda de notas",
    "compara mis juegos y decime cual me conviene retomar",
    "te acordas de lo que te dije sobre como explicarme las cosas",
    "analiza mis archivos de la carpeta Documentos y decime que sobra",
    "que opinas de Nox como asistente",
    "cuantas horas tengo en Steam y por que juego tanto",
]
for p in personales:
    check(f"queda local: {p[:56]}", enrutador.parece_personal(p))

print("\n=== Preguntas generales que SI pueden salir ===")
generales = [
    "por que un indice vectorial falla con siglas y como se corrige",
    "compara BM25 con busqueda semantica",
    "explica como funciona la cuantizacion de modelos de lenguaje",
    "cual es la diferencia entre un MoE y un modelo denso",
]
for p in generales:
    check(f"puede ir a la nube: {p[:52]}", not enrutador.parece_personal(p))

print("\n=== El canal externo solo expone herramientas publicas ===")
publicas = set(nube.HERRAMIENTAS_PUBLICAS)
todas = set(herramientas.DESPACHADOR)
expuestas = {e["function"]["name"] for e in nube._herramientas_publicas()}

check(f"expone exactamente {len(publicas)} herramientas", expuestas == publicas)
check("NO expone buscar_en_boveda", "buscar_en_boveda" not in expuestas)
check("NO expone leer_nota", "leer_nota" not in expuestas)
check("NO expone crear_nota", "crear_nota" not in expuestas)
check("NO expone buscar_recuerdos", "buscar_recuerdos" not in expuestas)
check("NO expone recordar", "recordar" not in expuestas)
check("NO expone leer_archivo", "leer_archivo" not in expuestas)
check("NO expone escribir_archivo", "escribir_archivo" not in expuestas)
check("NO expone mis_juegos", "mis_juegos" not in expuestas)
check("NO expone consultar_sistema", "consultar_sistema" not in expuestas)
check("NO expone abrir_programa", "abrir_programa" not in expuestas)
print(f"       (de {len(todas)} herramientas totales, salen {len(expuestas)})")

print("\n=== El system prompt externo no lleva contexto personal ===")
prompt = nube.SYSTEM_PROMPT_NUBE.lower()
check("no menciona la bóveda", "boveda" not in prompt and "bóveda" not in prompt)
check("no menciona proyectos suyos", "skyrent" not in prompt and "gbo" not in prompt)
import config as _c
check("no inyecta la memoria", f"lo que ya sabes de {_c.USUARIO.lower()}" not in prompt)

print("\n=== El historial limpio no acumula turnos personales ===")
c = nucleo.Conversacion()
c.herramientas_del_turno = {"buscar_en_boveda"}
antes = len(c.historial_limpio)
# Simula el filtro que aplica enviar()
sucio = bool(c.herramientas_del_turno - nucleo.PUBLICAS)
check("un turno que uso la boveda se marca como sucio", sucio)

c.herramientas_del_turno = {"buscar_en_internet", "hora_actual"}
limpio = not bool(c.herramientas_del_turno - nucleo.PUBLICAS)
check("un turno que solo busco en internet queda limpio", limpio)

check("una conversacion nueva arranca con historial limpio vacio", antes == 0)

print("\n=== La key no se expone ===")
check("la key se lee de archivo, no de config.py",
      nube.ARCHIVO_KEY.name == "openrouter.key")
import config
check("config.py no contiene ninguna key",
      "sk-or-" not in Path(config.__file__).read_text(encoding="utf-8"))

print("\n" + "=" * 62)
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("TODAS LAS PRUEBAS DE PRIVACIDAD PASARON")
