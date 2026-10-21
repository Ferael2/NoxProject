"""
Pruebas de los nombres mal escuchados: "cierra desktop" cuando se dijo "Vesktop".

    python test_nombres.py

Whisper se equivoca con los nombres propios raros. Nox lo compensa de dos formas: le pasa a
Whisper el vocabulario de lo que de verdad usas (vocabulario.py) y, si aun asi llega mal,
acepta el programa que mas se parece (sistema.py) y lo avisa. Todo con un catalogo falso.
"""
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

import config
import sistema
import vocabulario

fallos = []


def check(descripcion, condicion):
    if not condicion:
        fallos.append(descripcion)
    print(f"  [{'OK ' if condicion else 'FALLA'}] {descripcion}")


def entrada(nombre, ejecutable="", tipo="programa", alias=()):
    return {"nombre": nombre, "destino": f"/usr/share/applications/{nombre}.desktop", "tipo": tipo,
            "ejecutable": ejecutable, "alias": list(alias)}


CATALOGO = {
    "vesktop": entrada("Vesktop", "vesktop"),
    "discord": entrada("Discord", "discord"),
    "brave": entrada("Brave", "brave", alias=["navegador web"]),
    "spotify": entrada("Spotify", "spotify"),
    "visual studio code": entrada("Visual Studio Code", "code"),
    "kcalc": entrada("KCalc", "kcalc", alias=["calculadora"]),
    "calendario": entrada("Calendario", "korganizer"),
    "libreoffice calc": entrada("LibreOffice Calc"), "libreoffice writer": entrada("LibreOffice Writer"),
    "qt assistant": entrada("Qt Assistant"), "cachyos hello": entrada("CachyOS Hello"),
    "hades ii": entrada("Hades II", tipo="juego"),
}
tmp = tempfile.TemporaryDirectory()
parches = [mock.patch.object(sistema, "_programas", CATALOGO),
           mock.patch.object(config, "CARPETA_TRABAJO", Path(tmp.name))]
for p in parches:
    p.start()


def mejor(dicho):
    r = sistema.buscar_programa_aproximado(dicho)
    return r[0][1]["nombre"] if r else None


print("=== Parecidos: lo que Whisper suele escribir mal ===")
check("«desktop» -> Vesktop (el caso real)", mejor("desktop") == "Vesktop")
check("«vesk top» (partido en dos) -> Vesktop", mejor("vesk top") == "Vesktop")
check("«spotifai» -> Spotify", mejor("spotifay") == "Spotify")
check("«discor» -> Discord", mejor("discor") == "Discord")
check("una parte exacta del nombre ya la encuentra la busqueda normal («studio code»)",
      [d["nombre"] for _, d in sistema.buscar_programa("studio code")] == ["Visual Studio Code"])

print("\n=== Lo que NO debe confundirse ===")
check("palabras sin relacion no coinciden con nada", all(mejor(x) is None for x in ("banana", "mesa", "refrigerador", "xyz")))
check("palabras cortas no coinciden (casi todo se parece a algo)", all(mejor(x) is None for x in ("abc", "de", "kde")))
check("«calendario» no se confunde con «calculadora»", mejor("calendario") in (None, "Calendario"))

print("\n=== abrir_programa ===")
abiertos = []
with mock.patch.object(sistema.so, "abrir", side_effect=lambda d: abiertos.append(d["nombre"])):
    r = sistema.abrir_programa("desktop")
    check("«abre desktop» abre Vesktop", abiertos == ["Vesktop"])
    check("y lo dice, para que se vea la suposicion", "supuse que es Vesktop" in r)
    abiertos.clear()
    r = sistema.abrir_programa("Brave")
    check("un nombre exacto sigue funcionando igual, sin avisos", abiertos == ["Brave"] and "supuse" not in r)
    abiertos.clear()
    r = sistema.abrir_programa("refrigerador")
    check("algo que no existe ni se parece sigue diciendo que no lo tiene", not abiertos and "No tengo" in r)
CATALOGO["vesktops"] = entrada("Vesktops", "vesktops")
with mock.patch.object(sistema.so, "abrir", side_effect=lambda d: abiertos.append(d["nombre"])):
    abiertos.clear()
    r = sistema.abrir_programa("vesktop s")
    check("si hay dos igual de parecidos, pregunta en vez de adivinar", not abiertos and "¿Cuál?" in r)
del CATALOGO["vesktops"]

print("\n=== cerrar_programa ===")
ventanas = [{"id": "1", "titulo": "Vesktop", "app": "vesktop"}, {"id": "2", "titulo": "Brave", "app": "brave-browser"}]
cerradas = []
with mock.patch.object(sistema, "ventanas_abiertas", return_value=ventanas), \
        mock.patch.object(sistema.so, "cerrar_ventanas", side_effect=lambda v: cerradas.append(v[0]["id"]) and None):
    r = sistema.cerrar_programa("desktop")
    check("«cierra desktop» cierra la ventana de Vesktop", cerradas == ["1"])
    check("y avisa lo que entendio", "supuse" in r and "Vesktop" in r)
    cerradas.clear()
    r = sistema.cerrar_programa("brave")
    check("un nombre exacto cierra lo de siempre, sin avisos", cerradas == ["2"] and "supuse" not in r)
    cerradas.clear()
    r = sistema.cerrar_programa("refrigerador")
    check("si nada se parece, no cierra NADA y lista lo abierto", not cerradas and "No encuentro" in r)

print("\n=== Aprender lo que usas ===")
check("abrir y cerrar con exito ya fueron anotando lo usado", "Vesktop" in sistema.programas_mas_usados())
sistema._archivo_uso().unlink()
check("sin historial no hay frecuentes", sistema.programas_mas_usados() == [])
for n in ("Vesktop", "Vesktop", "Vesktop", "Spotify"):
    sistema._registrar_uso(n)
check("lo mas usado va primero", sistema.programas_mas_usados() == ["Vesktop", "Spotify"])
check("un archivo de uso roto no tumba nada", (sistema._archivo_uso().write_text("{ roto") or True) and sistema.programas_mas_usados() == [])
sistema._registrar_uso("Vesktop")
check("y se recupera solo", sistema.programas_mas_usados() == ["Vesktop"])

print("\n=== Vocabulario para Whisper ===")
vocabulario._cache = None
with mock.patch.object(sistema, "ventanas_abiertas", return_value=[{"id": "2", "titulo": "Brave", "app": "brave"}]), \
        mock.patch.object(vocabulario, "_de_boveda", return_value=[]):
    v = vocabulario.construir()
check("lo que usas aparece al principio", v.split("sobre: ")[1].startswith("Vesktop"))
check("lo que tienes abierto tambien sube", v.index("Brave") < v.index("Hades II") if "Hades II" in v else True)
check("las herramientas de mantenimiento no ocupan lugar", "Qt Assistant" not in v and "CachyOS Hello" not in v)
check("una familia aparece una sola vez (LibreOffice)", v.count("LibreOffice") == 1)
check("cabe en el limite (900 caracteres + el encabezado)", len(v) < 960)
vocabulario._cache = None

tmp.cleanup()
for p in parches:
    p.stop()
print("\n" + "=" * 60)
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("TODAS LAS PRUEBAS DE NOMBRES PASARON")
