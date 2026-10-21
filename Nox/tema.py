"""
Paleta y tipografia de la interfaz.

Diseño tomado del lenguaje visual de Claude, en negro y azul:
  - jerarquia por espaciado y peso tipografico, no por lineas y cajas
  - un solo color de acento, usado con moderacion
  - bordes casi invisibles: separan sin dibujar rejas
  - mucho aire alrededor del texto

Todo lo visual vive aca para poder cambiarlo sin tocar la logica de la ventana.
"""
import plataforma

# --- Fondos, del mas profundo al mas cercano ---
FONDO = "#0A0C10"          # el lienzo
SUPERFICIE = "#12151C"     # barras y paneles
ELEVADO = "#1A1F29"        # burbujas del asistente, campos
BORDE = "#232936"          # separadores apenas visibles
BORDE_SUAVE = "#1B212B"

# --- Azules ---
AZUL = "#4C8DFF"           # acento principal
AZUL_HOVER = "#6BA1FF"
AZUL_HUNDIDO = "#3A6FD8"
AZUL_TENUE = "#1E3A6B"     # fondo de las burbujas del usuario
AZUL_APAGADO = "#2A4A80"

# --- Texto ---
TEXTO = "#E8EBF0"          # principal
TEXTO_SUAVE = "#9AA4B5"    # secundario
TEXTO_TENUE = "#5D6675"    # metadatos, marcas de tiempo

# --- Estados ---
VERDE = "#4ADE80"          # listo
AMBAR = "#FBBF24"          # trabajando
ROJO = "#F87171"           # error
ROJO_HUNDIDO = "#DC5555"

# --- Tipografia ---
# Cada sistema tiene sus fuentes; si alguna faltara, Tk usa la de por defecto.
if plataforma.ES_WINDOWS:
    FUENTE = "Segoe UI"
    MONO = "Consolas"
else:
    FUENTE = "Noto Sans"       # la de KDE Plasma
    MONO = "Noto Sans Mono"

TITULO = (FUENTE, 15, "bold")
CUERPO = (FUENTE, 13)
CUERPO_BOLD = (FUENTE, 13, "bold")
ETIQUETA = (FUENTE, 11)
ETIQUETA_BOLD = (FUENTE, 11, "bold")
MICRO = (FUENTE, 10)
CODIGO = (MONO, 11)

# --- Espaciado ---
RADIO = 10                 # esquinas redondeadas
RADIO_CHICO = 6
AIRE = 16                  # margen exterior
AIRE_CHICO = 8


def color_origen(origen: str) -> str:
    """Azul si la respuesta vino de la nube, gris si fue local."""
    return AZUL if origen and origen.startswith("nube") else TEXTO_TENUE
