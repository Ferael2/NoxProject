"""
Diagnostico de la voz: graba unos segundos de TU voz y mide cada etapa para decir donde falla.

    python diagnostico_voz.py              # usa la entrada de audio predeterminada del sistema
    python diagnostico_voz.py --listar     # muestra las entradas disponibles
    python diagnostico_voz.py --entrada 10 # prueba otra entrada (el numero de --listar)
    python diagnostico_voz.py --segundos 8

Cuando se pida, di una frase como "Nox, abre Steam, por favor". Revisa en orden:
  1. la entrada de audio (¿llega señal o esta casi muda?)
  2. el detector de voz (¿reconoce que hablas?)
  3. Whisper (¿entiende lo que dices?)
  4. la palabra de activacion (¿encuentra "Nox" y separa la orden?)
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

import config
import voz
import vad


def listar():
    import sounddevice as sd
    por_defecto = sd.default.device[0]
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            marca = "  <- predeterminada" if i == por_defecto else ""
            print(f"  {i:>2}  {d['name']}  ({d['max_input_channels']} canales){marca}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Diagnostico de la voz de Nox.")
    ap.add_argument("--listar", action="store_true", help="lista las entradas de audio y sale")
    ap.add_argument("--entrada", type=int, default=None, help="numero de la entrada a usar")
    ap.add_argument("--segundos", type=int, default=6)
    args = ap.parse_args()

    import sounddevice as sd
    if args.listar:
        listar()
        return 0

    dispositivo = args.entrada if args.entrada is not None else sd.default.device[0]
    try:
        nombre = sd.query_devices(dispositivo)["name"]
    except Exception as e:
        print(f"No encuentro esa entrada de audio: {e}")
        return 1
    print(f"Entrada de audio: [{dispositivo}] {nombre}")
    print(f"Perfil de equipo: {config.EQUIPO} · Whisper: {config.MODELO_WHISPER_ESCUCHA} (escucha) / "
          f"{config.MODELO_WHISPER} (dictado) · detector de voz: {'activo' if config.USAR_VAD else 'apagado'}\n")

    for n in (3, 2, 1):
        print(f"Preparate… {n}", flush=True)
        time.sleep(1)
    print(f'\n>>> HABLA AHORA ({args.segundos} s): "Nox, abre Steam, por favor" <<<', flush=True)
    audio = sd.rec(int(args.segundos * 16000), samplerate=16000, channels=1, dtype="float32", device=dispositivo)
    sd.wait()
    audio = audio.flatten()
    print("Listo, analizando…\n")

    # 1. Señal
    pico = float(np.abs(audio).max())
    medio = float(np.abs(audio).mean())
    print("1) ENTRADA DE AUDIO")
    print(f"   volumen medio {medio:.4f} · pico {pico:.3f}  (hablando normal, el pico suele pasar de 0.05)")
    if pico < 0.01:
        print("   ✗ La señal es casi nula: el micrófono no está captando. Revisa que sea el correcto en la "
              "configuración de sonido, que no esté silenciado, o prueba otra entrada con --listar / --entrada.")
    elif pico < 0.05:
        print("   ! La señal es muy baja: sube el volumen de entrada del micrófono (o acércate).")
    else:
        print("   ✓ Llega señal suficiente.")

    # 2. Detector de voz
    print("\n2) DETECTOR DE VOZ")
    detector = vad.crear()
    if detector is None:
        print("   ! No se pudo cargar: Nox usaría el volumen como respaldo.")
    else:
        trozos = [audio[i:i + 1600] for i in range(0, len(audio) - 1599, 1600)]
        ps = [detector.probabilidad(t) for t in trozos]
        con_voz = sum(p >= config.UMBRAL_VAD for p in ps)
        print(f"   {con_voz} de {len(ps)} trozos de 100 ms reconocidos como voz · probabilidad máxima {max(ps):.2f} "
              f"(umbral {config.UMBRAL_VAD})")
        if max(ps) < config.UMBRAL_VAD:
            print("   ✗ Nunca superó el umbral: Nox no se entera de que hablas. Si en el paso 1 había señal, el "
                  "audio puede estar procesado de más (supresor de ruido agresivo): prueba la entrada física.")
        else:
            print("   ✓ Reconoce tu voz.")
    gasto = sum(float(np.abs(audio[i:i + 1600]).mean()) >= config.UMBRAL_SILENCIO for i in range(0, len(audio) - 1599, 1600))
    print(f"   (con el umbral de volumen de antes: {gasto} trozos)")

    # 3. Whisper
    print("\n3) RECONOCIMIENTO (Whisper)")
    textos = {}
    for modelo in dict.fromkeys((config.MODELO_WHISPER_ESCUCHA, config.MODELO_WHISPER)):
        try:
            t = time.time()
            m = voz.crear_whisper(modelo)
            segmentos, _ = m.transcribe(audio, language=config.IDIOMA_VOZ, beam_size=config.BEAM_SIZE_ESCUCHA,
                                        condition_on_previous_text=False)
            textos[modelo] = " ".join(s.text.strip() for s in segmentos).strip()
            print(f"   {modelo:<7} ({time.time() - t:.0f} s): {textos[modelo]!r}")
        except Exception as e:
            print(f"   {modelo:<7} ✗ falló: {type(e).__name__}: {e}")
    if not any(textos.values()):
        print("   ✗ No transcribió nada. Si el paso 2 sí detectó voz, prueba hablar más fuerte y más cerca.")

    # 4. Palabra de activacion
    print("\n4) PALABRA DE ACTIVACIÓN")
    texto = textos.get(config.MODELO_WHISPER_ESCUCHA, "")
    if texto:
        orden = voz.EscuchaContinua._extraer_orden(texto)
        if orden is None:
            print(f'   ✗ En {texto!r} no encontré "{config.PALABRA_ACTIVACION}". Whisper lo escribió distinto; '
                  "dime qué texto salió y lo agrego a las variantes.")
        else:
            print(f'   ✓ Entiende la orden: {orden!r}')
    else:
        print("   (sin texto no hay nada que revisar)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
