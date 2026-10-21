"""
Verifica que Nox entienda las formas naturales de dirigirse a el.

El nombre no siempre va primero: "como estas Nox", "abrime Steam Nox", "hola Nox".
Y hay que distinguir entre pedir atencion ("hey Nox" -> contesta y espera) y un
mensaje completo ("hola Nox" -> responde de verdad).

    python test_conversacion.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

import config
import enrutador
import voz

E = voz.EscuchaContinua._extraer_orden
LL = voz.EscuchaContinua.es_solo_llamada
fallos = []


def check(desc, cond):
    if not cond:
        fallos.append(desc)
    print(f"  [{'OK ' if cond else 'FALLA'}] {desc}")


print("=== Saludos: el nombre puede ir donde caiga ===")
saludos = [
    ("hola Nox", "hola"),
    ("Nox hola", "hola"),
    ("hey Nox", "hey"),
    ("buenas Nox", "buenas"),
    ("como estas Nox", "como estas"),
    ("Nox como estas", "como estas"),
    ("que tal Nox todo bien", "que tal todo bien"),
    ("buen dia Nox", "buen dia"),
]
for frase, esperado in saludos:
    r = E(frase)
    check(f"{frase!r:32} -> {r!r}", r == esperado)

print("\n=== Ordenes con el nombre al final ===")
ordenes = [
    ("abrime Steam Nox", "abrime Steam"),
    ("Nox abrime Steam", "abrime Steam"),
    ("subi el volumen Nox", "subi el volumen"),
    ("Nox, que juego me recomendas", "que juego me recomendas"),
]
for frase, esperado in ordenes:
    r = E(frase)
    check(f"{frase!r:32} -> {r!r}", r == esperado)

print("\n=== Pedir atencion vs. mensaje completo ===")
atencion = ["hey", "oye", "dime", "decime", "escuchame", "", "estas ahi"]
for a in atencion:
    check(f"'{a}' pide atencion (contesta y espera)", LL(a))

mensajes = ["hola", "como estas", "que tal", "abri Steam", "buenas"]
for m in mensajes:
    check(f"'{m}' es un mensaje (responde de verdad)", not LL(m))

print("\n=== No activarse cuando hablan DE el ===")
ajenas = [
    "el problema es que nox no funciona bien",
    "ayer instale nox en la otra compu y anduvo",
    "tuve que reiniciar nox como tres veces seguidas",
    "hola como estas",
    "abri Steam por favor",
]
for f in ajenas:
    r = E(f)
    check(f"{f[:46]!r:48} -> {r!r}", r is None)

print("\n=== El enrutador trata los saludos como charla ===")
for frase in ["hola", "como estas", "que tal todo bien", "buenas", "gracias"]:
    modo = enrutador.clasificar(frase)
    check(f"{frase!r:22} -> modo '{modo}'", modo == "charla")

print("\n=== Ventana de conversacion ===")
check(f"esta activa ({config.VENTANA_CONVERSACION:.0f}s sin repetir el nombre)",
      config.VENTANA_CONVERSACION > 0)
check("hay varias respuestas al llamado, no una sola",
      len(config.RESPUESTAS_AL_LLAMADO) >= 3)

import inspect
import gui
fuente = inspect.getsource(gui.VentanaNox._escuche_algo)
check("la ventana se chequea al escuchar sin nombre", "VENTANA_CONVERSACION" in fuente)
fuente_resp = inspect.getsource(gui.VentanaNox._mostrar_respuesta)
check("la ventana arranca cuando Nox TERMINA de hablar",
      "ultima_respuesta = time.time()" in fuente_resp)

print("\n" + "=" * 60)
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("LA CONVERSACION SE SIENTE NATURAL")
