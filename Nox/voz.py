"""
Voz del asistente: escuchar (STT) y hablar (TTS). Todo local y gratuito.

- Escuchar: faster-whisper, el modelo de OpenAI corriendo en CPU. Se descarga una
  sola vez la primera vez que se usa.
- Hablar: Piper, una voz neuronal local (voces/es_MX-claude-high.onnx). Si fallara,
  cae a la voz del sistema: SAPI en Windows, espeak-ng en Linux. Suenan roboticas pero
  no necesitan descargar nada.

Ambas partes se cargan de forma perezosa: si nunca usas la voz, no se carga nada.
"""
import os
import queue
import re
import sys
import threading

import numpy as np

import config
import plataforma
import vad

# pythonw.exe (sin consola) deja sys.stdout en None, asi que hay que chequear.
plataforma.configurar_salida()

_modelo_whisper = None
_voz_piper = None
_lock_tts = threading.Lock()
_detener_habla = threading.Event()


# --- Escuchar ---

def crear_whisper(nombre: str):
    """
    Carga un modelo de Whisper donde diga la configuracion (config.WHISPER_DEVICE).

    En CPU va con int8: rapido y suficiente para dictado. En una GPU NVIDIA es mucho mas
    rapido, pero necesita las librerias CUDA 12 + cuDNN 9 (ver INSTALACION.md) y le quita
    memoria de video al modelo de conversacion. Si la GPU falla por lo que sea, se usa la CPU
    en vez de dejar a Nox sin oidos.
    """
    from faster_whisper import WhisperModel

    if config.WHISPER_DEVICE != "cpu":
        try:
            modelo = WhisperModel(nombre, device=config.WHISPER_DEVICE,
                                  compute_type=config.WHISPER_COMPUTE_GPU)
            # Las librerias CUDA se cargan recien al transcribir: probar ahora, no en medio
            # de una frase.
            list(modelo.transcribe(np.zeros(16000, dtype=np.float32))[0])
            return modelo
        except Exception as e:
            print(f"No pude usar la GPU para Whisper ({e}); uso la CPU.")
    return WhisperModel(nombre, device="cpu", compute_type="int8")


def _cargar_whisper():
    global _modelo_whisper
    if _modelo_whisper is None:
        _modelo_whisper = crear_whisper(config.MODELO_WHISPER)
    return _modelo_whisper


def transcribir(audio: np.ndarray) -> str:
    """
    Convierte audio (float32, 16 kHz, mono) a texto.

    Los ajustes importantes:
    - initial_prompt: le da a Whisper el vocabulario de Brian (sus juegos, programas y
      temas). Sin esto escribe "fasmofobia" en vez de "Phasmophobia".
    - beam_size 5: explora varias transcripciones y se queda con la mejor, en vez de ir
      palabra por palabra. Es lo que evita que se coma pedazos.
    - condition_on_previous_text False: evita que arrastre errores de una frase a la
      siguiente, que es lo que hace que "suponga" palabras.
    """
    import vocabulario

    modelo = _cargar_whisper()
    segmentos, _ = modelo.transcribe(
        audio,
        language=config.IDIOMA_VOZ,
        vad_filter=True,
        initial_prompt=vocabulario.construir(),
        beam_size=config.BEAM_SIZE,
        best_of=config.BEAM_SIZE,
        condition_on_previous_text=False,
        temperature=[0.0, 0.2, 0.4],  # si no esta seguro, reintenta con mas libertad
        no_speech_threshold=0.5,
    )
    return " ".join(s.text.strip() for s in segmentos).strip()


class Grabadora:
    """
    Graba del microfono hasta que se le dice basta. Sin limite de tiempo: se corta
    cuando Brian aprieta el boton, asi puede dictar todo lo que quiera.

    Informa los segundos grabados por callback para que la interfaz muestre el avance.
    """

    def __init__(self, al_grabar=None):
        self._cola = queue.Queue()
        self._stream = None
        self.grabando = False
        self.al_grabar = al_grabar or (lambda segundos: None)
        self._muestras = 0

    def iniciar(self):
        import sounddevice as sd

        self._cola = queue.Queue()
        self.grabando = True
        self._muestras = 0

        def callback(indata, frames, tiempo, estado):
            if self.grabando:
                self._cola.put(indata.copy())
                self._muestras += frames
                self.al_grabar(self._muestras / config.FRECUENCIA_AUDIO)

        self._stream = sd.InputStream(
            samplerate=config.FRECUENCIA_AUDIO,
            channels=1,
            dtype="float32",
            callback=callback,
        )
        self._stream.start()

    def detener(self) -> np.ndarray:
        """Corta la grabacion y devuelve el audio junto."""
        self.grabando = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        trozos = []
        while not self._cola.empty():
            trozos.append(self._cola.get())

        if not trozos:
            return np.array([], dtype=np.float32)
        return np.concatenate(trozos, axis=0).flatten()


def escuchar_una_vez(segundos: int = None) -> str:
    """Graba unos segundos fijos y devuelve el texto. Util para probar desde la terminal."""
    import sounddevice as sd

    segundos = segundos or config.SEGUNDOS_GRABACION
    audio = sd.rec(
        int(segundos * config.FRECUENCIA_AUDIO),
        samplerate=config.FRECUENCIA_AUDIO,
        channels=1,
        dtype="float32",
    )
    sd.wait()
    return transcribir(audio.flatten())


# --- Escucha continua con palabra de activacion ---

class EscuchaContinua:
    """
    Escucha el microfono todo el tiempo esperando la palabra de activacion ("Nox").

    Como funciona: graba en bloques cortos, descarta los que no son voz (para no gastar
    CPU transcribiendo ruido), y transcribe lo que si lo es con un modelo chico de Whisper.
    Si aparece la palabra, avisa. Que algo sea voz lo decide Silero VAD (ver vad.py); si no
    esta disponible se usa el volumen.

    No se usa un detector de wake word entrenado (tipo openWakeWord) porque esos
    traen un puñado de palabras fijas y "Nox" no es una de ellas — entrenar una
    propia seria un proyecto aparte. Esto funciona con cualquier palabra.
    """

    def __init__(self, al_activarse, al_oir=None, al_hablar=None):
        self.al_activarse = al_activarse    # recibe el texto dicho despues de "Nox"
        self.al_oir = al_oir or (lambda t: None)  # para mostrar lo que va escuchando
        # Avisa mientras Brian habla, con los segundos acumulados. Sirve para que la
        # interfaz muestre que sigue escuchando y no parezca colgada.
        self.al_hablar = al_hablar or (lambda segundos: None)
        self._hilo = None
        self._corriendo = threading.Event()
        self._modelo = None

    def _cargar_modelo(self):
        if self._modelo is None:
            self._modelo = crear_whisper(config.MODELO_WHISPER_ESCUCHA)
        return self._modelo

    def iniciar(self):
        if self._hilo is not None and self._hilo.is_alive():
            return
        self._corriendo.set()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()

    def detener(self):
        self._corriendo.clear()

    @property
    def activa(self) -> bool:
        return self._corriendo.is_set()

    @staticmethod
    def _trozos_de_espera(segundos_hablados: float) -> int:
        """
        Cuanto silencio hace falta para dar por terminado el mensaje, en trozos de 100 ms.

        Crece con lo que Brian ya lleva hablado: una orden suelta se despacha rapido,
        pero si viene dictando hace rato lo mas probable es que una pausa sea para
        pensar, no para terminar. Interpolacion lineal entre el minimo y el maximo.
        """
        proporcion = min(segundos_hablados / config.SEGUNDOS_PARA_MAXIMO, 1.0)
        espera = config.SILENCIO_MINIMO + proporcion * (
            config.SILENCIO_MAXIMO - config.SILENCIO_MINIMO
        )
        return max(1, int(espera / 0.1))

    def _bucle(self):
        """
        Escucha hasta que Brian TERMINA de hablar, no hasta su primera pausa.

        La primera version cortaba cada 3 segundos, lo que partia las frases al medio
        ("Nox, abri You" | "Tube Music") y hacia que las ordenes llegaran incompletas.
        Ahora se detecta cuando empezas y cuando dejas de hablar, y se transcribe la
        frase entera.
        """
        import sounddevice as sd

        modelo = self._cargar_modelo()
        # Detector de voz: distingue una voz de un ventilador o un teclado. Si no se puede
        # cargar, se cae al umbral de volumen de siempre.
        detector = vad.crear() if config.USAR_VAD else None

        muestras_trozo = int(0.1 * config.FRECUENCIA_AUDIO)   # analizar cada 100 ms
        max_trozos = int(config.MAX_SEGUNDOS_FRASE / 0.1)
        trozos_preroll = int(config.PREROLL_SEGUNDOS / 0.1)

        preroll = []      # audio justo anterior a detectar voz (para no comerse la "N")
        frase = []        # audio de la frase en curso
        silencios = 0     # trozos seguidos sin voz
        con_voz = 0       # trozos CON voz acumulados (mide cuanto hablo de verdad)
        hablando = False

        try:
            with sd.InputStream(
                samplerate=config.FRECUENCIA_AUDIO, channels=1, dtype="float32",
                blocksize=muestras_trozo,
            ) as stream:
                while self._corriendo.is_set():
                    trozo, _ = stream.read(muestras_trozo)
                    if not self._corriendo.is_set():
                        break

                    trozo = trozo.flatten()
                    if detector is not None:
                        # Histeresis: para EMPEZAR a oir hace falta estar seguro; una vez
                        # hablando, una pausa corta o una "s" suave no cuentan como silencio.
                        umbral = config.UMBRAL_VAD_CONTINUAR if hablando else config.UMBRAL_VAD
                        hay_voz = detector.probabilidad(trozo) >= umbral
                    else:
                        hay_voz = float(np.abs(trozo).mean()) >= config.UMBRAL_SILENCIO

                    if not hablando:
                        # Guardar un poco de audio previo por si arranca a hablar ahora.
                        preroll.append(trozo)
                        if len(preroll) > trozos_preroll:
                            preroll.pop(0)

                        if hay_voz:
                            hablando = True
                            frase = list(preroll) + [trozo]
                            preroll = []
                            silencios, con_voz = 0, 1
                        continue

                    # Ya esta hablando: acumular hasta que TERMINE, no hasta la primera
                    # pausa. El silencio tambien se guarda: es parte de la frase.
                    frase.append(trozo)
                    if hay_voz:
                        silencios = 0
                        con_voz += 1
                    else:
                        silencios += 1

                    segundos_hablados = con_voz * 0.1
                    self.al_hablar(segundos_hablados)

                    termino = silencios >= self._trozos_de_espera(segundos_hablados)
                    demasiado_larga = len(frase) >= max_trozos

                    if not (termino or demasiado_larga):
                        continue

                    audio = np.concatenate(frase)
                    hablando, frase, silencios, con_voz = False, [], 0, 0
                    if detector is not None:
                        detector.reiniciar()  # cada frase empieza con el detector limpio

                    # Frases demasiado cortas suelen ser un golpe o un ruido.
                    if audio.size < config.FRECUENCIA_AUDIO * config.MIN_SEGUNDOS_FRASE:
                        continue

                    try:
                        import vocabulario
                        segmentos, _ = modelo.transcribe(
                            audio,
                            language=config.IDIOMA_VOZ,
                            vad_filter=True,
                            initial_prompt=vocabulario.construir(),
                            beam_size=config.BEAM_SIZE_ESCUCHA,
                            condition_on_previous_text=False,
                            no_speech_threshold=0.5,
                        )
                        texto = " ".join(s.text.strip() for s in segmentos).strip()
                    except Exception:
                        continue

                    if not texto:
                        continue

                    self.al_oir(texto)
                    orden = self._extraer_orden(texto)
                    if orden is not None:
                        self.al_activarse(orden)
        except Exception as e:
            print(f"Se corto la escucha continua: {e}")
            self._corriendo.clear()

    @staticmethod
    def _parecido_al_nombre(palabra: str) -> bool:
        """
        Whisper escribe "Nox" de muchas formas segun como suene: Knox, Nocs, Nogs,
        Noc, Nox... Enumerarlas todas es una carrera perdida, asi que se compara por
        similitud ademas de por la lista.
        """
        from difflib import SequenceMatcher

        limpia = palabra.lower().strip(" .,;:¿?¡!\"'()")
        if not limpia:
            return False
        if limpia in config.VARIANTES_ACTIVACION:
            return True
        # Entre 3 y 5 letras: menos de 3 hace que "no" active ("no se que hacer..."),
        # mas de 5 haria que "nosotros" o "noche" activen por parecido.
        if not (3 <= len(limpia) <= 5):
            return False
        return SequenceMatcher(None, limpia, config.PALABRA_ACTIVACION).ratio() >= 0.7

    @classmethod
    def _extraer_orden(cls, texto: str) -> str | None:
        """
        Busca el nombre y devuelve el resto de la frase como orden.

        Al hablar natural el nombre no siempre va primero: "Nox, abri Steam" pero
        tambien "como estas Nox", "hola Nox", "abrime Steam Nox". Asi que se busca en
        las primeras posiciones Y en las ultimas, y la orden es TODO lo demas, venga
        antes o despues.

        No se busca en el medio de una frase larga a proposito: ahi "nox" casi siempre
        significa que estan hablando DE el ("el problema es que nox no anda"), no
        con el.

        Devuelve None si no se lo llamo, o la orden (posiblemente vacia si solo dijo
        el nombre).
        """
        palabras = texto.split()
        if not palabras:
            return None

        n = len(palabras)
        for i, palabra in enumerate(palabras):
            if not cls._parecido_al_nombre(palabra):
                continue
            if not cls._es_vocativo(palabras, i, n):
                continue
            resto = palabras[:i] + palabras[i + 1:]
            return " ".join(resto).strip(" .,;:¿?¡!")
        return None

    @staticmethod
    def _es_vocativo(palabras: list[str], i: int, n: int) -> bool:
        """
        Distingue "le estoy hablando a Nox" de "estoy hablando de Nox".

        La posicion sola no alcanza: en "hey Nox" y en "ayer instale nox" el nombre
        cae igual de cerca del principio, pero solo el primero se le dirige a el.
        Lo que los separa es lo que viene ANTES: un saludo o una interjeccion abren
        una interpelacion; un verbo convierte al nombre en objeto de la frase.
        """
        # Primera palabra: casi siempre lo esta llamando ("Nox, abri Steam").
        if i == 0:
            return True

        # Ultimas dos: tambien ("abrime Steam, Nox" / "como estas Nox").
        if i >= n - 2:
            return True

        # En el medio del arranque, solo si todo lo anterior es preambulo de saludo.
        preambulo = [p.lower().strip(" .,;:¿?¡!") for p in palabras[:i]]
        return bool(preambulo) and all(p in config.PREAMBULOS for p in preambulo)

    @staticmethod
    def es_solo_llamada(orden: str) -> bool:
        """
        True si lo que dijo es solo para llamar su atencion, sin contenido todavia.

        "Hey Nox" o "decime Nox" piden atencion: corresponde contestar y esperar. En
        cambio "hola Nox" o "como estas Nox" ya son un mensaje completo y merecen una
        respuesta de verdad, no un "¿si?".
        """
        limpio = orden.lower().strip(" .,;:¿?¡!")
        if not limpio:
            return True
        return limpio in config.LLAMADAS_DE_ATENCION


# --- Hablar ---

def _cargar_piper():
    """Carga la voz neuronal de Piper. Devuelve None si no esta disponible."""
    global _voz_piper
    if _voz_piper is False:  # ya se intento y fallo, no reintentar en cada frase
        return None
    if _voz_piper is None:
        if not config.VOZ_PIPER.exists():
            _voz_piper = False
            return None
        try:
            from piper import PiperVoice
            _voz_piper = PiperVoice.load(str(config.VOZ_PIPER))
        except Exception as e:
            print(f"No pude cargar Piper ({e}); uso la voz del sistema.")
            _voz_piper = False
            return None
    return _voz_piper


def _hablar_piper(texto: str) -> bool:
    """Sintetiza y reproduce con Piper. False si no pudo (para caer al respaldo)."""
    voz = _cargar_piper()
    if voz is None:
        return False

    try:
        import sounddevice as sd
        from piper import SynthesisConfig

        cfg = SynthesisConfig(length_scale=config.VELOCIDAD_VOZ)

        # Se reproduce chunk por chunk: empieza a sonar sin esperar la frase entera.
        stream = None
        for chunk in voz.synthesize(texto, syn_config=cfg):
            muestras = np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
            if stream is None:
                stream = sd.OutputStream(
                    samplerate=chunk.sample_rate, channels=1, dtype="int16"
                )
                stream.start()
            if _detener_habla.is_set():
                break
            stream.write(muestras)

        if stream is not None:
            stream.stop()
            stream.close()
        return True
    except Exception as e:
        print(f"Fallo Piper al reproducir ({e}); uso la voz del sistema.")
        return False


def _hablar_espeak(texto: str) -> bool:
    """
    Respaldo en Linux si Piper falla: espeak-ng, en español latino. False si no esta
    instalado (Arch: sudo pacman -S espeak-ng; Debian/Ubuntu: sudo apt install espeak-ng).
    """
    import shutil

    espeak = shutil.which("espeak-ng")
    if espeak is None:
        print("Tampoco esta espeak-ng: no hay voz de respaldo.")
        return False

    return _decir_con_proceso([espeak, "-v", "es-419", "-s", str(config.VELOCIDAD_VOZ_RESPALDO), texto])


# Script de PowerShell para la voz de Windows (SAPI, via System.Speech). El texto no va
# dentro del script sino en una variable de entorno: asi las comillas o simbolos que
# traiga no se interpretan como codigo.
_SCRIPT_SAPI = (
    "Add-Type -AssemblyName System.Speech; "
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "$es = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'es*' } "
    "| Select-Object -First 1; "
    "if ($es) { $s.SelectVoice($es.VoiceInfo.Name) }; "
    "$s.Speak($env:NOX_TEXTO)"
)


def _hablar_sapi(texto: str) -> bool:
    """Respaldo en Windows si Piper falla: la voz que traiga el sistema, en español si hay."""
    return _decir_con_proceso(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _SCRIPT_SAPI],
        entorno={**os.environ, "NOX_TEXTO": texto},
    )


def _decir_con_proceso(comando: list[str], entorno=None) -> bool:
    """
    Corre una voz del sistema como proceso aparte, para poder cortarla con el boton de
    silencio.
    """
    import subprocess

    try:
        proceso = subprocess.Popen(
            comando, env=entorno,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            **plataforma.kwargs_sin_ventana(),
        )
    except OSError as e:
        print(f"No pude usar la voz del sistema: {e}")
        return False
    while proceso.poll() is None:
        if _detener_habla.wait(0.1):
            proceso.terminate()
            break
    return True


def _hablar_respaldo(texto: str) -> bool:
    return _hablar_sapi(texto) if plataforma.ES_WINDOWS else _hablar_espeak(texto)


def limpiar_para_voz(texto: str) -> str:
    """
    Saca el markdown antes de leer en voz alta: nadie quiere escuchar 'asterisco
    asterisco'. Tambien recorta bloques de codigo, que suenan horrible.
    """
    texto = re.sub(r"```.*?```", " (bloque de codigo) ", texto, flags=re.DOTALL)
    texto = re.sub(r"`([^`]*)`", r"\1", texto)
    texto = re.sub(r"\*\*([^*]*)\*\*", r"\1", texto)
    texto = re.sub(r"\*([^*]*)\*", r"\1", texto)
    texto = re.sub(r"^#{1,6}\s*", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"^\s*[-*]\s+", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"\[\[([^\]]*)\]\]", r"\1", texto)
    texto = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", texto)
    texto = re.sub(r"https?://\S+", " (enlace) ", texto)
    return re.sub(r"\n{2,}", ". ", texto).strip()


def hablar(texto: str):
    """
    Dice el texto en voz alta. Bloquea hasta terminar.
    Intenta con Piper (voz natural) y cae a la voz del sistema si no esta disponible.
    """
    if not texto.strip():
        return
    limpio = limpiar_para_voz(texto)

    with _lock_tts:
        _detener_habla.clear()
        if not _hablar_piper(limpio):
            _hablar_respaldo(limpio)


def callar():
    """Corta lo que este diciendo (para el boton de silencio de la interfaz)."""
    _detener_habla.set()


def hablar_async(texto: str) -> threading.Thread:
    """Habla sin bloquear la interfaz."""
    hilo = threading.Thread(target=hablar, args=(texto,), daemon=True)
    hilo.start()
    return hilo


def voces_disponibles() -> list[str]:
    """Las voces de Piper que hay en la carpeta voces/."""
    return sorted(p.stem for p in config.VOZ_PIPER.parent.glob("*.onnx"))
