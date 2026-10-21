"""
Pruebas del detector de voz (Silero VAD) de la escucha continua.

    python test_voz.py

Usa audio SINTETICO: la voz de Piper mezclada con ruidos fabricados (silencio, ruido
blanco, un ventilador grave, golpes de teclado). Sirve para comprobar la logica y comparar
contra el umbral de volumen anterior, pero NO reemplaza probarlo con un microfono real y
tu propia voz: un microfono capta eco, soplidos y un cuarto que aqui no existen.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

import config
import vad
import voz

fallos = []


def check(descripcion, condicion):
    if not condicion:
        fallos.append(descripcion)
    print(f"  [{'OK ' if condicion else 'FALLA'}] {descripcion}")


def sintetizar(texto: str):
    """Voz de Piper a 16 kHz mono, o None si la voz no esta instalada."""
    piper = voz._cargar_piper()
    if piper is None:
        return None
    partes, frecuencia = [], None
    for trozo in piper.synthesize(texto):
        partes.append(np.frombuffer(trozo.audio_int16_bytes, dtype=np.int16))
        frecuencia = trozo.sample_rate
    audio = np.concatenate(partes).astype(np.float32) / 32768
    n = int(len(audio) * 16000 / frecuencia)
    return np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)


def a_volumen(x, media):
    """Escala la senal para que su volumen medio (el que mide el umbral viejo) sea 'media'."""
    return (x / np.abs(x).mean() * media).astype(np.float32)


def porcentajes(senal, detector):
    """% de trozos de 100 ms que cada metodo da por 'voz': (volumen, vad)."""
    detector.reiniciar()
    trozos = [senal[i:i + 1600] for i in range(0, len(senal) - 1599, 1600)]
    por_volumen = sum(float(np.abs(t).mean()) >= config.UMBRAL_SILENCIO for t in trozos)
    por_vad = sum(detector.probabilidad(t) >= config.UMBRAL_VAD for t in trozos)
    return 100 * por_volumen / len(trozos), 100 * por_vad / len(trozos)


print("=== El detector carga y es rapido ===")
detector = vad.crear()
check("el modelo de Silero se carga (viene dentro de faster-whisper)", detector is not None)
if detector is None:
    sys.exit(1)

rng = np.random.default_rng(0)
seg = 6 * 16000

print("\n=== Ruidos que NO son voz ===")
ruidos = {
    "silencio": rng.normal(0, 1e-4, seg).astype(np.float32),
    "ruido blanco": a_volumen(rng.normal(0, 1, seg), 0.02),
    "ventilador (grave)": a_volumen(np.convolve(rng.normal(0, 1, seg), np.ones(200) / 200, "same"), 0.03),
    "teclado": np.where((np.arange(seg) % 6400) < 160, rng.normal(0, 0.4, seg), 0).astype(np.float32),
}
for nombre, senal in ruidos.items():
    vol, v = porcentajes(senal, detector)
    check(f"{nombre}: el VAD no lo toma por voz ({v:.0f} %; el umbral de volumen daba {vol:.0f} %)", v < 5)

print("\n=== Voz ===")
habla = sintetizar("Nox, abre Steam por favor, y después pon música para programar.")
if habla is None:
    print("  (la voz de Piper no esta instalada: se omiten estas pruebas)")
else:
    segundos_voz = len(habla) / 16000
    esperado = 100 * segundos_voz / (len(habla) // 1600 * 0.1)   # la frase ocupa todo el audio
    casos = {
        "voz normal": a_volumen(habla, 0.05),
        "voz muy baja": a_volumen(habla, 0.004),
        "voz con ruido de fondo": a_volumen(habla, 0.05) + a_volumen(rng.normal(0, 1, len(habla)), 0.02),
    }
    for nombre, senal in casos.items():
        vol, v = porcentajes(senal.astype(np.float32), detector)
        check(f"{nombre}: el VAD la detecta ({v:.0f} % de los trozos; el volumen daba {vol:.0f} %)", v >= 60)
    por_volumen, por_vad = porcentajes(casos["voz muy baja"].astype(np.float32), detector)
    check("una voz baja que el umbral de volumen se perdia, el VAD si la oye",
          por_volumen < 40 and por_vad >= 60)

print("\n=== Velocidad ===")
import time
trozo = ruidos["ruido blanco"][:1600]
t = time.time()
for _ in range(200):
    detector.probabilidad(trozo)
ms = (time.time() - t) / 200 * 1000
check(f"analizar 100 ms de audio tarda {ms:.2f} ms (limite: 10 ms)", ms < 10)

print("\n=== Si el detector falla, Nox sigue con el volumen ===")
from unittest import mock
with mock.patch.object(vad, "DetectorDeVoz", side_effect=RuntimeError("sin modelo")):
    check("vad.crear() devuelve None en vez de romper", vad.crear() is None)

print("\n=== Dentro de la escucha continua (micrófono simulado) ===")
import threading
from unittest import mock

TROZO = 1600


class MicrofonoFalso:
    """Entrega el audio en trozos de 100 ms, como sounddevice, y apaga la escucha al acabarse."""

    def __init__(self, audio, escucha):
        self.trozos = [audio[i:i + TROZO] for i in range(0, len(audio) - TROZO + 1, TROZO)]
        self.escucha = escucha

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n):
        if not self.trozos:
            self.escucha._corriendo.clear()
            return np.zeros((n, 1), dtype=np.float32), False
        return self.trozos.pop(0).reshape(-1, 1), False


class WhisperFalso:
    def __init__(self):
        self.llamadas = 0

    def transcribe(self, audio, **kwargs):
        self.llamadas += 1
        return [mock.Mock(text=" Nox, abre Steam")], None


def correr_escucha(audio, usar_vad):
    whisper = WhisperFalso()
    ordenes = []
    escucha = voz.EscuchaContinua(al_activarse=ordenes.append)
    escucha._modelo = whisper
    escucha._corriendo.set()
    with mock.patch.object(config, "USAR_VAD", usar_vad), \
            mock.patch("sounddevice.InputStream", lambda **kw: MicrofonoFalso(audio, escucha)), \
            mock.patch("vocabulario.construir", return_value=""):
        hilo = threading.Thread(target=escucha._bucle)
        hilo.start()
        hilo.join(timeout=60)
    return whisper.llamadas, ordenes


if habla is None:
    print("  (la voz de Piper no esta instalada: se omite)")
else:
    ventilador = a_volumen(np.convolve(rng.normal(0, 1, 5 * 16000), np.ones(200) / 200, "same"), 0.03)
    silencio = np.zeros(2 * 16000, dtype=np.float32)
    # 5 s de ventilador, 2 s de silencio, la frase, y 4 s de silencio para que termine
    audio = np.concatenate([ventilador, silencio, a_volumen(habla, 0.05), np.zeros(4 * 16000, dtype=np.float32)])
    audio = audio.astype(np.float32)

    llamadas, ordenes = correr_escucha(audio, usar_vad=True)
    check(f"con VAD: Whisper se llama solo para la frase, no para el ventilador ({llamadas} vez)", llamadas == 1)
    check(f"con VAD: se entiende la orden ({ordenes})", len(ordenes) == 1 and "steam" in ordenes[0].lower())

    antes, _ = correr_escucha(audio, usar_vad=False)
    check(f"con el volumen de antes, Whisper se llamaba {antes} veces (gastando CPU en el ventilador)", antes > llamadas)

print("\n" + "=" * 60)
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("TODAS LAS PRUEBAS DE VOZ PASARON")
