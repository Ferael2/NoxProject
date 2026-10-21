"""
Decide cuanto esfuerzo poner en cada pregunta.

Por que existe esto: en esta maquina el modelo genera ~6.8 tokens/s. Eso significa
que cada 500 caracteres de respuesta son ~18 segundos de espera. La diferencia entre
un asistente agradable y uno insoportable no es el tamaño del modelo, es que no
divague cuando no hace falta.

Se descarto enrutar a qwen3:14b: medido en esta PC va a 2.2 tok/s contra 6.8 del 8B,
porque se desborda 33% a RAM (single-channel a 2400 MHz). Tres veces mas lento no lo
compensa. En cambio se ajusta el ESFUERZO sobre el mismo modelo.
"""
import re
import sys

if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

# Ordenes directas: abrir cosas, poner musica, subir volumen. Respuesta de una linea.
PATRONES_ACCION = (
    r"\babr[ie]", r"\bpon[eé]", r"\bpone?r\b", r"\breproduc", r"\bsub[ií]\b",
    r"\bbaj[aá]\b", r"\bsilenci", r"\bpaus", r"\bsiguiente\b", r"\banterior\b",
    r"\bcerr[aá]", r"\bescrib[ií]", r"\bguard[aá]", r"\brecord[aá]", r"\bolvid",
    r"\bque hora\b", r"\bqué hora\b",
    r"\brecu[eé]rd(a|e)me\b", r"\bav[ií]same\b", r"\brecordatorio",
)

# Preguntas que piden razonar de verdad.
PATRONES_PROFUNDO = (
    r"\bpor qu[eé]\b", r"\bpor que\b", r"\bc[oó]mo funciona\b", r"\bexplic",
    r"\bcompar", r"\bdiferencia", r"\bconviene\b", r"\bmejor opci[oó]n\b",
    r"\bventajas?\b", r"\bdesventajas?\b", r"\banaliz", r"\bevalu",
    r"\brecomend", r"\bqu[eé] pasar[ií]a\b", r"\bcu[aá]l.*mejor\b",
    r"\bayudame a (pensar|decidir|elegir)\b", r"\bdise[nñ]",
)

# Charla: saludos, comentarios, cosas de todos los dias.
PATRONES_CHARLA = (
    r"^(hola|buenas|buen d[ií]a|buenas tardes|buenas noches|hey|ey)\b",
    r"^(gracias|dale|listo|ok|okay|perfecto|genial|bien|barbaro|bárbaro)\b",
    r"\b(como estas|cómo estás|como andas|cómo andás|que tal|qué tal|todo bien)\b",
    r"^(chau|adios|adiós|nos vemos|hasta luego|hasta ma[nñ]ana)\b",
    r"^(que hac[eé]s|qué hacés|en que anda|qué onda|que onda)\b",
)

# Cuanto texto puede gastar cada modo, en caracteres aproximados.
LIMITES = {
    "accion": "una o dos frases, nada mas",
    "charla": "una o dos frases, en tono relajado",
    "normal": "maximo un parrafo corto, salvo que pidan detalle",
    "profundo": "lo que haga falta, pero sin relleno",
}


def clasificar(texto: str) -> str:
    """Devuelve 'accion', 'charla', 'normal' o 'profundo'."""
    limpio = texto.lower().strip()

    if any(re.search(p, limpio) for p in PATRONES_CHARLA):
        return "charla"
    if any(re.search(p, limpio) for p in PATRONES_PROFUNDO):
        return "profundo"
    if any(re.search(p, limpio) for p in PATRONES_ACCION):
        return "accion"

    # Una pregunta larga con varias partes casi siempre pide razonar.
    if len(limpio.split()) > 25 or limpio.count("?") > 1:
        return "profundo"

    return "normal"


# Señales de que la pregunta toca cosas de Brian. Ante la duda, se resuelve local.
PATRONES_PERSONAL = (
    # Posesivos y referencias a si mismo
    r"\bmi\b", r"\bmis\b", r"\bmío\b", r"\bmio\b", r"\bmía\b", r"\bmia\b",
    r"\byo\b", r"\bme\b", r"\bconmigo\b", r"\bbrian\b",
    # La boveda y la memoria
    r"\bb[oó]veda\b", r"\bwiki\b", r"\bnota[s]?\b", r"\bobsidian\b",
    r"\bacord[aá]", r"\brecord[aá]", r"\bte acord", r"\bmemoria\b",
    # Su PC y sus cosas
    r"\bmi (pc|compu|computadora|maquina|máquina|equipo)\b",
    r"\barchivo[s]?\b", r"\bcarpeta[s]?\b", r"\bjuego[s]? (que|tengo|mio)",
    r"\bhoras\b", r"\bsteam\b", r"\binstalad",
    # Sus proyectos por nombre
    r"\bskyrent\b", r"\boversystem\b", r"\bcontapack\b", r"\bcodice farulum\b",
    r"\bc[oó]dice farulum\b", r"\bsistema financiero\b", r"\bgbo\b", r"\bnox\b",
)


# Señales de que la pregunta es sobre la PC de Brian o requiere actuar sobre ella.
# Todo esto se resuelve LOCAL: las herramientas del sistema no existen en la nube.
PATRONES_PC = (
    r"\babr[ie]", r"\bcerr[aá]", r"\bcierra\b", r"\bpon[eé]", r"\breproduc",
    r"\bvolumen\b", r"\bpaus", r"\bsilenci", r"\bcancion\b", r"\bcanción\b",
    r"\bprograma[s]?\b", r"\bventana[s]?\b", r"\bproceso[s]?\b", r"\bapp\b",
    r"\barchivo[s]?\b", r"\bcarpeta[s]?\b", r"\bdisco\b", r"\bdescarga[s]?\b",
    r"\bescritorio\b", r"\bdocumento[s]?\b", r"\bguard[aá]", r"\bescrib[ií]",
    r"\bjuego[s]?\b", r"\bsteam\b", r"\bhoras\b", r"\bjugad", r"\bjugar\b",
    r"\bcpu\b", r"\bram\b", r"\bmemoria\b", r"\bgrafica\b", r"\bgráfica\b",
    r"\bmi (pc|compu|computadora|maquina|máquina|equipo)\b",
    r"\bque tengo (abierto|instalado)\b", r"\bque hora\b", r"\bqué hora\b",
    # Recordatorios: se guardan en la PC, no existen en la nube.
    r"\brecu[eé]rd(a|e)me\b", r"\bav[ií]same\b", r"\brecordatorio[s]?\b", r"\bcancela (el|ese|mi) recordatorio\b",
    # Tipos de archivo: si nombra uno, esta hablando de algo que tiene guardado.
    r"\bpdf\b", r"\bexcel\b", r"\bword\b", r"\bdocx?\b", r"\bxlsx?\b", r"\bpptx?\b",
    r"\bcsv\b", r"\btxt\b", r"\bzip\b", r"\bfoto[s]?\b", r"\bimagen(es)?\b",
    r"\bcaptura[s]?\b", r"\bvideo[s]?\b", r"\bcancion(es)?\b", r"\bmp3\b", r"\bmp4\b",
    r"\bfactura[s]?\b", r"\brecibo[s]?\b", r"\bplanilla[s]?\b", r"\bbackup\b",
)

# Señales de que hace falta conocimiento externo o razonar sobre algo general.
# Esto es lo que conviene mandar a la nube: el modelo remoto es mucho mejor y no
# necesita tocar nada de la PC.
PATRONES_CONOCIMIENTO = (
    r"\bque es\b", r"\bqué es\b", r"\bque son\b", r"\bqué son\b",
    r"\bcomo funciona\b", r"\bcómo funciona\b", r"\bexplic", r"\bense[nñ]ame\b",
    r"\bpor qu[eé]\b", r"\bpara que sirve\b", r"\bdiferencia entre\b",
    r"\bbusc[aá] (en internet|informacion|información)\b", r"\binvestig",
    r"\bnoticias\b", r"\bultimas? (novedades|noticias)\b", r"\bactualidad\b",
    r"\bhistoria de\b", r"\bsignifica\b", r"\bdefini", r"\bconcepto\b",
    r"\btraduc", r"\bresum[ií]", r"\bcompar[aá]", r"\bventajas?\b",
)


def necesita_la_pc(texto: str) -> bool:
    """True si la pregunta requiere tocar la PC de Brian (va local si o si)."""
    limpio = texto.lower()
    return any(re.search(p, limpio) for p in PATRONES_PC)


def es_conocimiento_general(texto: str) -> bool:
    """True si la pregunta pide informacion o razonamiento general (va a la nube)."""
    limpio = texto.lower()
    return any(re.search(p, limpio) for p in PATRONES_CONOCIMIENTO)


def decidir_ruta(texto: str) -> tuple[str, str]:
    """
    Decide por donde va la consulta. Devuelve (ruta, motivo) para poder mostrarlo.

    El orden importa: las razones para quedarse local se evaluan primero, porque son
    restricciones (no puede hacerse afuera), no preferencias.
    """
    if parece_personal(texto):
        return "local", "toca tus datos"
    if pide_herramientas_externas(texto):
        return "local", "usa tus herramientas externas"
    if necesita_la_pc(texto):
        return "local", "necesita tu PC"
    if es_conocimiento_general(texto):
        return "nube", "informacion general"
    # Sin señales claras: la nube responde mejor y mas rapido en casi todo lo demas.
    return "nube", "consulta general"


# Palabras que sugieren navegar o actuar en una pagina: si hay herramientas externas activas
# (un navegador por MCP), eso solo existe en la PC, no en la nube.
PATRONES_EXTERNAS = (
    r"\bnaveg", r"\bentra (a|en)\b", r"\bp[aá]gina\b", r"\bformulario", r"\bhaz clic\b",
    r"\bhttps?://", r"\bwww\.", r"\b[\w-]+\.(com|org|net|io|es|mx)\b",
)


def pide_herramientas_externas(texto: str) -> bool:
    """True si hay herramientas externas activas y el pedido parece necesitarlas."""
    import mcp_cliente
    if not mcp_cliente.esquemas_activos():
        return False
    limpio = texto.lower()
    return any(re.search(p, limpio) for p in PATRONES_EXTERNAS)


def parece_personal(texto: str) -> bool:
    """
    True si la pregunta parece involucrar informacion de Brian.

    Se usa para decidir si una consulta profunda puede salir a la nube. Es
    deliberadamente exagerado: preferimos mandar de mas al modelo local (mas lento
    pero privado) que filtrar algo por afuera. Un falso positivo cuesta segundos;
    un falso negativo cuesta privacidad.
    """
    limpio = texto.lower()
    return any(re.search(p, limpio) for p in PATRONES_PERSONAL)


def configuracion(modo: str) -> dict:
    """
    Como se comporta el asistente en cada modo.

    'pensar' activa el razonamiento interno de Qwen3: casi duplica el tiempo, asi que
    solo se usa donde realmente cambia la respuesta.
    """
    return {
        "accion":   {"pensar": False, "revisar": False, "estilo": LIMITES["accion"]},
        "charla":   {"pensar": False, "revisar": False, "estilo": LIMITES["charla"]},
        "normal":   {"pensar": False, "revisar": False, "estilo": LIMITES["normal"]},
        "profundo": {"pensar": True,  "revisar": True,  "estilo": LIMITES["profundo"]},
    }[modo]


# Pedidos que traen un enlace y quieren SABER lo que dice (no solo verlo): "entra a X y dime...".
PATRON_ENLACE = r"https?://\S+|\bwww\.\S+|\b[\w-]+\.(?:com|org|net|io|es|mx)\b"
PATRONES_LEER = (
    r"\bdime\b", r"\bcu[aá]l\b", r"\bqu[eé] dice\b", r"\bres[uú]me", r"\blee\b", r"\bleer\b",
    r"\brevisa", r"\bbusca", r"\bencuentra", r"\bextrae", r"\bcu[aá]nto", r"\bqui[eé]n", r"\bd[oó]nde",
    r"\bde qu[eé] (trata|habla)",
)


def pista_de_herramienta(texto: str) -> str:
    """
    Una pista de que herramienta usar cuando el pedido trae un enlace y quiere LEER su contenido.

    Sin esto, "entra a <enlace> y dime X" empuja a un modelo chico hacia abrir_web, que solo
    muestra la pagina en pantalla y no devuelve nada que contestar. Medido: lo usaba el 100 % de
    las veces, y antes de que abrir_web avisara que no entrega contenido, inventaba la respuesta.
    """
    limpio = texto.lower()
    if not re.search(PATRON_ENLACE, limpio) or not any(re.search(p, limpio) for p in PATRONES_LEER):
        return ""
    import mcp_cliente
    if mcp_cliente.esquemas_activos():
        return ("PISTA: el pedido incluye un enlace y pide saber lo que dice. Usa las herramientas externas del "
                "navegador (navegar a la dirección y leer la página). No uses abrir_web: no devuelve el contenido.")
    return ("PISTA: el pedido incluye un enlace y pide saber lo que dice. Usa leer_pagina_web con esa dirección. "
            "No uses abrir_web: no devuelve el contenido.")


def instruccion_completa(texto: str, modo: str) -> str:
    """
    La linea que se agrega al mensaje de la persona: el estilo de respuesta, si aplica una pista, y
    la FECHA Y HORA de ahora. Un modelo no sabe que dia es, y sin esto no puede programar un
    recordatorio "para mañana a las 9" (tiene que calcular la fecha).
    """
    import recordatorios
    pista = pista_de_herramienta(texto)
    return (instruccion_de_estilo(modo) + (f" {pista}" if pista else "")
            + f" AHORA ES: {recordatorios.ahora_texto()}.")


def instruccion_de_estilo(modo: str) -> str:
    """Linea que se le agrega al prompt para que ajuste el largo de la respuesta."""
    estilo = configuracion(modo)["estilo"]
    base = f"LARGO DE ESTA RESPUESTA: {estilo}."

    if modo == "accion":
        return base + (
            " Es una orden directa: ejecutala y confirma en una linea. No expliques "
            "lo que hiciste ni ofrezcas alternativas salvo que algo falle."
        )
    if modo == "charla":
        return base + (
            " Es charla, no una consulta tecnica. No la conviertas en un proyecto ni "
            "ofrezcas ayuda con nada: contestá como contestaria una persona. Si te "
            "saluda, saludá; si te pregunta como estas, respondé y devolvé la pregunta."
        )
    if modo == "profundo":
        return base + " Aca si vale desarrollar, pero sin repetir ni rellenar."
    return base + " Si hace falta mas, te lo va a pedir."
