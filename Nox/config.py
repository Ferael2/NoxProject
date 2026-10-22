"""
Configuracion central del asistente.
Todo lo que se pueda querer ajustar (modelo, rutas, limites) vive aca.
"""
import getpass
import json
import os
import sys
from pathlib import Path

import plataforma

if getattr(sys, "frozen", False):
    PROYECTO = Path(sys.executable).resolve().parent
else:
    PROYECTO = Path(__file__).resolve().parent

# Nombres que dependen del sistema y del idioma (Documentos/Escritorio, Documents/Desktop).
# Ver plataforma.carpeta_usuario.
DOCUMENTOS = plataforma.carpeta_usuario("DOCUMENTS", "Documents")
ESCRITORIO = plataforma.carpeta_usuario("DESKTOP", "Desktop")


def _ajustes_locales() -> dict:
    """
    Ajustes propios de cada maquina. En el .exe de Windows viven en AppData, que permite
    guardarlos aunque Nox este instalado en una carpeta de solo lectura. Si no hay archivo
    ahi, se intenta leer el config_local.json antiguo junto al ejecutable.
    """
    try:
        return json.loads(archivo_ajustes_lectura().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def archivo_ajustes() -> Path:
    """Ruta persistente de preferencias; usa AppData para el .exe de Windows."""
    if getattr(sys, "frozen", False) and plataforma.ES_WINDOWS:
        appdata = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        return appdata / "Nox" / "config_local.json"
    return PROYECTO / "config_local.json"


def archivo_ajustes_lectura() -> Path:
    """Lee el archivo nuevo si existe y, si no, conserva la configuracion junto al .exe."""
    actual = archivo_ajustes()
    anterior = PROYECTO / "config_local.json"
    if actual.exists() or actual == anterior or not anterior.exists():
        return actual
    return anterior


AJUSTES_LOCALES = _ajustes_locales()

# --- Perfiles de equipo ---
# Un perfil agrupa lo que depende del hardware: que modelo conversa, cuanto contexto le cabe,
# y donde corre Whisper. Se elige con "equipo" en config_local.json; cualquier clave suelta
# de config_local.json (ej. "modelo_chat") pisa lo que diga el perfil.
#
# Los modelos de cada perfil salen de `python evaluar_modelo.py`, no de intuicion: ver
# resultados_modelos/ y HOJA_DE_RUTA.md. Un perfil solo dice "medido" si se midio en ese equipo.
PERFILES_EQUIPO = {
    # Ryzen 5 5600G, Radeon RX 7600 (8 GB de VRAM), 16 GB de RAM de un solo canal.
    # MEDIDO. Es el perfil por defecto: el que cabe en una tarjeta de 8 GB.
    "estandar_8gb": {
        "descripcion": "Tarjeta de video de 8 GB (AMD o NVIDIA), 16 GB de RAM",
        "modelo_chat": "qwen3:8b",
        "num_ctx": 8192,
        "modelo_whisper": "medium",
        "modelo_whisper_escucha": "small",
        "whisper_device": "cpu",   # faster-whisper solo usa GPU NVIDIA; en AMD va en CPU
    },
    # Laptop con RTX 4060 (8 GB de VRAM) y 24 GB de RAM. SIN MEDIR: la misma cantidad de VRAM
    # que el perfil anterior, asi que se parte del mismo modelo. Correr evaluar_modelo.py alla.
    "laptop_rtx4060": {
        "descripcion": "Laptop con RTX 4060 (8 GB de VRAM) y 24 GB de RAM",
        "modelo_chat": "qwen3:8b",
        "num_ctx": 8192,
        "modelo_whisper": "medium",
        "modelo_whisper_escucha": "small",
        # CPU por defecto: los 8 GB de VRAM los ocupa el modelo de conversacion. Para pasar
        # Whisper a la GPU hay que instalar CUDA 12 + cuDNN 9 y bajar el modelo (ver
        # INSTALACION.md): "whisper_device": "cuda" en config_local.json.
        "whisper_device": "cpu",
    },
    # Equipo modesto: sin tarjeta de video dedicada, o con 4 GB.
    "basico": {
        "descripcion": "Sin tarjeta dedicada o con 4 GB de VRAM, 8 GB de RAM",
        "modelo_chat": "qwen3:4b",
        "num_ctx": 4096,
        "modelo_whisper": "small",
        "modelo_whisper_escucha": "base",
        "whisper_device": "cpu",
    },
}
EQUIPO_POR_DEFECTO = "estandar_8gb"
EQUIPO = AJUSTES_LOCALES.get("equipo", EQUIPO_POR_DEFECTO)
if EQUIPO not in PERFILES_EQUIPO:
    print(f"Perfil de equipo '{EQUIPO}' desconocido; uso '{EQUIPO_POR_DEFECTO}'. "
          f"Validos: {', '.join(PERFILES_EQUIPO)}")
    EQUIPO = EQUIPO_POR_DEFECTO
_PERFIL = PERFILES_EQUIPO[EQUIPO]


def _ajuste(clave: str):
    """Un valor de config_local.json si lo hay; si no, el del perfil de equipo."""
    return AJUSTES_LOCALES.get(clave, _PERFIL[clave])


# --- Ollama ---
OLLAMA_HOST = "http://localhost:11434"
CHAT_URL = f"{OLLAMA_HOST}/api/chat"
EMBED_URL = f"{OLLAMA_HOST}/api/embeddings"

# --- Motor de conversación ---
# "openrouter" corre el modelo en la nube (sin necesidad de tener Ollama ni descargar 5.5 GB).
# "ollama" corre el modelo localmente en la máquina.
MOTOR_CHAT = str(AJUSTES_LOCALES.get("motor_chat", "openrouter")).lower()
MODELO_OPENROUTER = str(AJUSTES_LOCALES.get("modelo_openrouter", "google/gemma-4-31b-it:free")).strip()
MODELO_CHAT = _ajuste("modelo_chat")

MODELO_EMBED = "nomic-embed-text"  # usado si Ollama esta activo; si no, hay fallback local
USAR_OLLAMA_EMBED = bool(AJUSTES_LOCALES.get("usar_ollama_embed", False))

# Qwen3 razona antes de responder ("thinking"). Para un asistente conversacional
# eso agrega varios segundos por respuesta, asi que va apagado por defecto.
PENSAR = False

# Ventana de contexto. Ollama usa 4096 por defecto, aunque qwen3:8b soporta 40960:
# con 4096 se truncaba solo el historial apenas entraban una busqueda de la boveda
# mas el system prompt. Medido en esta maquina (RX 7600, 8 GB):
#   8192  -> 6.2 GB, 100% GPU   <- elegido
#   16384 -> 7.8 GB, se va 7% a CPU
#   32768 -> 10 GB, se va 31% a CPU (lento: la RAM es single-channel a 2400 MHz)
# Si algun dia pone un segundo modulo de RAM, subir esto sale mucho mas barato.
NUM_CTX = _ajuste("num_ctx")

# --- Boveda de Obsidian ---
# Es opcional: sin ella Nox funciona igual, solo que no tiene wiki personal para consultar.
# Se busca, en este orden:
#   1. la variable de entorno NOX_BOVEDA
#   2. "boveda" en config_local.json
#   3. una carpeta "Claude" hermana de la del proyecto (la disposicion original)
#   4. una carpeta "boveda" dentro del proyecto (vacia hasta que se use)
def _buscar_boveda() -> Path:
    for candidata in (os.environ.get("NOX_BOVEDA"), AJUSTES_LOCALES.get("boveda")):
        if candidata:
            return Path(candidata).expanduser()
    hermana = PROYECTO.parent / "Claude"
    if hermana.is_dir():
        return hermana
    return PROYECTO / "boveda"


BOVEDA = _buscar_boveda()
INDICE_DB = BOVEDA / "RAG" / "index.db"

# --- Memoria persistente del asistente ---
# Separada de la boveda a proposito: la boveda es conocimiento curado, esto es lo
# que el asistente aprende conversando.
MEMORIA_DB = PROYECTO / "memoria.db"
UMBRAL_MEMORIA = 0.55  # score minimo para considerar que un recuerdo es relevante

# Carpeta del propio codigo de Nox. Esta dentro del Escritorio (que es de escritura), asi
# que se excluye a proposito: Nox no debe poder tocar programas.json ni su propio codigo.
CARPETA_PROYECTO = PROYECTO

# --- Identidad ---
NOMBRE = "Nox"


# --- Quien usa a Nox ---
# Todo esto sale de config_local.json (lo crea instalar.sh / instalar.bat, o `python
# configurar.py`), asi cada persona tiene su propio Nox sin tocar el codigo.
def _nombre_usuario() -> str:
    nombre = str(AJUSTES_LOCALES.get("usuario") or "").strip()
    if nombre:
        return nombre
    try:  # sin nombre configurado se usa el del usuario del sistema ("ana_perez" -> "Ana Perez")
        return getpass.getuser().replace("_", " ").replace(".", " ").title()
    except Exception:
        return "Usuario"


USUARIO = _nombre_usuario()

# Como prefiere que le hablen. Es una regla de estilo, no un dato personal, asi que viaja
# tambien al canal de la nube. Ej: "Evita las metaforas con computadoras."
ESTILO_USUARIO = str(AJUSTES_LOCALES.get("estilo") or "").strip()

# Contexto personal libre (gustos, que contiene su boveda, que reproductor usa...). Solo se
# le dice al modelo LOCAL: nunca sale a la nube.
PERFIL_USUARIO = str(AJUSTES_LOCALES.get("perfil") or "").strip()

# Como quiere que se le hable. "trato" es tu/usted; "tono" es una de las opciones de
# TONOS (o un texto propio en "estilo"). Se configuran desde la ventana de Ajustes.
TRATOS = {
    "tu": "Háblale de tú.",
    "usted": "Trátale de usted, con respeto.",
}
TONOS = {
    "natural": ("Natural", "Directo y de persona a persona, sin formalidades de más."),
    "cercano": ("Cercano", "Cálido y cercano, como entre amigos que se respetan."),
    "directo": ("Al grano", "Respuestas cortas y al punto, sin rodeos ni cortesías de relleno."),
    "formal": ("Formal", "Formal y profesional, con lenguaje cuidado."),
    "detallado": ("Detallado", "Explica con detalle y paso a paso, con ejemplos, salvo que se pida brevedad."),
}


def _elegir(valor, validos, por_defecto):
    return valor if valor in validos else por_defecto


TRATO = _elegir(AJUSTES_LOCALES.get("trato"), TRATOS, "tu")
TONO = _elegir(AJUSTES_LOCALES.get("tono"), TONOS, "natural")

# Con boveda no hay nada que consultar: el prompt se arma distinto segun haya o no.
HAY_BOVEDA = INDICE_DB.exists()

# --- Nube (OpenRouter) ---
# Solo se usa para preguntas del modo "profundo" que NO tocan nada personal. La key va
# en el archivo openrouter.key (no en este archivo, para no versionarla por accidente).
# Limites de la cuenta gratuita: 50 peticiones/dia, 20 por minuto. Con $10 de credito
# cargado suben a 1000/dia (los modelos :free siguen costando 0; el credito es solo el
# umbral que desbloquea el limite alto).
USAR_NUBE = bool(AJUSTES_LOCALES.get("usar_nube", True))   # ajustable en la ventana de Ajustes

# La nube atiende primero todo lo que pueda salir de la PC (mucho mas rapida: ~2-20 s
# contra ~30-300 s del modelo local). El local es el respaldo automatico: entra solo
# cuando se acaba la cuota diaria, se cae la red, o la pregunta toca datos personales.
NUBE_PRIMERO = True

# Medido el 2026-09-08 con la misma pregunta a los cuatro candidatos gratuitos:
#   nemotron-3-super-120b   21.8s  <- elegido: mejor calidad/velocidad
#   nemotron-3.5-lightning  36.9s
#   nemotron-3-ultra-550b   95.9s  (mejor respuesta, pero inusable de tan lento)
#   gemma-4-31b             bloqueado por limite
#   inkling                 403: restringido a "agentic harnesses" registradas
# Para comparar: el Qwen local tarda ~60s en preguntas de este tipo.
MODELO_NUBE = "nvidia/nemotron-3-super-120b-a12b:free"

# Cuando hay un juego corriendo, la grafica ya esta ocupada: en una RX 7600 de 8 GB un
# juego moderno pide ~4 GB y el modelo local otros ~6. No entran juntos. Con esto activo,
# las consultas que puedan salir se van a la nube mientras jugas, y el modelo local se
# descarga de la VRAM apenas termina de responder.
CEDER_GPU_AL_JUGAR = bool(AJUSTES_LOCALES.get("ceder_gpu_al_jugar", True))
KEEP_ALIVE_NORMAL = "5m"   # cuanto se queda el modelo cargado en VRAM
KEEP_ALIVE_JUGANDO = "30s"  # mientras jugas, libera la VRAM enseguida

# Cadena de respaldo: si el principal esta saturado o bloqueado, se prueba el siguiente
MODELOS_NUBE_ALTERNATIVOS = [
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3.5-lightning:free",
    "minimax/minimax-m3.1-flash:free",
    "liquid/lfm-2.5-2.6b:free",
]

# --- Voz ---
VOZ_ACTIVA = bool(AJUSTES_LOCALES.get("voz_activa", True))
# tiny / base / small / medium / large-v3. "medium" entiende bastante mejor que "small",
# sobre todo nombres propios; cuesta mas CPU pero el Ryzen 5600G lo aguanta.
MODELO_WHISPER = _ajuste("modelo_whisper")

# Donde corre Whisper: "cpu" (siempre funciona) o "cuda" (GPU NVIDIA con CUDA 12 + cuDNN 9).
# Si "cuda" falla, Nox cae a la CPU solo. Ver voz.crear_whisper.
WHISPER_DEVICE = _ajuste("whisper_device")
WHISPER_COMPUTE_GPU = "float16"   # "int8_float16" ocupa menos memoria de video
# Cuantas transcripciones alternativas explora antes de decidir. Mas alto = menos
# palabras inventadas o comidas, a cambio de tiempo.
BEAM_SIZE = 5
BEAM_SIZE_ESCUCHA = 3      # en la escucha continua se baja, corre todo el tiempo
IDIOMA_VOZ = "es"
SEGUNDOS_GRABACION = 15    # tope de una grabacion por turno
FRECUENCIA_AUDIO = 16000   # Whisper espera 16 kHz

# Piper: voz neuronal local, mucho mas natural que las voces del sistema.
# Para cambiarla (con el entorno de Nox activado):
#   python -m piper.download_voices <nombre> --data-dir voces
# Opciones en español: es_MX-claude-high, es_ES-davefx-medium, es_ES-sharvard-medium,
# es_AR-daniela-high. Si el archivo no existe, cae automaticamente a la voz del
# sistema (SAPI en Windows, espeak-ng en Linux).
VOZ_PIPER = PROYECTO / "voces" / "es_MX-claude-high.onnx"
VELOCIDAD_VOZ = float(AJUSTES_LOCALES.get("velocidad_voz", 1.0))  # 1.0 normal; mas alto = mas lento (multiplicador)
VELOCIDAD_VOZ_RESPALDO = 180 if plataforma.ES_WINDOWS else 170  # palabras por minuto, solo
# si se usa la voz de respaldo del sistema (SAPI en Windows, espeak-ng en Linux)

# --- Palabra de activacion ---
PALABRA_ACTIVACION = "nox"
# Como Whisper suele escribir "Nox". Ademas de esta lista se compara por similitud
# (ver voz.py), porque enumerar todas las variantes es una carrera perdida.
# Ojo al agregar: "nos" y "no" se descartaron a proposito por ser demasiado comunes
# en español — activaban con frases como "no se que hacer" o "nos vamos".
VARIANTES_ACTIVACION = (
    "nox", "nocs", "noks", "knox", "nog", "noc", "nock", "nogs",
    "nax", "nox's", "nux", "nex", "nots",
)
MODELO_WHISPER_ESCUCHA = _ajuste("modelo_whisper_escucha")  # el de la escucha continua

# Frases que solo piden atencion, sin contenido: corresponde contestar y esperar.
# "Hola Nox" o "como estas Nox" NO van aca: esos ya son un mensaje y merecen respuesta.
LLAMADAS_DE_ATENCION = frozenset({
    "hey", "ey", "oye", "oi", "che", "eh",
    "dime", "decime", "deci", "di",
    "escucha", "escuchame", "escucha me", "atiende", "atendeme",
    "estas ahi", "estás ahí", "me escuchas", "me escuchás",
})

# Palabras que pueden venir ANTES del nombre cuando se lo esta llamando:
# "hey Nox", "buen dia Nox", "che Nox". Si antes del nombre aparece algo que no esta
# en esta lista (un verbo, por ejemplo), se asume que estan hablando DE el y no
# se activa: "ayer instale nox en la otra compu".
PREAMBULOS = frozenset({
    "hey", "ey", "eh", "oye", "oi", "che", "ah", "ay", "o",
    "hola", "buenas", "buen", "buenos", "dia", "día", "dias", "días",
    "tardes", "noches", "salu2", "saludos",
    "dime", "decime", "deci", "escucha", "escuchame", "atiende",
    "a", "ver", "bueno", "ok", "okay", "dale", "listo", "bien",
    "gracias", "por", "favor", "disculpa", "disculpame", "perdon", "perdón",
    "que", "qué", "tal", "como", "cómo", "estas", "estás", "andas", "andás",
    "todo", "y", "pero", "entonces", "asi", "así", "mira", "mirá", "vieja",
})

# Respuestas al llamado, rotadas para que no suene a maquina repitiendo lo mismo.
RESPUESTAS_AL_LLAMADO = ("¿Sí?", "Dime.", "Te escucho.", "Adelante.", "¿Qué necesitas?")

# Despues de responderte, Nox sigue atento un rato sin que tengas que repetir su
# nombre. Es lo que hace que se sienta una conversacion y no una serie de ordenes
# sueltas. En 0 se desactiva.
VENTANA_CONVERSACION = 25.0  # segundos

# La escucha espera a que TERMINES de hablar, no a la primera pausa.
#
# La primera version cortaba a los 0.8 s de silencio, y eso partia las frases al medio:
# al hablar natural uno hace pausas para pensar ("y entonces... este... queria que"),
# para respirar y entre ideas. Cada una de esas se tomaba como fin del mensaje.
#
# Ahora el silencio necesario es ADAPTATIVO: crece con lo que ya venis hablando. Una
# orden corta ("Nox, pausa") se despacha rapido, y un dictado largo te deja pensar.
UMBRAL_SILENCIO = 0.008        # volumen minimo para considerar que hay voz (solo si no hay VAD)

# Detector de voz (Silero VAD, ver vad.py). Es lo que decide "esto es una voz" en lugar del
# volumen: ignora ventiladores y teclados, y oye voces muy suaves. Medido con audio
# sintetico: ruido de ventilador activaba el 100 % de los trozos con el umbral de volumen
# y 0 % con el VAD; una voz baja pasaba de 14 % a 93 %.
USAR_VAD = bool(AJUSTES_LOCALES.get("usar_vad", True))

UMBRAL_VAD = 0.5               # probabilidad para EMPEZAR a considerar que hablas
UMBRAL_VAD_CONTINUAR = 0.35    # una vez hablando, basta esto para seguir (histeresis)
SILENCIO_MINIMO = 1.0          # espera base, para ordenes cortas
SILENCIO_MAXIMO = 2.6          # espera cuando ya venis hablando hace rato
SEGUNDOS_PARA_MAXIMO = 12.0    # a partir de aca se usa la espera larga
MAX_SEGUNDOS_FRASE = 120.0     # tope duro: un dictado puede ser largo de verdad
MIN_SEGUNDOS_FRASE = 0.4       # mas corto que esto suele ser un ruido
PREROLL_SEGUNDOS = 0.4         # audio previo que se conserva, para no comerse la "N"

# --- Iniciativa: que Nox te avise sin que lo llames (ver recordatorios.py) ---
# Los recordatorios que tu pides se avisan siempre que estas opciones esten encendidas; el
# saludo de la mañana viene APAGADO: Nox no empieza a hablarte solo hasta que lo activas.
AVISAR_RECORDATORIOS = bool(AJUSTES_LOCALES.get("avisar_recordatorios", True))
AVISOS_EN_VOZ = bool(AJUSTES_LOCALES.get("avisos_en_voz", True))
SALUDO_MATUTINO = bool(AJUSTES_LOCALES.get("saludo_matutino", False))

# Resumir cada conversacion al cerrarla y guardar lo que valga la pena (ver memoria.py). Apagado por
# defecto: es la persona quien decide si Nox guarda cosas de sus conversaciones.
MEMORIA_RESUMEN_SESION = bool(AJUSTES_LOCALES.get("memoria_resumen_sesion", False))

# --- Vista: mirar la pantalla (ver vista.py). APAGADA por defecto: una pantalla puede tener cualquier cosa. ---
VISTA_ACTIVA = bool(AJUSTES_LOCALES.get("vista_activa", False))
VISTA_PREGUNTAR = bool(AJUSTES_LOCALES.get("vista_preguntar", True))   # pedir permiso cada vez
MODELO_VISION = str(AJUSTES_LOCALES.get("modelo_vision") or "qwen3.5:4b")

# --- Permisos del sistema de archivos ---
# Lista blanca: Nox solo escribe aca adentro, y solo con estas extensiones.
CARPETA_TRABAJO = DOCUMENTOS / "Nox"
CARPETA_DOCUMENTOS = CARPETA_TRABAJO / "Documentos"  # los .docx/.odt que dicta Brian
CARPETAS_ESCRITURA = [
    CARPETA_TRABAJO,
    ESCRITORIO,
    DOCUMENTOS,
]
EXTENSIONES_ESCRITURA = {
    ".txt", ".md", ".csv", ".json", ".log", ".html", ".xml", ".yaml", ".yml", ".ini",
}
# Lectura: acceso amplio a la PC, por pedido de Brian (es su maquina local).
# None = sin restriccion de carpeta; se puede leer cualquier disco.
CARPETAS_LECTURA = None

# Aun con acceso amplio se siguen bloqueando los archivos de credenciales (.ssh,
# .env, cookies del navegador, claves privadas). No es desconfianza hacia Nox: es que
# Nox lee paginas web, y una pagina maliciosa podria intentar que abra tu archivo de
# contraseñas y lo muestre. El bloqueo corta esa via.
# Ponelo en False si alguna vez necesitas que lea uno de esos archivos a proposito.
BLOQUEAR_ARCHIVOS_SENSIBLES = True

# Cuantas acciones que modifican algo puede encadenar Nox en un solo pedido. Un modelo
# confundido —o engañado por una pagina web— podria intentar hacer muchas cosas seguidas;
# esto corta la cadena. Subilo si te queda corto en tareas legitimas.
MAX_ACCIONES_POR_TURNO = 6

# --- Limites ---
TOP_K_DEFECTO = 5           # fragmentos que devuelve una busqueda semantica

# Cuanto pesan los fragmentos de Fuentes/ (material crudo) frente a Wiki/ (curado).
# 1.0 = igual que la wiki; mas bajo = solo aparecen si no hay nada curado que sirva.
PESO_FUENTES = 0.7
MAX_CHARS_FRAGMENTO = 1200  # recorte por fragmento al pasarlo al modelo
MAX_CHARS_NOTA = 8000       # recorte al leer una nota completa
MAX_CHARS_WEB = 6000        # recorte al leer una pagina web
MAX_ITERACIONES_TOOLS = 6   # cuantas rondas de herramientas permite por turno
MAX_TURNOS_LIMPIOS = 6      # turnos sin datos personales que se recuerdan para la nube

# La autocritica (que el modelo revise su propia respuesta) casi duplica el tiempo del
# turno. En la nube sale gratis en tiempo; en local, a 6.8 tok/s, un turno profundo con
# razonamiento + autocritica llego a tardar 161 s. Por eso va apagada en local.
REVISAR_EN_LOCAL = False


def recargar():
    """
    Vuelve a leer config_local.json y actualiza lo que se puede cambiar sin reiniciar: quien
    eres, el tono, el modelo, la nube, la boveda, la voz. La ventana de Ajustes la llama al
    guardar. Lo que NO cambia en caliente (los modelos de Whisper ya cargados) se aplica la
    proxima vez que se abra Nox.
    """
    global AJUSTES_LOCALES, EQUIPO, _PERFIL, MODELO_CHAT, NUM_CTX
    global MODELO_WHISPER, MODELO_WHISPER_ESCUCHA, WHISPER_DEVICE
    global BOVEDA, INDICE_DB, HAY_BOVEDA
    global USUARIO, ESTILO_USUARIO, PERFIL_USUARIO, TRATO, TONO
    global MOTOR_CHAT, MODELO_OPENROUTER, MODELO_NUBE
    global USAR_NUBE, USAR_VAD, VOZ_ACTIVA, VELOCIDAD_VOZ, CEDER_GPU_AL_JUGAR
    global AVISAR_RECORDATORIOS, AVISOS_EN_VOZ, SALUDO_MATUTINO, MEMORIA_RESUMEN_SESION
    global VISTA_ACTIVA, VISTA_PREGUNTAR, MODELO_VISION

    AJUSTES_LOCALES = _ajustes_locales()
    EQUIPO = _elegir(AJUSTES_LOCALES.get("equipo"), PERFILES_EQUIPO, EQUIPO_POR_DEFECTO)
    _PERFIL = PERFILES_EQUIPO[EQUIPO]

    MOTOR_CHAT = str(AJUSTES_LOCALES.get("motor_chat", "openrouter")).lower()
    MODELO_OPENROUTER = str(AJUSTES_LOCALES.get("modelo_openrouter", "google/gemma-4-31b-it:free")).strip()
    MODELO_CHAT = _ajuste("modelo_chat")
    MODELO_NUBE = str(AJUSTES_LOCALES.get("modelo_nube", MODELO_OPENROUTER)).strip()
    NUM_CTX = _ajuste("num_ctx")
    MODELO_WHISPER = _ajuste("modelo_whisper")
    MODELO_WHISPER_ESCUCHA = _ajuste("modelo_whisper_escucha")
    WHISPER_DEVICE = _ajuste("whisper_device")

    BOVEDA = _buscar_boveda()
    INDICE_DB = BOVEDA / "RAG" / "index.db"
    HAY_BOVEDA = INDICE_DB.exists()

    USUARIO = _nombre_usuario()
    ESTILO_USUARIO = str(AJUSTES_LOCALES.get("estilo") or "").strip()
    PERFIL_USUARIO = str(AJUSTES_LOCALES.get("perfil") or "").strip()
    TRATO = _elegir(AJUSTES_LOCALES.get("trato"), TRATOS, "tu")
    TONO = _elegir(AJUSTES_LOCALES.get("tono"), TONOS, "natural")

    USAR_NUBE = bool(AJUSTES_LOCALES.get("usar_nube", True))
    USAR_VAD = bool(AJUSTES_LOCALES.get("usar_vad", True))
    VOZ_ACTIVA = bool(AJUSTES_LOCALES.get("voz_activa", True))
    VELOCIDAD_VOZ = float(AJUSTES_LOCALES.get("velocidad_voz", 1.0))
    CEDER_GPU_AL_JUGAR = bool(AJUSTES_LOCALES.get("ceder_gpu_al_jugar", True))
    AVISAR_RECORDATORIOS = bool(AJUSTES_LOCALES.get("avisar_recordatorios", True))
    AVISOS_EN_VOZ = bool(AJUSTES_LOCALES.get("avisos_en_voz", True))
    SALUDO_MATUTINO = bool(AJUSTES_LOCALES.get("saludo_matutino", False))
    MEMORIA_RESUMEN_SESION = bool(AJUSTES_LOCALES.get("memoria_resumen_sesion", False))
    VISTA_ACTIVA = bool(AJUSTES_LOCALES.get("vista_activa", False))
    VISTA_PREGUNTAR = bool(AJUSTES_LOCALES.get("vista_preguntar", True))
    MODELO_VISION = str(AJUSTES_LOCALES.get("modelo_vision") or "qwen3.5:4b")
