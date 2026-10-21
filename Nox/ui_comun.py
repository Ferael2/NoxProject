"""
Piezas de interfaz que comparten la ventana de Ajustes y el asistente de bienvenida.

Todas usan el tema de Nox (tema.py), asi que se ven como parte de la aplicacion y cambiar el
diseño sigue siendo tocar un solo archivo.
"""
import queue
import threading

import customtkinter as ctk

import tema


# --- Texto ---

def titulo(parent, texto: str, tamano: int = 18):
    ctk.CTkLabel(parent, text=texto, font=(tema.FUENTE, tamano, "bold"), text_color=tema.TEXTO,
                 anchor="w", justify="left").pack(fill="x", pady=(0, 4))


def parrafo(parent, texto: str, color: str = None, ancho: int = 560, pady=(0, 10)):
    """Texto de apoyo que se ajusta al ancho en vez de salirse de la ventana."""
    etiqueta = ctk.CTkLabel(parent, text=texto, font=tema.ETIQUETA, text_color=color or tema.TEXTO_TENUE,
                            anchor="w", justify="left", wraplength=ancho)
    etiqueta.pack(fill="x", pady=pady)
    return etiqueta


def campo(parent, pregunta: str, ayuda: str = "", ancho: int = 560):
    """Una pregunta con su ayuda debajo; el widget se agrega despues con .pack()."""
    ctk.CTkLabel(parent, text=pregunta, font=tema.CUERPO_BOLD, text_color=tema.TEXTO,
                 anchor="w", justify="left").pack(fill="x", pady=(16, 0))
    if ayuda:
        parrafo(parent, ayuda, ancho=ancho, pady=(2, 6))
    else:
        ctk.CTkFrame(parent, height=6, fg_color="transparent").pack()


def separador(parent):
    ctk.CTkFrame(parent, height=1, fg_color=tema.BORDE, corner_radius=0).pack(fill="x", pady=(18, 0))


# --- Controles ---

def entrada(parent, valor: str = "", placeholder: str = "", ancho: int = 380, oculto: bool = False):
    e = ctk.CTkEntry(parent, width=ancho, height=36, font=tema.CUERPO, fg_color=tema.ELEVADO,
                     border_color=tema.BORDE, text_color=tema.TEXTO, placeholder_text=placeholder,
                     placeholder_text_color=tema.TEXTO_TENUE, corner_radius=tema.RADIO_CHICO,
                     show="•" if oculto else "")
    if valor:
        e.insert(0, valor)
    e.pack(anchor="w")
    return e


def caja_texto(parent, valor: str = "", alto: int = 90, ancho: int = 560):
    c = ctk.CTkTextbox(parent, width=ancho, height=alto, font=tema.CUERPO, fg_color=tema.ELEVADO,
                       border_color=tema.BORDE, border_width=1, text_color=tema.TEXTO,
                       corner_radius=tema.RADIO_CHICO, wrap="word")
    c.insert("1.0", valor)
    c.pack(anchor="w")
    return c


def leer_caja(caja) -> str:
    return caja.get("1.0", "end").strip()


def menu(parent, valores: list[str], valor: str, comando=None, ancho: int = 300):
    m = ctk.CTkOptionMenu(parent, values=valores, width=ancho, height=34, font=tema.CUERPO,
                          dropdown_font=tema.CUERPO, fg_color=tema.ELEVADO, button_color=tema.BORDE,
                          button_hover_color=tema.AZUL_APAGADO, text_color=tema.TEXTO,
                          dropdown_fg_color=tema.SUPERFICIE, dropdown_hover_color=tema.ELEVADO,
                          dropdown_text_color=tema.TEXTO, corner_radius=tema.RADIO_CHICO, command=comando)
    m.set(valor)
    m.pack(anchor="w")
    return m


def segmentado(parent, valores: list[str], valor: str, comando=None):
    s = ctk.CTkSegmentedButton(parent, values=valores, font=tema.CUERPO, fg_color=tema.ELEVADO,
                               selected_color=tema.AZUL, selected_hover_color=tema.AZUL_HOVER,
                               unselected_color=tema.ELEVADO, unselected_hover_color=tema.BORDE,
                               text_color=tema.TEXTO, corner_radius=tema.RADIO_CHICO, command=comando)
    s.set(valor)
    s.pack(anchor="w")
    return s


def interruptor(parent, texto: str, valor: bool, comando=None, variable=None):
    """Devuelve (widget, BooleanVar). Va con su texto al lado, como en las apps del sistema."""
    variable = variable if variable is not None else ctk.BooleanVar(value=bool(valor))
    w = ctk.CTkSwitch(parent, text=texto, variable=variable, command=comando, font=tema.CUERPO,
                      text_color=tema.TEXTO, progress_color=tema.AZUL, button_color=tema.TEXTO_SUAVE,
                      button_hover_color=tema.TEXTO, fg_color=tema.BORDE, width=44, height=22)
    w.pack(anchor="w", pady=(10, 0))
    return w, variable


def boton(parent, texto: str, comando, primario: bool = False, ancho: int = 130, lado: str = None):
    if primario:
        b = ctk.CTkButton(parent, text=texto, width=ancho, height=34, command=comando, font=tema.CUERPO_BOLD,
                          fg_color=tema.AZUL, hover_color=tema.AZUL_HOVER, text_color="#FFFFFF",
                          corner_radius=tema.RADIO_CHICO)
    else:
        b = ctk.CTkButton(parent, text=texto, width=ancho, height=34, command=comando, font=tema.CUERPO,
                          fg_color="transparent", hover_color=tema.ELEVADO, text_color=tema.TEXTO_SUAVE,
                          border_width=1, border_color=tema.BORDE, corner_radius=tema.RADIO_CHICO)
    if lado:
        b.pack(side=lado)
    return b


def barra(parent, ancho: int = 380):
    b = ctk.CTkProgressBar(parent, width=ancho, height=8, fg_color=tema.ELEVADO,
                           progress_color=tema.AZUL, corner_radius=4)
    b.set(0)
    return b


# --- Trabajo en segundo plano ---

def en_hilo(ventana, trabajo, al_terminar=None):
    """
    Corre 'trabajo()' en un hilo y llama a 'al_terminar(ok, valor)' en el hilo de la interfaz.
    Si 'trabajo' falla, ok es False y 'valor' es la excepcion. Si la ventana se cerro mientras
    tanto, no se llama a nada. Se usa una cola revisada con after() porque Tk no es seguro de
    tocar desde otros hilos.
    """
    cola = queue.Queue()

    def correr():
        try:
            cola.put((True, trabajo()))
        except Exception as e:   # el hilo nunca debe morir en silencio
            cola.put((False, e))

    threading.Thread(target=correr, daemon=True).start()

    def revisar():
        try:
            ok, valor = cola.get_nowait()
        except queue.Empty:
            try:
                if ventana.winfo_exists():
                    ventana.after(120, revisar)
            except Exception:
                pass
            return
        try:
            if al_terminar and ventana.winfo_exists():
                al_terminar(ok, valor)
        except Exception:
            pass

    ventana.after(120, revisar)


class Progreso:
    """Un hilo escribe aqui el avance de una descarga; la interfaz lo lee para su barra."""

    def __init__(self):
        self.fraccion = 0.0
        self.texto = ""

    def __call__(self, fraccion: float, texto: str):
        self.fraccion, self.texto = fraccion, texto


def color_estado(estado: str) -> str:
    return {"conectado": tema.VERDE, "iniciando": tema.AMBAR, "deteniendo": tema.AMBAR,
            "error": tema.ROJO}.get(estado, tema.TEXTO_TENUE)


TEXTO_ESTADO = {"conectado": "conectado", "iniciando": "conectando…", "deteniendo": "deteniendo…",
                "error": "con error", "detenido": "apagado"}
