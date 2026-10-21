"""
Pruebas de la interfaz: ventana de Ajustes, asistente de bienvenida y ventana principal.

    python test_interfaz.py

Construye las ventanas OCULTAS (no aparece nada en pantalla), cambia sus campos por codigo
como lo haria una persona y comprueba que se guarde y se aplique. Necesita un entorno
grafico; si no hay, se omite. No toca tu configuracion ni tu clave: todo en carpetas temporales.
"""
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

import tkinter

try:
    probe = tkinter.Tk()
    probe.destroy()
except tkinter.TclError:
    print("Sin entorno grafico: se omiten las pruebas de interfaz.")
    sys.exit(0)

import customtkinter as ctk

import hashlib
import numpy as np

import ajustes
import ajustes_ui
import memoria
import recordatorios
import vista
import bienvenida_ui
import config
import mcp_cliente
import nube

fallos = []


def check(descripcion, condicion):
    if not condicion:
        fallos.append(descripcion)
    print(f"  [{'OK ' if condicion else 'FALLA'}] {descripcion}")


tmp = tempfile.TemporaryDirectory()
carpeta = Path(tmp.name)
parches = [
    mock.patch.object(config, "PROYECTO", carpeta),
    mock.patch.object(config, "CARPETA_TRABAJO", carpeta),
    mock.patch.object(config, "MEMORIA_DB", carpeta / "memoria.db"),
    mock.patch.object(ajustes, "ARCHIVO", carpeta / "config_local.json"),
    mock.patch.object(nube, "ARCHIVO_KEY", carpeta / "openrouter.key"),
    mock.patch.object(ajustes_ui.VentanaAjustes, "_traer_al_frente", lambda self: None),
    mock.patch.object(bienvenida_ui.AsistenteBienvenida, "after", lambda self, ms, f=None, *a: None if f is None else ctk.CTkToplevel.after(self, ms, f, *a)),
]
for p in parches:
    p.start()
config.recargar()
adm = mcp_cliente.Administrador(carpeta / "mcp_servidores.json")
mcp_cliente._administrador = adm

ctk.set_appearance_mode("dark")
raiz = ctk.CTk()
raiz.withdraw()


def bombear(segundos=0.4):
    limite = time.time() + segundos
    while time.time() < limite:
        raiz.update()
        time.sleep(0.03)


def oculta(ventana):
    ventana.withdraw()
    bombear(0.1)
    return ventana


print("=== Ajustes: todas las paginas se construyen ===")
av = oculta(ajustes_ui.VentanaAjustes(raiz, al_guardar=lambda: avisos.append("guardado"), al_reiniciar=lambda: avisos.append("reinicio")))
avisos = []
for clave, nombre in av.PAGINAS:
    try:
        av._ir_a(clave)
        bombear(0.2)
        ok = True
    except Exception as e:
        ok = False
        print("      ", clave, type(e).__name__, e)
    check(f"la pagina «{nombre}» se construye", ok)

print("\n=== Ajustes: guardar lo de «Tú» ===")
av._ir_a("tu")
av.e_usuario.delete(0, "end"); av.e_usuario.insert(0, "Lucía")
av.s_trato.set("Usted")
av.m_tono.set("Formal")
av._actualizar_vista()
av.c_estilo.insert("1.0", "Usa ejemplos de cocina.")
av.c_perfil.insert("1.0", "Tiene un gato llamado Miso.")
av._actualizar_vista()
check("la vista previa cambia al instante con trato, tono y texto propio",
      "usted" in av.t_vista.cget("text") and "cocina" in av.t_vista.cget("text") and "Formal" in config.TONOS["formal"][0])
av._guardar()
bombear()
guardado = ajustes.cargar()
check("se guarda el nombre", guardado.get("usuario") == "Lucía")
check("se guardan trato y tono", guardado.get("trato") == "usted" and guardado.get("tono") == "formal")
check("se guardan las instrucciones y el perfil", "cocina" in guardado.get("estilo", "") and "Miso" in guardado.get("perfil", ""))
check("y se aplica al instante (config.py ya lo sabe)", config.USUARIO == "Lucía" and config.TRATO == "usted")
check("la interfaz principal es avisada para actualizarse", avisos == ["guardado"])
check("un cambio que no pide reinicio no ofrece reiniciar", not av.boton_reiniciar.winfo_ismapped())

print("\n=== Ajustes: un valor invalido no se guarda ===")
antes = (carpeta / "config_local.json").read_text(encoding="utf-8")
av.e_usuario.delete(0, "end"); av.e_usuario.insert(0, "x" * 200)
av._guardar()
check("muestra el error en rojo", "demasiado largo" in av.estado.cget("text"))
check("y NO cambia el archivo", (carpeta / "config_local.json").read_text(encoding="utf-8") == antes)
av.e_usuario.delete(0, "end"); av.e_usuario.insert(0, "Lucía")

print("\n=== Ajustes: equipo, voz, nube ===")
av._ir_a("equipo")
av.m_perfil.set(ajustes_ui.NOMBRES_PERFIL["basico"])
av._perfil_cambiado()
check("elegir un perfil muestra su descripcion", "qwen3:4b" in av.t_perfil.cget("text"))
av._guardar()
check("el perfil elegido se guarda y se aplica", ajustes.cargar().get("equipo") == "basico" and config.EQUIPO == "basico" and config.MODELO_CHAT == "qwen3:4b")
check("cambiar el equipo ofrece reiniciar", av.estado.cget("text").lower().count("reinici") >= 1)
av.m_perfil.set(ajustes_ui.NOMBRES_PERFIL["estandar_8gb"])
av._guardar()
av._sugerido = "laptop_rtx4060"
av._usar_sugerencia()
check("«Usar la sugerencia» cambia el perfil elegido", av.m_perfil.get() == ajustes_ui.NOMBRES_PERFIL["laptop_rtx4060"])
av._mostrar_deteccion(True, {"gpu": "NVIDIA GeForce RTX 4060 Laptop GPU", "vram_gb": 8.0, "ram_gb": 24.0,
                             "sugerido": "laptop_rtx4060", "motivo": "x"})
check("la deteccion se muestra con la tarjeta y la RAM", "4060" in av.t_deteccion.cget("text") and "24" in av.t_deteccion.cget("text"))

av._ir_a("voz")
av.sl_velocidad.set(1.2)
av.v_vad.set(False)
av._guardar()
check("la velocidad de la voz se guarda y se aplica", config.VELOCIDAD_VOZ == 1.2 and ajustes.cargar().get("velocidad_voz") == 1.2)
check("el detector de voz se puede apagar desde la interfaz", config.USAR_VAD is False)

av._ir_a("nube")
av.e_key.insert(0, "sk-or-v1-" + "ab12cd34" * 4)
av._guardar_key()
check("la clave se guarda desde la interfaz", ajustes.hay_key())
check("y el cuadro se vacia (no se deja la clave a la vista)", av.e_key.get() == "")
av._quitar_key()
check("se puede quitar", not ajustes.hay_key())
av.e_key.insert(0, "corta")
av._guardar_key()
check("una clave que no parece clave se rechaza con un mensaje", "no parece" in av.estado.cget("text"))

av._ir_a("boveda")
av.e_boveda.insert(0, str(carpeta / "no_existe"))
av._estado_boveda()
check("avisa si la carpeta de la boveda no existe", "no existe" in av.t_boveda.cget("text"))
(carpeta / "boveda").mkdir()
av.e_boveda.delete(0, "end"); av.e_boveda.insert(0, str(carpeta / "boveda"))
av._estado_boveda()
check("avisa si falta el indice de busqueda", "índice" in av.t_boveda.cget("text"))

print("\n=== Ajustes: herramientas externas (con un servidor MCP real) ===")
SERVIDOR = str(Path(__file__).resolve().parent / "mcp_servidor_de_prueba.py")
adm.agregar("prueba", {"nombre": "Servidor de prueba", "comando": sys.executable, "args": [SERVIDOR]})
av._ir_a("externas")
av._firma_externas = None
av._pintar_externas()
check("el servidor aparece apagado", adm.estado_servidores()[0]["estado"] == "detenido")
av._activar_servidor("prueba", True)
adm.esperar_listo(60)
bombear(0.3)
av._firma_externas = None
av._pintar_externas()
check("al activarlo se conecta", adm.estado_servidores()[0]["estado"] == "conectado")


def _recorrer(w):
    for h in w.winfo_children():
        yield h
        yield from _recorrer(h)


etiquetas = [w.cget("text") for w in _recorrer(av.f_externas) if isinstance(w, ctk.CTkLabel)]
check("ve las herramientas del servidor", any("sumar" in t for t in etiquetas) and any("eco" in t for t in etiquetas))
check("todas nacen bloqueadas", all(h["politica"] == "bloquear" for h in adm.estado_servidores()[0]["herramientas"]))
adm.fijar_politica("prueba", "sumar", "permitir")
check("cambiar la politica llega al modelo", [e["function"]["name"] for e in adm.esquemas()] == ["mcp_prueba_sumar"])
av._activar_servidor("prueba", False)
adm.detener_todo(10)

n_antes = len(adm.servidores)
av._agregar_plantilla("navegador")
check("la plantilla del navegador se añade (apagada)", "navegador" in adm.servidores and not adm.servidores["navegador"]["activo"])

dialogo = oculta(ajustes_ui.DialogoServidor(av, lambda: None))
dialogo.e_nombre.insert(0, "Malo")
dialogo.e_comando.insert(0, "python; rm -rf ~")
dialogo._crear()
check("el formulario rechaza un comando con simbolos de shell", "símbolos de shell" in dialogo.t_error.cget("text") and "malo" not in adm.servidores)
dialogo.e_comando.delete(0, "end"); dialogo.e_comando.insert(0, "python")
dialogo.e_args.insert(0, "-m servidor --opcion 'con espacios'")
dialogo._crear()
check("con datos validos añade el servidor, apagado y con sus argumentos",
      "malo" in adm.servidores and adm.servidores["malo"]["args"] == ["-m", "servidor", "--opcion", "con espacios"]
      and not adm.servidores["malo"]["activo"])

print("\n=== Ajustes: memoria, iniciativa y vista ===")
def vector_falso(texto):
    v = np.zeros(128, dtype=np.float32)
    for palabra in texto.lower().split():
        v[int(hashlib.md5(palabra.encode()).hexdigest(), 16) % 128] += 1
    return v
memoria._embed = vector_falso
memoria.guardar("tiene un gato llamado Miso", "dato")
memoria.guardar("le encanta el cafe con leche por las mananas", "dato")
memoria.guardar("le encanta el cafe con leche en las mananas", "dato")
av2 = oculta(ajustes_ui.VentanaAjustes(raiz))
av2._ir_a("memoria")
bombear(0.3)
filas = [w for w in _recorrer(av2.f_memoria) if isinstance(w, ctk.CTkLabel) and "Miso" in w.cget("text")]
check("la pagina de memoria lista los recuerdos", len(filas) == 1)
check("y muestra las estadisticas", "3 recuerdos" in av2.t_memoria_stats.cget("text"))
av2.vista_memoria.set("Duplicados"); av2._pintar_memoria(); bombear(1.0)
textos = [w.cget("text") for w in _recorrer(av2.f_memoria) if isinstance(w, ctk.CTkLabel)]
check("en «Duplicados» propone los dos del cafe (y no toca nada)", sum("cafe con leche" in t for t in textos) == 2 and len(memoria.listar()) == 3)
pares = memoria.candidatos_duplicados()
av2._fusionar(pares[0]["a"]["id"], pares[0]["b"]["id"])
check("«Conservar este» fusiona: queda uno solo", len(memoria.listar()) == 2)
miso = next(r for r in memoria.listar() if "Miso" in r["contenido"])
av2._olvidar(miso["id"])
check("«Olvidar» borra solo ese", all("Miso" not in r["contenido"] for r in memoria.listar()) and len(memoria.listar()) == 1)
av2.v_resumen.set(True)
av2._ir_a("iniciativa")
av2.e_rec_texto.insert(0, "sacar la pizza"); av2.e_rec_min.insert(0, "15")
av2._programar()
check("se programa un recordatorio desde la ventana", [r["texto"] for r in recordatorios.listar()] == ["sacar la pizza"])
check("y aparece en la lista", any("sacar la pizza" in w.cget("text") for w in _recorrer(av2.f_recordatorios) if isinstance(w, ctk.CTkLabel)))
av2.e_rec_texto.insert(0, "x"); av2.e_rec_min.insert(0, "pronto")
av2._programar()
check("minutos que no son numero se rechazan con mensaje", "número" in av2.estado.cget("text"))
av2._cancelar_recordatorio(recordatorios.listar()[0]["id"])
check("se cancela desde la ventana", recordatorios.listar() == [])
av2.v_saludo.set(True)
av2._ir_a("vista")
check("la vista viene apagada y pidiendo permiso en la pantalla", av2.v_vista.get() is False and av2.v_vista_pregunta.get() is True)
av2.v_vista.set(True)
with mock.patch.object(vista, "comprobar_modelo", return_value=(True, "Error de compilacion NOX-4821 (3 s)")):
    av2._comprobar_vision(); bombear(0.8)
check("«Comprobar que funciona» usa la imagen de prueba y lo muestra", "Funciona" in av2.t_resultado_vision.cget("text"))
av2._guardar()
check("se guardan los tres ajustes nuevos y se aplican",
      config.MEMORIA_RESUMEN_SESION and config.SALUDO_MATUTINO and config.VISTA_ACTIVA and ajustes.cargar().get("vista_activa") is True)
av2.v_vista.set(False); av2.v_saludo.set(False); av2.v_resumen.set(False); av2._guardar()
check("y se pueden volver a apagar", not (config.MEMORIA_RESUMEN_SESION or config.SALUDO_MATUTINO or config.VISTA_ACTIVA))
av2._cerrar()

print("\n=== Ajustes: cerrar sin guardar restaura lo probado ===")
config.VELOCIDAD_VOZ = 1.0
av._velocidad_original = 1.0
av._ir_a("voz")
av.sl_velocidad.set(1.4)
av._probar_voz = lambda: setattr(config, "VELOCIDAD_VOZ", 1.4)
av._probar_voz()
av._cerrar()
check("la velocidad de prueba no se queda si no guardas", config.VELOCIDAD_VOZ == 1.0)

print("\n=== Asistente de bienvenida ===")
(carpeta / "config_local.json").unlink()
config.recargar()
check("sin configuracion, hace falta la bienvenida", ajustes.necesita_bienvenida())
terminado = []
with mock.patch.object(ajustes, "detectar_equipo", return_value={"gpu": "RTX 4060", "vram_gb": 8.0, "ram_gb": 24.0, "sugerido": "laptop_rtx4060", "motivo": "ok"}), \
        mock.patch("modelos.instalados", return_value=[]), mock.patch("modelos.ollama_activo", return_value=True):
    w = oculta(bienvenida_ui.AsistenteBienvenida(raiz, al_terminar=lambda: terminado.append(True)))
    check("arranca en el primer paso con el nombre del sistema sugerido", w.paso == 0 and w.e_usuario.get() == config.USUARIO)
    w.e_usuario.delete(0, "end"); w.e_usuario.insert(0, "Sofía")
    w._siguiente()
    check("avanza al paso de trato y tono", w.paso == 1)
    w.s_trato.set("Usted"); w.v_trato.set("Usted"); w.v_tono.set("detallado")
    w.c_estilo.insert("1.0", "Explícame con calma.")
    w._siguiente()
    bombear(0.8)
    check("el paso del equipo detecta y sugiere el perfil", w.paso == 2 and w.v_equipo.get() == ajustes_ui.NOMBRES_PERFIL["laptop_rtx4060"])
    etiquetas = [x.cget("text") for x in _recorrer(w.f_modelos) if isinstance(x, ctk.CTkLabel)]
    check("muestra los modelos que faltan", any("✗" in t for t in etiquetas))
    w._atras()
    check("se puede volver atras", w.paso == 1)
    w._siguiente(); bombear(0.3)
    w._siguiente()
    w.v_voz.set(False); w.v_nube.set(False)
    w._siguiente()
    check("llega al resumen con el nombre", w.paso == 4)
    w._siguiente()
bombear(0.3)
guardado = ajustes.cargar()
check("al terminar se guarda todo junto", guardado.get("usuario") == "Sofía" and guardado.get("trato") == "usted"
      and guardado.get("tono") == "detallado" and guardado.get("equipo") == "laptop_rtx4060")
check("incluidas las instrucciones, la voz y la nube", "calma" in guardado.get("estilo", "") and guardado.get("voz_activa") is False and guardado.get("usar_nube") is False)
check("queda marcada como hecha: no vuelve a salir", not ajustes.necesita_bienvenida() and terminado == [True])
check("y se aplica al instante", config.USUARIO == "Sofía" and config.EQUIPO == "laptop_rtx4060")

(carpeta / "config_local.json").unlink()
config.recargar()
w2 = oculta(bienvenida_ui.AsistenteBienvenida(raiz))
w2._cerrar()
check("cerrarla a la mitad NO la marca como hecha (se vuelve a ofrecer)", ajustes.necesita_bienvenida())
w3 = oculta(bienvenida_ui.AsistenteBienvenida(raiz, al_terminar=lambda: None))
w3._saltar()
check("«Configurar después» la marca como hecha, con los valores por defecto", not ajustes.necesita_bienvenida())

print("\n=== Ventana principal ===")
import gui
with mock.patch("nucleo.verificar_ollama", return_value=(True, "ok")):
    principal = gui.VentanaNox()
    principal.withdraw()
    bombear(0.5)
    check("tiene el boton de Ajustes y no abre la bienvenida si ya se hizo", principal.ajustes_abiertos is None)
    with mock.patch.object(ajustes_ui.VentanaAjustes, "__init__", lambda self, *a, **k: None), \
            mock.patch.object(ajustes_ui.VentanaAjustes, "winfo_exists", lambda self: True), \
            mock.patch.object(ajustes_ui.VentanaAjustes, "lift", lambda self: None), \
            mock.patch.object(ajustes_ui.VentanaAjustes, "focus_force", lambda self: None):
        principal._abrir_ajustes()
        primera = principal.ajustes_abiertos
        principal._abrir_ajustes()
        check("abrir Ajustes dos veces no abre dos ventanas", principal.ajustes_abiertos is primera)
    config.recargar()
    principal.conversacion.actualizar_prompt()
    check("el prompt de la conversacion se actualiza sin borrar el chat",
          principal.conversacion.mensajes[0]["role"] == "system" and config.USUARIO in principal.conversacion.mensajes[0]["content"])
    principal._al_cerrar()

tmp.cleanup()
for p in parches:
    p.stop()
config.recargar()
try:
    raiz.destroy()
except Exception:
    pass

print("\n" + "=" * 60)
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("TODAS LAS PRUEBAS DE INTERFAZ PASARON")
