"""
Detector de voz humana en tiempo real (VAD) para la escucha continua.

Hasta ahora Nox decidia "esto es voz" con un umbral de volumen: cualquier ruido mas fuerte
que `UMBRAL_SILENCIO` (un ventilador, el teclado, una puerta) arrancaba una grabacion y
gastaba CPU transcribiendola para nada, y una voz suave podia quedar por debajo del umbral y
no oirse. Un VAD no mide cuanto suena, mide si lo que suena PARECE VOZ.

El modelo es Silero VAD (MIT, ~2 MB, menos de 1 ms por bloque). No se agrega ninguna
dependencia: faster-whisper ya lo trae empaquetado y lo ejecuta con onnxruntime, que ya
esta instalado. Aca solo se usa en modo continuo (bloque a bloque), cosa que faster-whisper
no expone porque lo usa sobre audio ya grabado.

    detector = vad.crear()               # None si no se pudo cargar (se usa el volumen)
    p = detector.probabilidad(trozo)     # 0.0 (no es voz) .. 1.0 (es voz)
"""
import numpy as np

FRECUENCIA = 16000     # el modelo solo acepta 16 kHz (o 8 kHz)
VENTANA = 512          # muestras nuevas por paso: 32 ms
CONTEXTO = 64          # muestras del paso anterior que el modelo necesita ver


class DetectorDeVoz:
    def __init__(self):
        import onnxruntime
        from faster_whisper.utils import get_assets_path
        import os

        opciones = onnxruntime.SessionOptions()
        opciones.inter_op_num_threads = 1
        opciones.intra_op_num_threads = 1
        opciones.log_severity_level = 4
        self._sesion = onnxruntime.InferenceSession(
            os.path.join(get_assets_path(), "silero_vad_v6.onnx"),
            providers=["CPUExecutionProvider"], sess_options=opciones,
        )
        self.reiniciar()

    def reiniciar(self):
        """Olvida el estado interno. Se usa al terminar una frase, para empezar limpio."""
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._contexto = np.zeros(CONTEXTO, dtype=np.float32)
        self._pendiente = np.zeros(0, dtype=np.float32)
        self._ultima = 0.0

    def probabilidad(self, audio: np.ndarray) -> float:
        """
        Probabilidad de que el audio sea voz, de 0 a 1. Acepta cualquier largo: lo que no
        completa una ventana de 32 ms espera al proximo llamado. Si el audio abarca varias
        ventanas, devuelve la mas alta (con que haya un instante de voz, hay voz).
        """
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        buffer = np.concatenate([self._pendiente, audio])
        n_ventanas = len(buffer) // VENTANA
        self._pendiente = buffer[n_ventanas * VENTANA:]

        mejor = None
        for i in range(n_ventanas):
            ventana = buffer[i * VENTANA:(i + 1) * VENTANA]
            entrada = np.concatenate([self._contexto, ventana])[None, :]
            probs, self._h, self._c = self._sesion.run(
                None, {"input": entrada, "h": self._h, "c": self._c}
            )
            self._contexto = ventana[-CONTEXTO:]
            p = float(np.ravel(probs)[-1])
            mejor = p if mejor is None else max(mejor, p)

        if mejor is not None:
            self._ultima = mejor
        return self._ultima


def crear() -> DetectorDeVoz | None:
    """El detector, o None si no se puede cargar: entonces Nox sigue con el umbral de volumen."""
    try:
        return DetectorDeVoz()
    except Exception as e:  # falta onnxruntime, cambio el modelo empaquetado, etc.
        print(f"No pude cargar el detector de voz ({e}); uso el volumen como antes.")
        return None
