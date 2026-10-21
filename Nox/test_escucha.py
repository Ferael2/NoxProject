"""
Verifica que la escucha espere a que Brian termine, en vez de cortar en la primera pausa.

Simula el flujo de trozos de audio que ve EscuchaContinua, con un patron de habla real
(frases separadas por pausas para pensar), y comprueba cuantos mensajes habria mandado.

    python test_escucha.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

import config
import voz

E = voz.EscuchaContinua._trozos_de_espera
fallos = []


def simular(patron, espera_fija=None) -> int:
    """
    Corre la logica de acumulacion sobre un patron de (segundos, hay_voz) y devuelve
    cuantos mensajes se habrian despachado.

    espera_fija simula la version vieja (corte a los 0.8 s) para comparar.
    """
    mensajes = 0
    silencios = con_voz = 0
    hablando = False

    for segundos, hay_voz in patron:
        for _ in range(int(segundos / 0.1)):
            if not hablando:
                if hay_voz:
                    hablando, silencios, con_voz = True, 0, 1
                continue

            if hay_voz:
                silencios = 0
                con_voz += 1
            else:
                silencios += 1

            limite = (
                int(espera_fija / 0.1) if espera_fija
                else E(con_voz * 0.1)
            )
            if silencios >= limite:
                mensajes += 1
                hablando, silencios, con_voz = False, 0, 0
    return mensajes


print("=== Caso que te fallaba: dictado con pausas para pensar ===")
# "Nox armame un documento con... este... las ideas del mod... y tambien
#  queria que... o sea que agregue una maquina nueva"
dictado = [
    (3.0, True),   # "Nox armame un documento con"
    (1.2, False),  # pausa para pensar
    (4.0, True),   # "las ideas del mod de minecraft"
    (1.5, False),  # otra pausa
    (5.0, True),   # "y tambien queria que agregue una maquina"
    (1.0, False),  # duda
    (3.0, True),   # "de reciclaje de herramientas"
    (4.0, False),  # ya termino de verdad
]

antes = simular(dictado, espera_fija=0.8)
ahora = simular(dictado)

print(f"  Version vieja (corte fijo a 0.8s): {antes} mensajes cortados")
print(f"  Version nueva (espera adaptativa): {ahora} mensaje completo")
ok = ahora == 1 and antes > 1
print(f"  [{'OK ' if ok else 'FALLA'}] el dictado llega entero")
if not ok:
    fallos.append("el dictado se sigue partiendo")

print("\n=== Las ordenes cortas siguen siendo rapidas ===")
orden = [(1.2, True), (1.5, False)]
n = simular(orden)
ok = n == 1
print(f"  [{'OK ' if ok else 'FALLA'}] 'Nox, abri Steam' se despacha ({n} mensaje)")
if not ok:
    fallos.append("las ordenes cortas no se despachan")

espera_corta = E(1.2) * 0.1
ok = espera_corta <= 1.3
print(f"  [{'OK ' if ok else 'FALLA'}] espera solo {espera_corta:.1f}s tras una orden corta")
if not ok:
    fallos.append("las ordenes cortas esperan demasiado")

print("\n=== Dos mensajes separados siguen separandose ===")
# Habla, se calla de verdad un buen rato, y despues habla otra vez.
dos = [(2.0, True), (5.0, False), (2.0, True), (4.0, False)]
n = simular(dos)
ok = n == 2
print(f"  [{'OK ' if ok else 'FALLA'}] dos mensajes distintos dan {n} mensajes")
if not ok:
    fallos.append("no separa mensajes distintos")

print("\n=== Limites ===")
ok = config.MAX_SEGUNDOS_FRASE >= 60
print(f"  [{'OK ' if ok else 'FALLA'}] admite dictados largos ({config.MAX_SEGUNDOS_FRASE:.0f}s)")
if not ok:
    fallos.append("el tope de grabacion es muy corto")

ok = E(0) * 0.1 >= 1.0
print(f"  [{'OK ' if ok else 'FALLA'}] la espera minima ({E(0)*0.1:.1f}s) tolera una respiracion")
if not ok:
    fallos.append("la espera minima es muy corta")

print("\n=== La grabacion manual no tiene tope ===")
import inspect
fuente = inspect.getsource(voz.Grabadora)
ok = "SEGUNDOS_GRABACION" not in fuente
print(f"  [{'OK ' if ok else 'FALLA'}] el boton 'Hablar' graba hasta que lo pares")
if not ok:
    fallos.append("la grabacion manual tiene tope fijo")

print("\n" + "=" * 60)
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("LA ESCUCHA ESPERA A QUE TERMINES")
