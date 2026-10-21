"""
Asistente personal local — version de terminal.

Usa el mismo nucleo que la interfaz grafica (gui.py). Si preferis ventana, corre esa.

Uso:
    python asistente.py

Comandos:
    /salir      terminar
    /limpiar    borrar el historial (la memoria permanente se mantiene)
    /pensar     alternar el modo razonamiento de Qwen3
    /voz        alternar que lea las respuestas en voz alta
    /hablar     dictar por microfono en vez de escribir
    /memoria    ver lo que tiene guardado en memoria permanente
    /tools      ver las herramientas disponibles
"""
import sys

import requests

import config
import herramientas
import memoria
import nucleo

# pythonw.exe (sin consola) deja sys.stdout en None, asi que hay que chequear.
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")


def _aviso_herramienta(nombre: str, args: dict):
    partes = []
    for k, v in args.items():
        v = str(v)
        partes.append(f"{k}={v[:60]}..." if len(v) > 60 else f"{k}={v}")
    print(f"  \033[90m[herramienta] {nombre}({', '.join(partes)})\033[0m")


def main():
    ok, mensaje = nucleo.verificar_ollama()
    if not ok:
        print(mensaje)
        sys.exit(1)

    conversacion = nucleo.Conversacion(al_usar_herramienta=_aviso_herramienta)
    voz_activa = False

    print("\033[1mAsistente local\033[0m — modelo:", config.MODELO_CHAT,
          "| boveda:", config.BOVEDA.name)
    print("Comandos: /salir  /limpiar  /pensar  /voz  /hablar  /memoria  /tools\n")

    while True:
        try:
            entrada = input("\033[1;36mvos>\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nHasta luego.")
            break

        if not entrada:
            continue

        # --- Comandos ---
        if entrada == "/salir":
            print("Hasta luego.")
            break

        if entrada == "/limpiar":
            conversacion.reiniciar()
            print("Historial borrado (la memoria permanente sigue ahi).\n")
            continue

        if entrada == "/pensar":
            conversacion.pensar = not conversacion.pensar
            estado = "activado" if conversacion.pensar else "desactivado"
            print(f"Modo razonamiento: {estado}\n")
            continue

        if entrada == "/voz":
            voz_activa = not voz_activa
            print(f"Lectura en voz alta: {'activada' if voz_activa else 'desactivada'}\n")
            continue

        if entrada == "/hablar":
            import voz as modulo_voz
            print(f"Grabando {config.SEGUNDOS_GRABACION}s... hablá ahora.")
            entrada = modulo_voz.escuchar_una_vez()
            if not entrada:
                print("No entendi nada.\n")
                continue
            print(f"\033[1;36mvos (voz)>\033[0m {entrada}")

        if entrada == "/memoria":
            recuerdos = memoria.listar()
            if not recuerdos:
                print("La memoria esta vacia.\n")
            else:
                for r in recuerdos:
                    print(f"  #{r['id']} ({r['categoria']}) {r['contenido']}")
                print()
            continue

        if entrada == "/tools":
            for e in herramientas.ESQUEMAS:
                f = e["function"]
                print(f"  - {f['name']}: {f['description'][:85]}...")
            print()
            continue

        # --- Turno normal ---
        try:
            respuesta = conversacion.enviar(entrada)
        except requests.RequestException as e:
            print(f"\033[31mError hablando con Ollama: {e}\033[0m\n")
            continue

        print(f"\n\033[1;32masistente>\033[0m {respuesta}\n")

        if voz_activa:
            import voz as modulo_voz
            modulo_voz.hablar(respuesta)


if __name__ == "__main__":
    main()
