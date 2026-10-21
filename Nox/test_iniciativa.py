"""
Pruebas de la iniciativa de Nox: recordatorios y saludo de la mañana (recordatorios.py).

    python test_iniciativa.py

Todo en carpetas temporales y con la hora controlada: no espera minutos de verdad.
"""
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

import config
import enrutador
import guardian
import herramientas
import recordatorios as R

fallos = []


def check(descripcion, condicion):
    if not condicion:
        fallos.append(descripcion)
    print(f"  [{'OK ' if condicion else 'FALLA'}] {descripcion}")


def invalido(**kw) -> bool:
    try:
        R.crear(**kw)
    except R.RecordatorioInvalido:
        return True
    return False


tmp = tempfile.TemporaryDirectory()
carpeta = Path(tmp.name)
parches = [mock.patch.object(config, "CARPETA_TRABAJO", carpeta), mock.patch.object(guardian, "BITACORA", carpeta / "bitacora.log")]
for p in parches:
    p.start()

AHORA = datetime(2026, 10, 20, 22, 40)     # martes

print("=== Fechas en español ===")
check("fecha larga", R.fecha_larga(AHORA) == "martes 20 de octubre de 2026")
check("ahora, con hora (es lo que se le dice al modelo)", R.ahora_texto(AHORA) == "martes 20 de octubre de 2026, 22:40")
check("hoy", R.describir_cuando(datetime(2026, 10, 20, 23, 5), AHORA) == "hoy a las 23:05")
check("mañana", R.describir_cuando(datetime(2026, 10, 21, 9, 0), AHORA) == "mañana a las 9:00")
check("esta semana: el dia", R.describir_cuando(datetime(2026, 10, 23, 18, 30), AHORA) == "el viernes a las 18:30")
check("mas lejos: con fecha", R.describir_cuando(datetime(2026, 11, 3, 8, 0), AHORA) == "el martes 3 de noviembre a las 8:00")

print("\n=== Crear ===")
r = R.crear("llamar a mamá", en_minutos=20, ahora=AHORA)
check("en 20 minutos queda a las 23:00", r["cuando"] == "2026-10-20T23:00")
r2 = R.crear("entregar el informe", fecha_iso="2026-10-21T09:00", ahora=AHORA)
check("con fecha exacta", r2["cuando"] == "2026-10-21T09:00" and r2["id"] == 2)
check("con espacio en lugar de T tambien", R.crear("x", fecha_iso="2026-10-22 10:30", ahora=AHORA)["cuando"] == "2026-10-22T10:30")
check("sin cuando, pide el cuando", invalido(texto="algo", ahora=AHORA))
check("con las dos formas a la vez, tambien (es ambiguo)", invalido(texto="algo", en_minutos=5, fecha_iso="2026-10-21T09:00", ahora=AHORA))
check("sin texto", invalido(texto="  ", en_minutos=5, ahora=AHORA))
check("texto larguisimo", invalido(texto="x" * 500, en_minutos=5, ahora=AHORA))
check("una hora que ya paso", invalido(texto="algo", fecha_iso="2026-10-20T08:00", ahora=AHORA))
check("fecha que no se entiende", invalido(texto="algo", fecha_iso="mañana a las nueve", ahora=AHORA))
check("minutos negativos o cero", invalido(texto="algo", en_minutos=0, ahora=AHORA) and invalido(texto="algo", en_minutos=-5, ahora=AHORA))
check("minutos que no son numero", invalido(texto="algo", en_minutos="pronto", ahora=AHORA))
check("mas de un año adelante", invalido(texto="algo", fecha_iso="2028-01-01T10:00", ahora=AHORA))
check("repeticion desconocida", invalido(texto="algo", en_minutos=5, repetir="cada rato", ahora=AHORA))
check("el texto se limpia (sin saltos de linea ni espacios dobles)",
      R.crear("hola\n  mundo", en_minutos=5, ahora=AHORA)["texto"] == "hola mundo")

print("\n=== Listar, cancelar, vencidos ===")
lista = R.listar()
check("se listan del mas proximo al mas lejano", [x["cuando"] for x in lista] == sorted(x["cuando"] for x in lista))
check("cancelar uno lo quita", R.cancelar(2)["texto"] == "entregar el informe" and all(x["id"] != 2 for x in R.listar()))
check("cancelar uno que no existe devuelve None", R.cancelar(999) is None)
check("a las 22:50 todavia no toca el de las 23:00", all(x["id"] != 1 for x in R.vencidos(datetime(2026, 10, 20, 22, 50))))
check("a las 23:01 ya toca", any(x["id"] == 1 for x in R.vencidos(datetime(2026, 10, 20, 23, 1))))
check("si Nox estaba cerrado, tambien avisa los que se pasaron", any(x["id"] == 1 for x in R.vencidos(datetime(2026, 10, 25, 12, 0))))
R.marcar_avisado(1, datetime(2026, 10, 20, 23, 1))
check("avisado una vez, no vuelve a avisar", all(x["id"] != 1 for x in R.vencidos(datetime(2026, 10, 25, 12, 0))))

print("\n=== Repetir ===")
d = R.crear("tomar agua", fecha_iso="2026-10-20T23:00", repetir="diario", ahora=AHORA)
R.marcar_avisado(d["id"], datetime(2026, 10, 20, 23, 1))
nuevo = next(x for x in R.listar() if x["id"] == d["id"])
check("un recordatorio diario se reprograma para mañana", nuevo["cuando"] == "2026-10-21T23:00" and not nuevo["avisado"])
R.marcar_avisado(d["id"], datetime(2026, 10, 30, 8, 0))
check("si pasaron dias con Nox cerrado, salta al proximo futuro (no avisa 9 veces)",
      next(x for x in R.listar() if x["id"] == d["id"])["cuando"] == "2026-10-30T23:00")

print("\n=== Limites y archivos ===")
for i in range(R.MAX_PENDIENTES):
    try:
        R.crear(f"r{i}", en_minutos=10 + i, ahora=AHORA)
    except R.RecordatorioInvalido:
        break
check("hay un tope de pendientes", invalido(texto="uno mas", en_minutos=5, ahora=AHORA))
(carpeta / "recordatorios.json").write_text("{ roto", encoding="utf-8")
check("un archivo roto no tumba nada: se lee como vacio", R.listar() == [])
check("y se puede volver a crear", R.crear("otra vez", en_minutos=5, ahora=AHORA)["id"] == 1)
check("no quedan archivos temporales", not list(carpeta.glob("*.tmp")))
(carpeta / "recordatorios.json").unlink()

print("\n=== Saludo de la mañana ===")
manana = datetime(2026, 10, 21, 8, 15)
with mock.patch.object(config, "SALUDO_MATUTINO", False):
    check("apagado (como viene), no saluda", R.saludo_matutino(manana) is None)
with mock.patch.object(config, "SALUDO_MATUTINO", True):
    check("a las 22:40 no es de mañana, no saluda", R.saludo_matutino(AHORA) is None)
    R.crear("reunion", fecha_iso="2026-10-21T10:00", ahora=manana)
    texto = R.saludo_matutino(manana, marcar=False)
    check("saluda con la fecha y lo de hoy", "miércoles 21 de octubre" in texto and "reunion" in texto and config.USUARIO in texto)
    check("sin marcar, lo repetiria", R.saludo_matutino(manana, marcar=False) is not None)
    R.saludo_matutino(manana)
    check("una vez dado, no se repite el mismo dia", R.saludo_matutino(manana) is None)
    check("al dia siguiente si", R.saludo_matutino(manana + timedelta(days=1)) is not None)

print("\n=== Herramientas (lo que usa el modelo) ===")
guardian.registrar_confirmador(None)
guardian.nuevo_turno()
salida = herramientas.ejecutar("crear_recordatorio", {"texto": "regar plantas", "en_minutos": 30})
check(f"crear repite lo programado ({salida[:60]})", salida.startswith("Programado.") and "regar plantas" in salida)
check("una fecha invalida se explica, no revienta", "No pude programarlo" in herramientas.ejecutar("crear_recordatorio", {"texto": "x", "fecha_iso": "ayer"}))
check("listar muestra los pendientes con su numero", "regar plantas" in herramientas.ejecutar("listar_recordatorios", {}))
idr = next(x["id"] for x in R.listar() if x["texto"] == "regar plantas")
check("cancelar por numero", herramientas.ejecutar("cancelar_recordatorio", {"id_recordatorio": idr}).startswith("Cancelado"))
check("cancelar uno inexistente avisa", "No existe" in herramientas.ejecutar("cancelar_recordatorio", {"id_recordatorio": 9999}))
check("crear y cancelar cuentan como acciones que modifican (limite por turno y bitacora)",
      {"crear_recordatorio", "cancelar_recordatorio"} <= guardian.ACCIONES_QUE_MODIFICAN)
check("listar es de solo lectura", "listar_recordatorios" not in guardian.ACCIONES_QUE_MODIFICAN)
guardian.nuevo_turno()
pasaron = sum(not herramientas.ejecutar("crear_recordatorio", {"texto": f"t{i}", "en_minutos": 5}).startswith("Freno")
              for i in range(config.MAX_ACCIONES_POR_TURNO + 3))
check(f"un modelo confundido no puede llenar la agenda en un turno (paso {pasaron})", pasaron <= config.MAX_ACCIONES_POR_TURNO)
import nube
check("a la nube no llegan los recordatorios (no son herramientas publicas)",
      not {"crear_recordatorio", "listar_recordatorios"} & set(nube.HERRAMIENTAS_PUBLICAS))

print("\n=== El modelo sabe que dia es y el enrutador lo manda a la PC ===")
check("cada mensaje lleva la fecha y la hora de ahora", "AHORA ES:" in enrutador.instruccion_completa("hola", "charla"))
for frase in ("recuérdame llamar a mamá en 20 minutos", "avísame mañana a las 9 de la reunión", "qué recordatorios tengo"):
    check(f"«{frase}» se resuelve en la PC", enrutador.decidir_ruta(frase)[0] == "local")

tmp.cleanup()
for p in parches:
    p.stop()
print("\n" + "=" * 60)
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("TODAS LAS PRUEBAS DE INICIATIVA PASARON")
