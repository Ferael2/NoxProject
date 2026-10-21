"""
Pruebas de la compatibilidad Linux / Windows.

    python test_plataforma.py

Lo que depende del sistema en que se corre se prueba de verdad. Lo de OTRO sistema se
SIMULA: PowerShell, el registro de Windows y el menu inicio se reemplazan por datos falsos
para comprobar la logica de Nox (armar comandos, filtrar, rechazar). Eso NO prueba que
Windows responda como se espera; para eso hay que correr Nox en una maquina con Windows
(python chequeo.py y despues usarlo).
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

import config
import escanear_programas
import plataforma
import seguridad
import sistema
import so_linux
import so_windows
import voz
from seguridad import Rechazado

fallos = []


def check(descripcion, condicion):
    if not condicion:
        fallos.append(descripcion)
    print(f"  [{'OK ' if condicion else 'FALLA'}] {descripcion}")


def rechaza(fn) -> bool:
    try:
        fn()
    except Rechazado:
        return True
    return False


class PowerShellFalso:
    """Reemplaza so_windows._powershell: guarda los scripts y devuelve lo que se le diga."""

    def __init__(self, salida=""):
        self.salida = salida
        self.scripts = []

    def __call__(self, script, timeout):
        self.scripts.append(script)
        return subprocess.CompletedProcess([], 0, stdout=self.salida, stderr="")


print("=== SISTEMA DETECTADO ===")
check(f"se detecta exactamente un sistema ({plataforma.NOMBRE_SO})",
      sum([plataforma.ES_WINDOWS, plataforma.ES_LINUX, plataforma.ES_MAC]) == 1)
check("sistema.py usa el modulo de este sistema",
      sistema.so is (so_windows if plataforma.ES_WINDOWS else so_linux))
check("Documentos y Escritorio existen como carpetas",
      config.DOCUMENTOS.is_dir() and config.ESCRITORIO.is_dir())
check("config.BOVEDA es una ruta (existe o no: es opcional)", isinstance(config.BOVEDA, Path))

print("\n=== LAS DOS INTERFACES SON IGUALES ===")
publico = ["AGRUPA_MISMA_APP", "ACCIONES_MULTIMEDIA", "validar_destino", "abrir",
           "ventanas_abiertas", "cerrar_ventanas", "cerrar_a_la_fuerza",
           "juego_corriendo", "tecla_multimedia", "ejecutar_consulta"]
for modulo in (so_linux, so_windows):
    faltan = [n for n in publico if not hasattr(modulo, n)]
    check(f"{modulo.__name__} tiene toda la interfaz", not faltan)
check("las acciones multimedia son las mismas en los dos",
      set(so_linux.ACCIONES_MULTIMEDIA) == set(so_windows.ACCIONES_MULTIMEDIA))

print("\n=== WINDOWS (simulado): ventanas ===")
un_solo = json.dumps({"ProcessName": "notepad", "Id": 4242, "MainWindowTitle": "notas.txt - Bloc de notas"})
varios = json.dumps([
    {"ProcessName": "chrome", "Id": 10, "MainWindowTitle": "Google"},
    {"ProcessName": "chrome", "Id": 11, "MainWindowTitle": "YouTube"},
    {"ProcessName": "explorer", "Id": 12, "MainWindowTitle": "Documentos"},
])
with mock.patch.object(so_windows, "_powershell", PowerShellFalso(un_solo)):
    v = so_windows.ventanas_abiertas()
check("una sola ventana (PowerShell devuelve un objeto, no una lista)",
      v == [{"id": 4242, "titulo": "notas.txt - Bloc de notas", "app": "notepad"}])
with mock.patch.object(so_windows, "_powershell", PowerShellFalso("")):
    check("sin ventanas no falla", so_windows.ventanas_abiertas() == [])
with mock.patch.object(so_windows, "_powershell", PowerShellFalso("esto no es json")):
    check("salida rota no falla", so_windows.ventanas_abiertas() == [])

ps = PowerShellFalso()
with mock.patch.object(so_windows, "_powershell", ps):
    error = so_windows.cerrar_ventanas([{"id": 10, "titulo": "", "app": "chrome"},
                                        {"id": 11, "titulo": "", "app": "chrome"}])
check("cerrar pide CloseMainWindow (como la X) y no mata",
      error is None and "CloseMainWindow" in ps.scripts[0] and "Stop-Process" not in ps.scripts[0])
check("solo se meten numeros en el script (sin inyeccion)", "10,11" in ps.scripts[0])

ps = PowerShellFalso()
with mock.patch.object(so_windows, "_powershell", ps):
    n, _ = so_windows.cerrar_a_la_fuerza(
        [{"id": 10, "titulo": "", "app": "chrome"}, {"id": 12, "titulo": "", "app": "explorer"}],
        {"chrome"})
check("forzar nunca incluye a un proceso intocable (explorer)",
      n == 1 and "Stop-Process -Id 10 -Force" in ps.scripts[0])

print("\n=== WINDOWS (simulado): cerrar_programa de punta a punta ===")
fake = PowerShellFalso(varios)
with mock.patch.object(sistema, "so", so_windows), mock.patch.object(so_windows, "_powershell", fake):
    r = sistema.cerrar_programa("chrome")
    check("dos ventanas de Chrome (un solo programa) se cierran juntas", r.startswith("Le pedi a") and "10,11" in fake.scripts[-1])
    r = sistema.cerrar_programa("explorer")
    check("el explorador de archivos no se puede cerrar", r.startswith("No encuentro"))
    r = sistema.cerrar_programa("programa que no existe")
    check("un programa que no esta abierto da un mensaje claro", "No encuentro" in r)
    r = sistema.listar_abiertos()
    check("listar abiertos muestra chrome", "Google" in r or "chrome" in r.lower())

print("\n=== WINDOWS (simulado): abrir programas ===")
with tempfile.TemporaryDirectory() as tmp:
    menu = Path(tmp) / "Programs"
    (menu / "Mozilla").mkdir(parents=True)
    (menu / "Mozilla" / "Firefox.lnk").write_text("x")
    (menu / "Desinstalar Firefox.lnk").write_text("x")
    (menu / "Notas.lnk").write_text("x")
    fuera = Path(tmp) / "Descargas"
    fuera.mkdir()
    (fuera / "trampa.lnk").write_text("x")
    (fuera / "virus.exe").write_text("x")

    with mock.patch.object(escanear_programas, "MENUS_INICIO", [menu]):
        encontrados = escanear_programas.escanear_menu_inicio()
        check("el escaner de Windows encuentra los .lnk del menu inicio",
              {"firefox", "notas"} <= set(encontrados))
        check("el escaner de Windows descarta 'Desinstalar'", "desinstalar firefox" not in encontrados)
        check("acceso directo del menu inicio es valido",
              so_windows.validar_destino(encontrados["firefox"]) == encontrados["firefox"]["destino"])
        check(".lnk fuera del menu inicio se rechaza",
              rechaza(lambda: so_windows.validar_destino({"nombre": "x", "destino": str(fuera / "trampa.lnk")})))
        check(".exe fuera del menu inicio se rechaza",
              rechaza(lambda: so_windows.validar_destino({"nombre": "x", "destino": str(fuera / "virus.exe")})))
        check("un .bat se rechaza",
              rechaza(lambda: so_windows.validar_destino({"nombre": "x", "destino": str(menu / "x.bat")})))
        check("URL de Steam valida pasa",
              so_windows.validar_destino({"nombre": "x", "destino": "steam://rungameid/1086940"}) == "steam://rungameid/1086940")
        check("URL de Steam con algo de mas se rechaza",
              rechaza(lambda: so_windows.validar_destino({"nombre": "x", "destino": "steam://rungameid/1;calc"})))

print("\n=== CATALOGO: se regenera si es de otro sistema ===")
catalogo_linux = {"brave": {"nombre": "Brave", "destino": "/usr/share/applications/brave.desktop", "tipo": "programa"}}
catalogo_windows = {"brave": {"nombre": "Brave", "destino": r"C:\ProgramData\x\Brave.lnk", "tipo": "programa"}}
solo_steam = {"juego": {"nombre": "J", "destino": "steam://rungameid/1", "tipo": "juego"}}
with mock.patch.object(plataforma, "ES_WINDOWS", False):
    check("en Linux: un catalogo de Linux sirve", escanear_programas.catalogo_es_de_este_so(catalogo_linux))
    check("en Linux: un catalogo de Windows se descarta", not escanear_programas.catalogo_es_de_este_so(catalogo_windows))
    check("en Linux: un catalogo solo de Steam sirve", escanear_programas.catalogo_es_de_este_so(solo_steam))
with mock.patch.object(plataforma, "ES_WINDOWS", True):
    check("en Windows: un catalogo de Windows sirve", escanear_programas.catalogo_es_de_este_so(catalogo_windows))
    check("en Windows: un catalogo de Linux se descarta", not escanear_programas.catalogo_es_de_este_so(catalogo_linux))

with tempfile.TemporaryDirectory() as tmp:
    ajeno = Path(tmp) / "programas.json"
    ajeno.write_text(json.dumps(catalogo_windows if plataforma.ES_LINUX else catalogo_linux))
    with mock.patch.object(sistema, "CATALOGO", ajeno), mock.patch.object(sistema, "_programas", None), \
            mock.patch.object(escanear_programas, "SALIDA", ajeno):
        regenerado = sistema.cargar_catalogo()
    check("un programas.json de otro sistema se reemplaza por uno nuevo",
          escanear_programas.catalogo_es_de_este_so(regenerado) and regenerado != (
              catalogo_windows if plataforma.ES_LINUX else catalogo_linux))
    with mock.patch.object(sistema, "CATALOGO", Path(tmp) / "no_existe.json"), \
            mock.patch.object(sistema, "_programas", None), \
            mock.patch.object(escanear_programas, "SALIDA", Path(tmp) / "nuevo.json"):
        check("sin programas.json se arma uno", isinstance(sistema.cargar_catalogo(), dict))

print("\n=== WINDOWS (simulado): juegos, multimedia y consultas ===")
catalogo = {"hades": {"nombre": "Hades", "destino": "steam://rungameid/1145360", "tipo": "juego"}}
with mock.patch.object(so_windows, "_appid_de_steam_en_curso", return_value="1145360"):
    check("detecta el juego por el RunningAppID de Steam", so_windows.juego_corriendo(catalogo) == "Hades")
with mock.patch.object(so_windows, "_appid_de_steam_en_curso", return_value="431960"), \
        mock.patch.object(so_windows, "_powershell", PowerShellFalso("")):
    check("ignora Wallpaper Engine", so_windows.juego_corriendo(catalogo) is None)
with mock.patch.object(so_windows, "_appid_de_steam_en_curso", return_value=None), \
        mock.patch.object(so_windows, "_powershell", PowerShellFalso("svchost\nHades\nsteam\n")):
    check("sin Steam, detecta el juego por el nombre del proceso", so_windows.juego_corriendo(catalogo) == "Hades")

ps = PowerShellFalso()
with mock.patch.object(so_windows, "_powershell", ps):
    error = so_windows.tecla_multimedia("subir_volumen", 3)
check("subir volumen x3 manda la tecla 175 tres veces",
      error is None and ps.scripts[0].count("[char]175") == 3)

ps = PowerShellFalso("Id Name\n 1 foo")
with mock.patch.object(so_windows, "_powershell", ps):
    r = so_windows.ejecutar_consulta("Get-Process | Select-Object -First 3")
check("una consulta valida llega a PowerShell", "Get-Process" in ps.scripts[0] and "foo" in r)
ps = PowerShellFalso()
with mock.patch.object(so_windows, "_powershell", ps):
    r = so_windows.ejecutar_consulta("Remove-Item C:\\x")
check("una consulta peligrosa no llega a PowerShell", not ps.scripts and r.startswith("Rechazado"))

print("\n=== PLATAFORMA (simulado) ===")
with mock.patch.object(plataforma, "ES_WINDOWS", True):
    check("Windows: los procesos lanzados salen desprendidos", "creationflags" in plataforma.kwargs_desprendido())
    check("Windows: PowerShell se lanza sin ventana", plataforma.kwargs_sin_ventana().get("creationflags"))
with mock.patch.object(plataforma, "ES_WINDOWS", False):
    check("Linux: los procesos lanzados salen en sesion propia", plataforma.kwargs_desprendido() == {"start_new_session": True})
    check("Linux: no hay banderas de ventana", plataforma.kwargs_sin_ventana() == {})

llamadas = []
with mock.patch.object(voz.subprocess if hasattr(voz, "subprocess") else subprocess, "Popen") as popen:
    popen.return_value.poll.return_value = 0
    with mock.patch.object(plataforma, "ES_WINDOWS", True):
        voz._hablar_respaldo("Hola 'mundo'; Remove-Item x")
    comando = popen.call_args.args[0]
    entorno = popen.call_args.kwargs.get("env") or {}
check("voz de Windows: el texto va en una variable, no dentro del script",
      "Remove-Item" not in " ".join(comando) and entorno.get("NOX_TEXTO") == "Hola 'mundo'; Remove-Item x")

print("\n" + "=" * 60)
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("TODAS LAS PRUEBAS DE PLATAFORMA PASARON")
