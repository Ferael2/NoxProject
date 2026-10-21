"""
Control de la PC: abrir programas, escribir archivos, volumen y multimedia.

Filosofia de permisos: LISTA BLANCA, no lista negra.

Una lista negra (bloquear 'Remove-Item', 'del', etc.) siempre tiene agujeros —
basta una forma de escribir el comando que no este en la lista. Aca al reves:
Nox solo puede abrir programas que esten en programas.json, y solo puede escribir
archivos en carpetas explicitamente permitidas, con extensiones explicitamente
permitidas. Todo lo demas se rechaza por defecto.
"""
import json
import re
import subprocess
import time
from pathlib import Path

import config
import escanear_programas
import plataforma
import seguridad
from seguridad import Rechazado

# Lo que cambia entre Linux y Windows (abrir y cerrar programas, ventanas, multimedia,
# consultas) vive en un modulo por sistema con la misma interfaz. Ver so_linux.py.
if plataforma.ES_WINDOWS:
    import so_windows as so
else:
    import so_linux as so

plataforma.configurar_salida()

CATALOGO = config.PROYECTO / "programas.json"
_programas = None

_normalizar = seguridad.normalizar


# --- Abrir programas ---

def cargar_catalogo() -> dict:
    """
    El catalogo de programas permitidos. programas.json es propio de cada maquina (tiene
    rutas de este sistema), asi que si falta, o es de otro sistema operativo, se arma de
    nuevo al momento en vez de fallar.
    """
    global _programas
    if _programas is None:
        _programas = {}
        if CATALOGO.exists():
            try:
                _programas = json.loads(CATALOGO.read_text(encoding="utf-8"))
            except ValueError:
                _programas = {}
        if not _programas or not escanear_programas.catalogo_es_de_este_so(_programas):
            try:
                _programas = escanear_programas.generar_catalogo()
            except OSError:
                _programas = {}
    return _programas


def buscar_programa(nombre: str) -> list[tuple[str, dict]]:
    """
    Busca en el catalogo por coincidencia parcial. Devuelve los candidatos
    ordenados: primero los que empiezan igual, despues los que solo contienen.
    """
    catalogo = cargar_catalogo()
    consulta = _normalizar(nombre)

    exactos, empiezan, contienen = [], [], []
    for clave, datos in catalogo.items():
        # Ademas del nombre se mira cada alias: el nombre en ingles y el generico
        # ("navegador web", "terminal").
        nombres = [clave] + datos.get("alias", [])
        if consulta in nombres:
            exactos.append((clave, datos))
        elif any(n.startswith(consulta) for n in nombres):
            empiezan.append((clave, datos))
        elif any(consulta in n for n in nombres):
            contienen.append((clave, datos))

    return exactos + empiezan + contienen


# --- Nombres mal escuchados ---
# Whisper se equivoca con los nombres propios raros: "Vesktop" sale como "desktop". Si no hay
# ninguna coincidencia exacta, se acepta la mas parecida, y se avisa para que se vea el cambio.

UMBRAL_PARECIDO = 0.8
MIN_LETRAS_PARECIDO = 4   # con menos letras casi cualquier cosa se "parece" a algo


def _parecido(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


def _mejor_parecido(consulta: str, nombres: list[str]) -> float:
    """
    Que tanto se parece lo dicho a alguno de los nombres: al nombre entero (sin espacios) o a
    cualquiera de sus palabras ("studio" dentro de "visual studio code").
    """
    consulta = consulta.replace(" ", "")
    if len(consulta) < MIN_LETRAS_PARECIDO:
        return 0.0
    mejor = 0.0
    for nombre in nombres:
        if not nombre:
            continue
        for trozo in {nombre.replace(" ", ""), *nombre.split()}:
            if len(trozo) >= MIN_LETRAS_PARECIDO:
                mejor = max(mejor, _parecido(consulta, trozo))
    return mejor


def buscar_programa_aproximado(nombre: str) -> list[tuple[str, dict, float]]:
    """Programas del catalogo que SE PARECEN a lo dicho, de mas a menos: [(clave, datos, parecido)]."""
    consulta = _normalizar(nombre)
    encontrados = []
    for clave, datos in cargar_catalogo().items():
        nombres = [clave, *datos.get("alias", []), _normalizar(datos.get("ejecutable", ""))]
        puntaje = _mejor_parecido(consulta, nombres)
        if puntaje >= UMBRAL_PARECIDO:
            encontrados.append((clave, datos, puntaje))
    return sorted(encontrados, key=lambda t: -t[2])


# --- Que programas usas (para ayudar a Whisper a oirlos) ---

def _archivo_uso() -> Path:
    return config.CARPETA_TRABAJO / "uso_programas.json"


def _registrar_uso(nombre: str):
    """Cuenta cada programa que se abre o cierra por voz o chat. No pasa nada si falla."""
    try:
        archivo = _archivo_uso()
        try:
            usos = json.loads(archivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            usos = {}
        clave = _normalizar(nombre)
        usos[clave] = {"nombre": nombre, "veces": usos.get(clave, {}).get("veces", 0) + 1}
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_text(json.dumps(usos, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def programas_mas_usados(limite: int = 15) -> list[str]:
    """Los nombres de los programas que mas se han abierto o cerrado, de mas a menos."""
    try:
        usos = json.loads(_archivo_uso().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    ordenados = sorted(usos.values(), key=lambda u: -u.get("veces", 0))
    return [u["nombre"] for u in ordenados[:limite]]


def nombre_de_catalogo(app: str) -> str:
    """El nombre bonito de una ventana ('vesktop' -> 'Vesktop'), segun el catalogo."""
    clave = _normalizar(app)
    for datos in cargar_catalogo().values():
        if clave in (_normalizar(datos.get("ejecutable", "")), _normalizar(datos["nombre"])):
            return datos["nombre"]
    return app[:1].upper() + app[1:]


def validar_destino(datos: dict):
    """
    Comprueba una entrada del catalogo y devuelve lo que se va a abrir (un comando en
    Linux, una ruta o URL en Windows). Lanza Rechazado si el destino no es de confianza.
    """
    return so.validar_destino(datos)


def abrir_programa(nombre: str) -> str:
    candidatos = buscar_programa(nombre)
    aviso = ""

    if not candidatos:
        # Sin coincidencia exacta: quiza Whisper escribio mal el nombre ("desktop" por "vesktop").
        parecidos = buscar_programa_aproximado(nombre)
        if len(parecidos) == 1 or (len(parecidos) > 1 and parecidos[0][2] - parecidos[1][2] >= 0.08):
            clave, datos, _ = parecidos[0]
            candidatos = [(clave, datos)]
            aviso = f" (Entendí «{nombre}» y supuse que es {datos['nombre']}.)"
        elif parecidos:
            opciones = ", ".join(d["nombre"] for _, d, _ in parecidos[:4])
            return f"No encuentro '{nombre}', pero se parece a: {opciones}. ¿Cuál?"

    if not candidatos:
        return (
            f"No tengo '{nombre}' en el catalogo de programas permitidos. "
            "Puedo listarte lo que si puedo abrir, o se puede correr "
            "escanear_programas.py si se instalo hace poco."
        )

    # Si hay varios y ninguno es exacto, mejor preguntar que adivinar.
    exacto = _normalizar(nombre)
    if len(candidatos) > 1 and exacto not in [candidatos[0][0]] + candidatos[0][1].get("alias", []):
        opciones = ", ".join(d["nombre"] for _, d in candidatos[:6])
        if len(candidatos) > 6:
            opciones += f" (y {len(candidatos) - 6} mas)"
        return f"Hay varias opciones para '{nombre}': {opciones}. ¿Cual de todas?"

    datos = candidatos[0][1]
    try:
        so.abrir(datos)
        _registrar_uso(datos["nombre"])
        return f"Abriendo {datos['nombre']}.{aviso}"
    except Rechazado as e:
        return str(e)
    except OSError as e:
        return f"No pude abrir {datos['nombre']}: {e}"


def listar_programas(filtro: str = "", solo_juegos: bool = False) -> str:
    catalogo = cargar_catalogo()
    consulta = _normalizar(filtro)

    items = [
        d for c, d in catalogo.items()
        if (not consulta or consulta in c)
        and (not solo_juegos or d.get("tipo") == "juego")
    ]
    if not items:
        return "Nada coincide con eso en el catalogo."

    juegos = [d["nombre"] for d in items if d.get("tipo") == "juego"]
    apps = [d["nombre"] for d in items if d.get("tipo") != "juego"]

    partes = []
    if juegos:
        partes.append("Juegos: " + ", ".join(sorted(juegos)))
    if apps:
        partes.append("Programas: " + ", ".join(sorted(apps)[:40]))
        if len(apps) > 40:
            partes.append(f"(y {len(apps) - 40} programas mas)")
    return "\n".join(partes)


# --- Cerrar programas ---

# Procesos que nunca se cierran, aunque coincidan con algo del catalogo (la lista vive en
# seguridad.py, con el resto de las decisiones de "esto se puede o no").
INTOCABLES = seguridad.INTOCABLES

# Iconos genericos del tema ("accessories-calculator"): no dicen que programa es.
ICONOS_GENERICOS = ("accessories-", "utilities-", "applications-", "preferences-", "system-")

# Solo para las pruebas de seguridad de Linux (busca procesos por nombre).
_pids_del_programa = getattr(so, "_pids_del_programa", None)


def ventanas_abiertas() -> list[dict]:
    """Ventanas abiertas: [{"id", "titulo", "app"}]. Cada sistema las averigua a su modo."""
    return so.ventanas_abiertas()


def _ventanas_cerrables() -> list[dict]:
    """Las ventanas abiertas menos la del propio Nox y las de procesos intocables."""
    return [
        v for v in ventanas_abiertas()
        if v["titulo"] != config.NOMBRE and not seguridad.es_intocable(_normalizar(v["app"]))
    ]


def _describir(ventana: dict) -> str:
    """Titulo de la ventana, mas el programa entre parentesis si el titulo no lo dice."""
    titulo, app = ventana["titulo"], ventana["app"]
    if app and _normalizar(app) not in _normalizar(titulo) and not app.startswith(ICONOS_GENERICOS):
        return f"{titulo[:60]} ({app})" if titulo else app
    return titulo[:60]


def listar_abiertos() -> str:
    """Que programas tiene abiertos ahora mismo."""
    ventanas = ventanas_abiertas()
    if not ventanas:
        return "No detecto ventanas abiertas (o este sistema no me deja verlas)."
    return "\n".join(sorted({_describir(v) for v in ventanas}))


def cerrar_programa(nombre: str, forzar: bool = False) -> str:
    """
    Cierra un programa abierto.

    Solo cierra lo que tiene una ventana abierta, y nunca procesos del sistema. Por
    defecto pide el cierre normal, que es exactamente lo mismo que apretar la X: el
    programa tiene la chance de preguntar si guardar. 'forzar' termina el proceso sin
    preguntar; se usa solo si Brian insiste o el programa no responde.

    Cerrar no es borrar: no hay ninguna via aca para eliminar archivos ni datos.
    """
    consulta = _normalizar(nombre)
    if not consulta:
        return "¿Que programa cierro?"

    ventanas = _ventanas_cerrables()
    candidatas = [
        v for v in ventanas
        if consulta in _normalizar(v["titulo"]) or consulta in _normalizar(v["app"])
    ]

    aviso = ""
    if not candidatas:
        # Quiza Whisper escribio mal el nombre: se busca la ventana abierta que MAS se parezca.
        puntajes = [(_mejor_parecido(consulta, [_normalizar(v["app"]), _normalizar(v["titulo"])]), v) for v in ventanas]
        parecidas = sorted([p for p in puntajes if p[0] >= UMBRAL_PARECIDO], key=lambda p: -p[0])
        if parecidas:
            mejor = parecidas[0][0]
            candidatas = [v for p, v in parecidas if mejor - p < 0.05]
            aviso = f" (Entendí «{nombre}» y supuse que es {_describir(candidatas[0])}.)"

    if not candidatas:
        abiertas = "; ".join(sorted({_describir(v) for v in ventanas})[:15])
        return (
            f"No encuentro '{nombre}' entre las ventanas abiertas. "
            f"Ahora estan abiertas: {abiertas or 'ninguna'}"
        )

    # Varias coincidencias: mejor preguntar que cerrar la equivocada. Pasa seguido con
    # las terminales, y una de ellas puede tener algo corriendo. Donde varias ventanas de
    # un mismo programa son un solo proceso (Windows) no hay duda: se cierran todas.
    misma_app = len({_normalizar(v["app"]) for v in candidatas}) == 1
    if len(candidatas) > 1 and not (so.AGRUPA_MISMA_APP and misma_app):
        opciones = "; ".join(_describir(v) for v in candidatas[:8])
        return f"Coinciden varias ventanas: {opciones}. ¿Cual cierro?"

    etiqueta = _describir(candidatas[0])

    if not forzar:
        error = so.cerrar_ventanas(candidatas)
        if error:
            return error
        _registrar_uso(nombre_de_catalogo(candidatas[0]["app"] or etiqueta))
        return f"Le pedi a '{etiqueta}' que se cierre (como apretar la X).{aviso}"

    # Forzar: hace falta el proceso, y la ventana no siempre dice cual es. Se busca por el
    # nombre que dio Brian, el programa de la ventana (suele ser el nombre del ejecutable,
    # ej. "vesktop") y el ejecutable de lo que coincida en el catalogo.
    nombres = {consulta, consulta.replace(" ", "")}
    for v in candidatas:
        if v["app"]:
            nombres.add(_normalizar(v["app"]))
    for _, datos in buscar_programa(nombre)[:3]:
        if datos.get("ejecutable"):
            nombres.add(_normalizar(datos["ejecutable"]))
    nombres = {n for n in nombres if not seguridad.es_intocable(n)}

    procesos, rebeldes = so.cerrar_a_la_fuerza(candidatas, nombres)
    if not procesos:
        return (
            f"Veo la ventana '{etiqueta}' pero no identifico su proceso para "
            "forzar el cierre. Puedo pedirle que cierre normalmente."
        )
    detalle = f"{procesos} proceso(s)" + (f", {rebeldes} hubo que matarlos" if rebeldes else "")
    return f"Cerre '{etiqueta}' a la fuerza ({detalle}).{aviso}"


# --- Deteccion de juegos en curso ---

_cache_juego = {"momento": 0.0, "resultado": None}


def hay_juego_corriendo() -> str | None:
    """
    Devuelve el nombre del juego en curso, o None.

    Sirve para que Nox se aparte de la grafica cuando Brian esta jugando: en una
    RX 7600 de 8 GB, un juego moderno puede pedir 4 GB y el modelo local otros 6.
    No entran juntos. Medido con Monster Hunter Wilds: 3.9 GB de VRAM solo el juego.

    Como se detecta depende del sistema (ver juego_corriendo en so_linux.py y
    so_windows.py). Se cachea unos segundos porque se consulta en cada turno y recorrer
    procesos no es gratis.
    """
    ahora = time.time()
    if ahora - _cache_juego["momento"] < 10:
        return _cache_juego["resultado"]

    try:
        encontrado = so.juego_corriendo(cargar_catalogo())
    except (OSError, subprocess.SubprocessError):
        encontrado = None

    _cache_juego.update(momento=ahora, resultado=encontrado)
    return encontrado


# --- Navegador y web ---

# Atajos para que "abri youtube" funcione sin que Nox tenga que adivinar la URL.
SITIOS = {
    "youtube": "https://www.youtube.com",
    "youtube music": "https://music.youtube.com",
    "music": "https://music.youtube.com",
    "musica": "https://music.youtube.com",
    "gmail": "https://mail.google.com",
    "correo": "https://mail.google.com",
    "drive": "https://drive.google.com",
    "github": "https://github.com",
    "chatgpt": "https://chat.openai.com",
    "claude": "https://claude.ai",
    "whatsapp": "https://web.whatsapp.com",
    "netflix": "https://www.netflix.com",
    "twitch": "https://www.twitch.tv",
    "reddit": "https://www.reddit.com",
    "steam": "https://store.steampowered.com",
    "traductor": "https://translate.google.com",
    "maps": "https://maps.google.com",
}


def abrir_web(destino: str) -> str:
    """
    Abre algo en el navegador. Acepta una URL, el nombre de un sitio conocido,
    o texto libre (en cuyo caso busca en DuckDuckGo).
    """
    import webbrowser
    from urllib.parse import quote_plus

    texto = destino.strip()
    clave = _normalizar(texto)

    if clave in SITIOS:
        url, que = SITIOS[clave], texto
    elif texto.startswith(("http://", "https://")):
        url, que = texto, texto
    elif re.fullmatch(r"[\w-]+(\.[\w-]+)+(/[^\s]*)?", texto):
        url, que = "https://" + texto, texto  # escribio "youtube.com" sin protocolo
    else:
        url, que = f"https://duckduckgo.com/?q={quote_plus(texto)}", f"busqueda de '{texto}'"

    # Solo http/https: bloquea file://, javascript:, data: y demas.
    try:
        url = seguridad.validar_url(url)
    except Rechazado as e:
        return f"Error: {e}"

    webbrowser.open(url)
    # El modelo recibe esto como resultado de la herramienta: si no se le dice que NO vio la
    # pagina, un modelo chico rellena el vacio e inventa lo que "decia".
    return (f"Abriendo {que} en el navegador. [Nota para ti: solo se mostro en la pantalla de la persona; "
            "no tienes su contenido y no debes inventarlo. Para leerla usa leer_pagina_web o el navegador externo.]")


def reproducir_en_youtube(busqueda: str) -> str:
    """
    Busca en YouTube y abre directamente el primer video, en vez de dejar la
    lista de resultados. Si no logra identificarlo, cae en la busqueda normal.
    """
    import webbrowser
    from urllib.parse import quote_plus

    import requests

    consulta = quote_plus(busqueda)
    url_busqueda = f"https://www.youtube.com/results?search_query={consulta}"

    try:
        resp = requests.get(
            url_busqueda,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        ids = re.findall(r'"videoId":"([\w-]{11})"', resp.text)
        if ids:
            webbrowser.open(f"https://www.youtube.com/watch?v={ids[0]}")
            return f"Reproduciendo '{busqueda}' en YouTube."
    except requests.RequestException:
        pass

    webbrowser.open(url_busqueda)
    return f"Abri la busqueda de '{busqueda}' en YouTube (no pude identificar el primer video)."


# --- Escribir archivos ---

def escribir_archivo(ruta: str, contenido: str, agregar: bool = False) -> str:
    """Crea o amplia un archivo de texto en una carpeta permitida."""
    ruta_abs = Path(ruta).expanduser()
    if not ruta_abs.is_absolute():
        ruta_abs = config.CARPETA_TRABAJO / ruta_abs

    try:
        destino = seguridad.validar_escritura(
            ruta_abs, config.CARPETAS_ESCRITURA, config.EXTENSIONES_ESCRITURA
        )
    except Rechazado as e:
        return f"Error: {e}"

    destino.parent.mkdir(parents=True, exist_ok=True)

    # Antes de pisar algo que ya existe, guardar una copia. Asi ningun error de Nox
    # sobre archivos es irreversible.
    if destino.exists() and not agregar:
        import guardian
        copia = guardian.respaldar(destino)
        if copia is None and destino.exists():
            return (
                f"No pude respaldar {destino.name} antes de reemplazarlo, asi que no lo "
                "toco. Revisa que la carpeta de respaldos sea escribible."
            )

    if agregar and destino.exists():
        actual = destino.read_text(encoding="utf-8", errors="ignore")
        destino.write_text(actual.rstrip() + "\n" + contenido, encoding="utf-8")
        return f"Contenido agregado a {destino}"

    existia = destino.exists()
    destino.write_text(contenido, encoding="utf-8")
    verbo = "Reemplazado" if existia else "Creado"
    return f"{verbo}: {destino} ({len(contenido)} caracteres)"


def explorar_carpeta(ruta: str) -> str:
    """Lista lo que hay en una carpeta, con tamaños y fechas."""
    from datetime import datetime

    destino = Path(ruta).expanduser()
    if not destino.is_absolute():
        destino = config.CARPETA_TRABAJO / destino
    destino = seguridad.resolver(destino)

    if not destino.exists():
        return f"No existe: {destino}"
    if not destino.is_dir():
        return f"No es una carpeta: {destino}"

    try:
        items = sorted(
            destino.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
        )
    except PermissionError:
        return f"No tengo permiso para entrar a {destino}"

    if not items:
        return f"{destino} esta vacia."

    lineas = [f"{destino}\n"]
    for p in items[:80]:
        try:
            if p.is_dir():
                lineas.append(f"  [carpeta] {p.name}")
            else:
                mb = p.stat().st_size / 1024 / 1024
                fecha = datetime.fromtimestamp(p.stat().st_mtime).strftime("%d/%m/%Y")
                tam = f"{mb:.1f} MB" if mb >= 1 else f"{p.stat().st_size / 1024:.0f} KB"
                lineas.append(f"  {p.name}  ({tam}, {fecha})")
        except OSError:
            continue

    if len(items) > 80:
        lineas.append(f"  ... y {len(items) - 80} elementos mas")
    return "\n".join(lineas)


def buscar_archivos(patron: str, carpeta: str = "") -> str:
    """Busca archivos por nombre en una carpeta (y sus subcarpetas)."""
    base = Path(carpeta).expanduser() if carpeta else Path.home()
    base = seguridad.resolver(base)

    if not base.exists() or not base.is_dir():
        return f"No existe la carpeta: {base}"

    if "*" not in patron and "?" not in patron:
        patron = f"*{patron}*"

    encontrados = []
    try:
        for p in base.rglob(patron):
            if p.is_file():
                encontrados.append(p)
            if len(encontrados) >= 60:
                break
    except (PermissionError, OSError):
        pass

    if not encontrados:
        return f"No encontre nada que coincida con '{patron}' en {base}"

    lineas = [f"{len(encontrados)} resultado(s) en {base}:\n"]
    for p in encontrados:
        try:
            kb = p.stat().st_size / 1024
            lineas.append(f"  {p}  ({kb:.0f} KB)")
        except OSError:
            lineas.append(f"  {p}")
    return "\n".join(lineas)


def leer_archivo(ruta: str) -> str:
    """Lee un archivo de texto. Bloquea rutas sensibles (credenciales, sistema)."""
    ruta_abs = Path(ruta).expanduser()
    if not ruta_abs.is_absolute():
        ruta_abs = config.CARPETA_TRABAJO / ruta_abs

    try:
        destino = seguridad.validar_lectura(ruta_abs, config.CARPETAS_LECTURA)
    except Rechazado as e:
        return f"Error: {e}"

    if destino.stat().st_size > 2_000_000:
        return "El archivo es demasiado grande (mas de 2 MB)."

    try:
        texto = destino.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return f"No pude leerlo: {e}"

    if len(texto) > config.MAX_CHARS_NOTA:
        texto = texto[: config.MAX_CHARS_NOTA] + "\n\n[...recortado...]"
    return texto


# --- Volumen y multimedia ---

def control_multimedia(accion: str, repeticiones: int = 1) -> str:
    """Volumen y reproduccion, como las teclas multimedia del teclado."""
    if accion not in so.ACCIONES_MULTIMEDIA:
        return f"Accion desconocida. Validas: {', '.join(so.ACCIONES_MULTIMEDIA)}"

    repeticiones = max(1, min(int(repeticiones), 20))
    error = so.tecla_multimedia(accion, repeticiones)
    if error:
        return error

    return f"Listo: {accion.replace('_', ' ')}" + (
        f" x{repeticiones}" if repeticiones > 1 else ""
    )


# --- Consultas del sistema (solo lectura) ---

def consulta_lectura(comando: str) -> str:
    """
    Ejecuta un comando de consulta del sistema (PowerShell en Windows, comandos de Linux
    en Linux). La validacion vive en seguridad.py, en una lista blanca.
    """
    return so.ejecutar_consulta(comando)
