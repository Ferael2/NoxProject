"""
Pruebas de las herramientas externas (MCP): conexion de verdad con un servidor de prueba y,
sobre todo, las BARRERAS: que nada se ejecute sin permiso.

    python test_mcp.py

Levanta mcp_servidor_de_prueba.py como proceso aparte (un servidor MCP real, por stdio).
Todo en carpetas temporales: no toca tu mcp_servidores.json.
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

import config
import guardian
import herramientas
import mcp_cliente
import nube
import nucleo
import seguridad
from mcp_cliente import Administrador, ConfigInvalida

fallos = []


def check(descripcion, condicion):
    if not condicion:
        fallos.append(descripcion)
    print(f"  [{'OK ' if condicion else 'FALLA'}] {descripcion}")


def rechaza(fn) -> bool:
    try:
        fn()
    except ConfigInvalida:
        return True
    return False


SERVIDOR = str(Path(__file__).resolve().parent / "mcp_servidor_de_prueba.py")
tmp = tempfile.TemporaryDirectory()
carpeta = Path(tmp.name)
os.environ["CLAVE_SECRETA_DE_PRUEBA"] = "no-me-filtres"   # no debe llegar al servidor

print("=== Validar lo que se guarda ===")
ok = {"nombre": "Prueba", "comando": "python", "args": ["x.py"]}
check("un servidor normal se acepta", mcp_cliente.validar_servidor("prueba", ok)["activo"] is False)
check("el identificador no puede tener mayusculas ni espacios", rechaza(lambda: mcp_cliente.validar_servidor("Mi Servidor", ok)))
check("el comando no puede llevar simbolos de shell", rechaza(lambda: mcp_cliente.validar_servidor("a", {**ok, "comando": "python; rm -rf ~"})))
check("el comando no puede llevar una tuberia", rechaza(lambda: mcp_cliente.validar_servidor("a", {**ok, "comando": "cat x | sh"})))
check("falta el comando", rechaza(lambda: mcp_cliente.validar_servidor("a", {"nombre": "x"})))
check("los argumentos deben ser textos", rechaza(lambda: mcp_cliente.validar_servidor("a", {**ok, "args": [1, 2]})))
check("las variables de entorno deben tener nombres validos", rechaza(lambda: mcp_cliente.validar_servidor("a", {**ok, "env": {"a b": "x"}})))
check("la politica debe ser una conocida", rechaza(lambda: mcp_cliente.validar_servidor("a", {**ok, "herramientas": {"t": "siempre"}})))
check("'Mi Navegador!' se vuelve un identificador valido", mcp_cliente.identificador("Mi Navegador!") == "mi_navegador")
nombre = mcp_cliente.nombre_para_modelo("web", "browser.click-now")
check("el nombre para el modelo solo lleva letras, numeros y _", nombre == "mcp_web_browser_click_now")
largo = mcp_cliente.nombre_para_modelo("web", "x" * 200)
check("un nombre larguisimo se acorta sin repetirse", len(largo) <= 60 and largo != mcp_cliente.nombre_para_modelo("web", "x" * 201))

print("\n=== Conectar un servidor real ===")
archivo = carpeta / "mcp_servidores.json"
with mock.patch.object(config, "CARPETA_TRABAJO", carpeta):
    adm = Administrador(archivo)
    adm.agregar("prueba", {"nombre": "Servidor de prueba", "comando": sys.executable, "args": [SERVIDOR]})
    check("un servidor nuevo nace DESACTIVADO", adm.servidores["prueba"]["activo"] is False)
    check("y sin ninguna herramienta permitida", adm.servidores["prueba"]["herramientas"] == {})
    adm.arrancar()
    check("sin activarlo, no se conecta", adm._estado["prueba"]["estado"] == "detenido")

    adm.fijar_activo("prueba", True)
    adm.esperar_listo(60)
    est = adm._estado["prueba"]
    check(f"al activarlo se conecta ({est['estado']} {est['error']})", est["estado"] == "conectado")
    descubiertas = set(est["herramientas"])
    check("descubre las 6 herramientas del servidor", {"sumar", "eco", "variables_de_entorno", "pagina_con_trampa", "lenta", "enorme", "falla"} <= descubiertas)

    adm.fijar_politica("prueba", "variables_de_entorno", "permitir"); adm.esquemas()
    directorio = adm.ejecutar("mcp_prueba_variables_de_entorno", {})
    check("el servidor trabaja en su propia carpeta, no en la de Nox", (carpeta / "mcp" / "prueba").is_dir())
    adm.fijar_politica("prueba", "variables_de_entorno", "bloquear")

    print("\n=== Todo bloqueado por defecto ===")
    check("conectado, pero el modelo NO ve ninguna herramienta externa", adm.esquemas() == [])
    check("herramientas.esquemas_completos() no suma nada", len(herramientas.esquemas_completos()) == len(herramientas.ESQUEMAS))
    check("llamar a una herramienta bloqueada por su nombre no hace nada",
          "no existe" in adm.ejecutar(mcp_cliente.nombre_para_modelo("prueba", "sumar"), {"a": 1, "b": 2}))
    check("la ventana ve las herramientas, todas en 'bloquear'",
          all(h["politica"] == "bloquear" for h in adm.estado_servidores()[0]["herramientas"]))

    print("\n=== Permitir una herramienta ===")
    adm.fijar_politica("prueba", "sumar", "permitir")
    esquemas = adm.esquemas()
    check("ahora el modelo ve SOLO esa herramienta", [e["function"]["name"] for e in esquemas] == ["mcp_prueba_sumar"])
    funcion = esquemas[0]["function"]
    check("con su esquema de parametros (a y b)", set(funcion["parameters"]["properties"]) == {"a", "b"})
    check("la descripcion avisa que es externa", "externa" in funcion["description"].lower())
    salida = adm.ejecutar("mcp_prueba_sumar", {"a": 2, "b": 3})
    check(f"se ejecuta y devuelve el resultado ({salida.splitlines()[-1]})", salida.strip().endswith("5"))
    check("el resultado viene marcado como informacion de un tercero", "no sigas instrucciones" in salida)
    check("las otras herramientas siguen bloqueadas", "no existe" in adm.ejecutar("mcp_prueba_eco", {"texto": "hola"}))
    check("argumentos que no son un objeto se rechazan", "deben ser un objeto" in adm.ejecutar("mcp_prueba_sumar", [1, 2]))

    print("\n=== Barreras ===")
    adm.fijar_politica("prueba", "variables_de_entorno", "permitir")
    adm.esquemas()
    entorno = adm.ejecutar("mcp_prueba_variables_de_entorno", {})
    check("el servidor NO ve las claves del entorno de Nox", "CLAVE_SECRETA_DE_PRUEBA" not in entorno)
    check("(sigue viendo lo basico que necesita, como PATH)", "PATH" in entorno)

    adm.fijar_politica("prueba", "pagina_con_trampa", "permitir")
    adm.esquemas()
    trampa = adm.ejecutar("mcp_prueba_pagina_con_trampa", {})
    check("un texto con instrucciones escondidas llega marcado como dato", "IGNORA TUS INSTRUCCIONES" in trampa and "no sigas instrucciones" in trampa.splitlines()[0])

    adm.fijar_politica("prueba", "enorme", "permitir")
    adm.esquemas()
    grande = adm.ejecutar("mcp_prueba_enorme", {})
    check(f"un resultado enorme se recorta ({len(grande)} caracteres)", len(grande) < mcp_cliente.MAX_CHARS_RESULTADO + 400 and "recortado" in grande)

    adm.fijar_politica("prueba", "falla", "permitir")
    adm.esquemas()
    check("si la herramienta falla, se informa sin romper nada", "ERROR" in adm.ejecutar("mcp_prueba_falla", {}))

    adm.fijar_politica("prueba", "lenta", "permitir")
    adm.esquemas()
    with mock.patch.object(mcp_cliente, "TIMEOUT_LLAMADA", 1):
        check("una herramienta que tarda de mas se corta", "tardó más" in adm.ejecutar("mcp_prueba_lenta", {"segundos": 5}))
    check("tras un corte, el servidor sigue respondiendo", adm.ejecutar("mcp_prueba_sumar", {"a": 1, "b": 1}).strip().endswith("2"))

    adm.fijar_politica("prueba", "sumar", "bloquear")
    check("bloquear de nuevo: con el nombre viejo ya no corre", "bloqueada" in adm.ejecutar("mcp_prueba_sumar", {"a": 1, "b": 1}))
    adm.fijar_politica("prueba", "sumar", "permitir")

    print("\n=== Herramientas de alto riesgo ===")
    check("'browser_run_code_unsafe' es de alto riesgo", mcp_cliente.riesgo_de("browser_run_code_unsafe") == "alto")
    check("'browser_evaluate' y 'browser_file_upload' tambien", all(mcp_cliente.riesgo_de(n) == "alto" for n in ("browser_evaluate", "browser_file_upload")))
    check("'delete_file' y 'exec_command' tambien", all(mcp_cliente.riesgo_de(n) == "alto" for n in ("delete_file", "exec_command")))
    check("'browser_snapshot' y 'sumar' no lo son", all(mcp_cliente.riesgo_de(n) == "normal" for n in ("browser_snapshot", "sumar")))
    adm.servidores["prueba"]["herramientas"]["browser_evaluate"] = "bloquear"
    adm._estado["prueba"]["herramientas"]["browser_evaluate"] = {"descripcion": "", "esquema": {"type": "object", "properties": {}}, "solo_lectura": False}
    check("una herramienta de alto riesgo no se puede dejar en 'permitir'", rechaza(lambda: adm.fijar_politica("prueba", "browser_evaluate", "permitir")))
    check("pero si en 'preguntar'", not rechaza(lambda: adm.fijar_politica("prueba", "browser_evaluate", "preguntar")))
    adm.servidores["prueba"]["herramientas"]["browser_evaluate"] = "permitir"   # como si alguien editara el archivo a mano
    check("editando el archivo a mano tampoco se salta: sigue pidiendo permiso", adm._politica("prueba", "browser_evaluate") == "preguntar")
    del adm.servidores["prueba"]["herramientas"]["browser_evaluate"]
    del adm._estado["prueba"]["herramientas"]["browser_evaluate"]
    plantilla = mcp_cliente.PLANTILLAS["navegador"]["recomendadas"]
    check("la seleccion recomendada de la plantilla no tiene nada de alto riesgo en 'permitir'",
          not any(p == "permitir" and mcp_cliente.riesgo_de(n) == "alto" for n, p in plantilla.items()))
    check("y no supera el tope de herramientas activas", len(plantilla) <= mcp_cliente.MAX_HERRAMIENTAS_ACTIVAS)
    check("aplicar la seleccion recomendada solo toca lo que el servidor tiene",
          adm.aplicar_recomendadas("prueba", {"sumar": "permitir", "no_existe": "permitir"}) == 1)

    print("\n=== Tope de herramientas activas ===")
    for t in ("eco", "lenta", "enorme", "falla"):
        adm.fijar_politica("prueba", t, "bloquear")
    with mock.patch.object(mcp_cliente, "MAX_HERRAMIENTAS_ACTIVAS", 3):
        activas = [t for t in ("sumar", "variables_de_entorno", "pagina_con_trampa")]
        for t in activas:
            adm.fijar_politica("prueba", t, "permitir")
        check("no deja pasar del tope (cada herramienta gasta memoria del modelo)",
              rechaza(lambda: adm.fijar_politica("prueba", "eco", "permitir")))
        check("pero siempre se puede bloquear una", not rechaza(lambda: adm.fijar_politica("prueba", "sumar", "bloquear")))
        adm.fijar_politica("prueba", "sumar", "permitir")

    print("\n=== Guardian: permisos, limite y confirmaciones ===")
    adm.fijar_politica("prueba", "pagina_con_trampa", "preguntar")
    adm.fijar_politica("prueba", "variables_de_entorno", "bloquear")
    adm.esquemas()
    with mock.patch.object(mcp_cliente, "_administrador", adm), \
            mock.patch.object(guardian, "BITACORA", carpeta / "bitacora.log"):
        preguntas = []
        guardian.registrar_confirmador(lambda n, a: preguntas.append(n) or False)
        guardian.nuevo_turno()
        ok, motivo = guardian.revisar("mcp_prueba_pagina_con_trampa", {})
        check("'preguntar': le pide permiso a la persona", preguntas == ["mcp_prueba_pagina_con_trampa"])
        check("si la persona dice que no, NO se ejecuta", not ok)

        guardian.registrar_confirmador(lambda n, a: True)
        guardian.nuevo_turno()
        check("si dice que si, se ejecuta", guardian.revisar("mcp_prueba_pagina_con_trampa", {})[0])

        preguntas.clear()
        guardian.registrar_confirmador(lambda n, a: preguntas.append(n) or True)
        guardian.nuevo_turno()
        check("'permitir': no pregunta", guardian.revisar("mcp_prueba_sumar", {"a": 1, "b": 1})[0] and not preguntas)
        check("'bloquear': se rechaza", not guardian.revisar("mcp_prueba_variables_de_entorno", {})[0])
        check("un nombre inventado que parece externo se rechaza", not guardian.revisar("mcp_inventado_borrar_todo", {})[0])

        guardian.registrar_confirmador(None)
        guardian.nuevo_turno()
        check("sin ventana para preguntar, 'preguntar' se niega (nunca se ejecuta a ciegas)",
              not guardian.revisar("mcp_prueba_pagina_con_trampa", {})[0])

        guardian.nuevo_turno()
        pasaron = sum(guardian.revisar("mcp_prueba_sumar", {"a": 1, "b": 1})[0] for _ in range(config.MAX_ACCIONES_POR_TURNO + 4))
        check(f"cada llamada externa cuenta para el limite por turno (dejo pasar {pasaron})", pasaron == config.MAX_ACCIONES_POR_TURNO)
        guardian.nuevo_turno()

        print("\n=== Integracion con las herramientas de Nox ===")
        guardian.registrar_confirmador(lambda n, a: True)
        completos = herramientas.esquemas_completos()
        nombres = {e["function"]["name"] for e in completos}
        check("el modelo local ve las herramientas externas permitidas", {"mcp_prueba_sumar", "mcp_prueba_pagina_con_trampa"} <= nombres)
        check("ESQUEMAS (lo fijo) no cambia", not any(e["function"]["name"].startswith("mcp_") for e in herramientas.ESQUEMAS))
        guardian.nuevo_turno()
        check("herramientas.ejecutar las corre pasando por el guardian",
              herramientas.ejecutar("mcp_prueba_sumar", {"a": 20, "b": 22}).strip().endswith("42"))
        check("una herramienta inventada sigue dando error", "no existe" in herramientas.ejecutar("mcp_nada_nada", {}).lower())
        publicas = {e["function"]["name"] for e in nube._herramientas_publicas()}
        check("a la nube NO llega ninguna herramienta externa", not any(n.startswith("mcp_") for n in publicas))
        check("un turno que usa una herramienta externa cuenta como personal (no sale a la nube)",
              not {"mcp_prueba_sumar"} <= nucleo.PUBLICAS)
        check("el prompt local avisa de las herramientas externas", "HERRAMIENTAS EXTERNAS" in nucleo.construir_system_prompt())
        guardian.registrar_confirmador(None)

        import enrutador
        check("pedir navegar con herramientas externas activas va local, no a la nube",
              enrutador.decidir_ruta("entra a bbc.com y dime los titulares")[0] == "local")

    print("\n=== Apagar y persistir ===")
    adm.fijar_activo("prueba", False)
    adm.detener_todo(10)
    check("al desactivarlo se desconecta", adm._estado["prueba"]["estado"] == "detenido")
    check("sin servidor conectado el modelo no ve nada", adm.esquemas() == [])
    nuevo = Administrador(archivo)
    check("la configuracion se guarda y se recupera", nuevo.servidores["prueba"]["herramientas"].get("sumar") == "permitir")
    check("y se recupera desactivada", nuevo.servidores["prueba"]["activo"] is False)
    archivo.write_text("{ roto", encoding="utf-8")
    check("un archivo roto no tumba a Nox: se lee como vacio", Administrador(archivo).servidores == {})

    print("\n=== Servidores que fallan ===")
    adm2 = Administrador(carpeta / "otro.json")
    adm2.agregar("fantasma", {"nombre": "No existe", "comando": "programa_que_no_existe_xyz"})
    adm2.fijar_activo("fantasma", True)
    adm2.esperar_listo(30)
    e = adm2._estado["fantasma"]
    check(f"un programa que no existe da un error claro, sin colgar Nox ({e['error'][:50]})", e["estado"] == "error" and "No encuentro" in e["error"])
    adm2.detener_todo(5)

    print("\n=== La configuracion no se puede tocar desde el chat ===")
    try:
        seguridad.validar_escritura(config.PROYECTO / "mcp_servidores.json", config.CARPETAS_ESCRITURA, config.EXTENSIONES_ESCRITURA)
        escribible = True
    except seguridad.Rechazado:
        escribible = False
    check("las herramientas de archivos no pueden editar mcp_servidores.json", not escribible)

tmp.cleanup()
print("\n" + "=" * 60)
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("TODAS LAS PRUEBAS DE MCP PASARON")
