"""
Como hablarle a quien usa Nox: tuteo o usted, un tono, y su propio texto libre.

Vive aparte porque lo usan tanto el prompt local (nucleo.py) como el de la nube (nube.py),
y esos dos modulos no pueden importarse entre si.
"""
import config


def trato_y_tono(tono: str | None = None, trato: str | None = None, extra: str | None = None) -> str:
    """
    El parrafo de "como hablarle", armado con lo que la persona eligio en Ajustes. El texto
    libre va al final, para que tenga la ultima palabra.

    Sin argumentos usa lo guardado. Con argumentos sirve para la VISTA PREVIA de la ventana de
    Ajustes: muestra como quedaria antes de guardar.
    """
    tono = tono if tono in config.TONOS else config.TONO
    trato = trato if trato in config.TRATOS else config.TRATO
    extra = config.ESTILO_USUARIO if extra is None else extra.strip()

    partes = [f"Trato: {config.TONOS[tono][1]} {config.TRATOS[trato]} Español neutral."]
    if tono != "detallado":
        partes.append("Respuestas concisas salvo que pida detalle.")
    if extra:
        partes.append(extra)
    return " ".join(partes)
