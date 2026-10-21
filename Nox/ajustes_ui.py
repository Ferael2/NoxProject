"""
La ventana de Ajustes de Nox.

Todo lo que antes obligaba a editar archivos (tu nombre, como quieres que te hable, el perfil
de tu equipo, el modelo, la voz, la bóveda, la nube, las herramientas externas) se cambia
aqui, con la misma logica de validacion que usa el resto de Nox (ajustes.py, mcp_cliente.py).

Que se aplica al instante y que no:
  - Nombre, trato, tono, instrucciones, modelo, nube, bóveda, velocidad de la voz: al guardar.
  - Los modelos de Whisper (voz): al reiniciar Nox, porque ya estan cargados en memoria.
  - Las herramientas externas: en cuanto tocas el interruptor o la politica (no esperan a Guardar).
"""
import shlex
import shutil
from tkinter import filedialog

import customtkinter as ctk

import ajustes
import config
import mcp_cliente
import memoria
import modelos
import plataforma
import recordatorios
import tema
import ui_comun as ui
import vista
from ajustes import AjusteInvalido
from mcp_cliente import ConfigInvalida

# Nombres amigables de los perfiles de equipo.
NOMBRES_PERFIL = {
    "estandar_8gb": "Estándar (tarjeta de video de 8 GB)",
    "laptop_rtx4060": "Laptop con RTX 4060",
    "basico": "Básico (equipo modesto)",
}
AUTOMATICO = "Automático (el del perfil)"
POLITICAS_VISIBLES = {"bloquear": "Bloqueada", "preguntar": "Preguntar siempre", "permitir": "Permitir"}
POLITICA_DE_TEXTO = {v: k for k, v in POLITICAS_VISIBLES.items()}


class VentanaAjustes(ctk.CTkToplevel):
    PAGINAS = [("tu", "Tú"), ("equipo", "Equipo"), ("voz", "Voz"), ("memoria", "Memoria"),
               ("iniciativa", "Iniciativa"), ("vista", "Vista"), ("boveda", "Bóveda"), ("nube", "Nube"),
               ("externas", "Herramientas externas"), ("seguridad", "Seguridad")]

    def __init__(self, padre, al_guardar=None, al_reiniciar=None, pagina: str = "tu"):
        super().__init__(padre)
        self.padre = padre
        self.al_guardar = al_guardar or (lambda: None)
        self.al_reiniciar = al_reiniciar
        self.actual = ajustes.cargar()
        self._lectores = {}           # clave de ajuste -> funcion que lee su valor de la pantalla
        self._paginas_hechas = set()
        self._velocidad_original = config.VELOCIDAD_VOZ
        self._sondeo = None
        self._firma_externas = None
        self._cerrada = False

        self.title("Ajustes de Nox")
        self.geometry("900x680")
        self.minsize(760, 560)
        self.configure(fg_color=tema.FONDO)
        self.transient(padre)

        self._construir()
        self.protocol("WM_DELETE_WINDOW", self._cerrar)
        self.after(150, self._traer_al_frente)
        self._ir_a(pagina)

    def _traer_al_frente(self):
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    # ----------------------------------------------------------------- marco

    def _construir(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        lateral = ctk.CTkFrame(self, width=210, fg_color=tema.SUPERFICIE, corner_radius=0)
        lateral.grid(row=0, column=0, sticky="nsw", rowspan=2)
        lateral.grid_propagate(False)
        ctk.CTkLabel(lateral, text="Ajustes", font=tema.TITULO, text_color=tema.TEXTO,
                     anchor="w").pack(fill="x", padx=22, pady=(24, 14))
        self._botones = {}
        for clave, texto in self.PAGINAS:
            b = ctk.CTkButton(lateral, text=texto, anchor="w", height=38, font=tema.CUERPO,
                              fg_color="transparent", hover_color=tema.ELEVADO, text_color=tema.TEXTO_SUAVE,
                              corner_radius=tema.RADIO_CHICO, command=lambda c=clave: self._ir_a(c))
            b.pack(fill="x", padx=12, pady=2)
            self._botones[clave] = b

        self.contenido = ctk.CTkFrame(self, fg_color=tema.FONDO, corner_radius=0)
        self.contenido.grid(row=0, column=1, sticky="nsew")
        self.contenido.grid_columnconfigure(0, weight=1)
        self.contenido.grid_rowconfigure(0, weight=1)

        pie = ctk.CTkFrame(self, height=64, fg_color=tema.SUPERFICIE, corner_radius=0)
        pie.grid(row=1, column=1, sticky="ew")
        pie.grid_propagate(False)
        pie.grid_columnconfigure(0, weight=1)
        self.estado = ctk.CTkLabel(pie, text="", font=tema.ETIQUETA, text_color=tema.TEXTO_TENUE,
                                   anchor="w", justify="left", wraplength=420)
        self.estado.grid(row=0, column=0, padx=22, sticky="w")
        botones = ctk.CTkFrame(pie, fg_color="transparent")
        botones.grid(row=0, column=1, padx=18, pady=14, sticky="e")
        self.boton_reiniciar = ui.boton(botones, "Reiniciar ahora", self._reiniciar, ancho=130)
        ui.boton(botones, "Cerrar", self._cerrar, ancho=90, lado="left")
        self.boton_guardar = ui.boton(botones, "Guardar", self._guardar, primario=True, ancho=110)
        self.boton_guardar.pack(side="left", padx=(10, 0))
        self._paginas = {}

    def _ir_a(self, clave: str):
        for c, b in self._botones.items():
            b.configure(fg_color=tema.ELEVADO if c == clave else "transparent",
                        text_color=tema.AZUL if c == clave else tema.TEXTO_SUAVE)
        for c, marco in self._paginas.items():
            marco.grid_remove()
        if clave not in self._paginas:
            marco = ctk.CTkScrollableFrame(self.contenido, fg_color=tema.FONDO, corner_radius=0,
                                           scrollbar_button_color=tema.BORDE,
                                           scrollbar_button_hover_color=tema.AZUL_APAGADO)
            marco.grid(row=0, column=0, sticky="nsew", padx=(28, 12), pady=(10, 0))
            self._paginas[clave] = marco
            getattr(self, f"_pagina_{clave}")(marco)
        self._paginas[clave].grid()
        self._sondear(clave == "externas")

    def _mensaje(self, texto: str, color: str = None):
        self.estado.configure(text=texto, text_color=color or tema.TEXTO_TENUE)

    # ------------------------------------------------------------------ Tú

    def _pagina_tu(self, f):
        a = self.actual
        ui.titulo(f, "Tú")
        ui.parrafo(f, "Nox usa esto para dirigirse a ti, igual que las apps de IA te preguntan cómo quieres "
                      "que te hablen. Lo puedes cambiar cuando quieras.")

        ui.campo(f, "¿Cómo quieres que te llame?")
        self.e_usuario = ui.entrada(f, a.get("usuario", ""), placeholder=config.USUARIO)

        ui.campo(f, "Trato")
        self.s_trato = ui.segmentado(f, ["Tú", "Usted"], "Usted" if config.TRATO == "usted" else "Tú",
                                     comando=lambda _: self._actualizar_vista())

        ui.campo(f, "Tono")
        etiquetas = [t[0] for t in config.TONOS.values()]
        self.m_tono = ui.menu(f, etiquetas, config.TONOS[config.TONO][0], comando=lambda _: self._actualizar_vista())
        self.t_tono = ui.parrafo(f, "", pady=(6, 0))

        ui.campo(f, "Instrucciones para Nox",
                 "Cómo quieres que responda. Por ejemplo: «Sé breve», «Explícame con ejemplos» o "
                 "«Evita las metáforas».")
        self.c_estilo = ui.caja_texto(f, a.get("estilo", ""), alto=80)
        self.c_estilo.bind("<KeyRelease>", lambda e: self._actualizar_vista())

        ui.campo(f, "Lo que Nox debería saber de ti",
                 "Tus gustos, tu trabajo, tus proyectos… Solo se usa en tu equipo: esto NUNCA se envía a la nube.")
        self.c_perfil = ui.caja_texto(f, a.get("perfil", ""), alto=110)

        ui.separador(f)
        ui.campo(f, "Así le hablará Nox", "Vista previa de las instrucciones que recibe con lo de arriba.")
        self.t_vista = ui.parrafo(f, "", color=tema.TEXTO_SUAVE, pady=(0, 24))
        self._actualizar_vista()

        self._lectores.update({
            "usuario": lambda: self.e_usuario.get(),
            "trato": lambda: "usted" if self.s_trato.get() == "Usted" else "tu",
            "tono": lambda: self._clave_de_tono(self.m_tono.get()),
            "estilo": lambda: ui.leer_caja(self.c_estilo),
            "perfil": lambda: ui.leer_caja(self.c_perfil),
        })

    @staticmethod
    def _clave_de_tono(etiqueta: str) -> str:
        return next((k for k, (e, _) in config.TONOS.items() if e == etiqueta), "natural")

    def _actualizar_vista(self):
        import estilo
        tono = self._clave_de_tono(self.m_tono.get())
        trato = "usted" if self.s_trato.get() == "Usted" else "tu"
        self.t_tono.configure(text=config.TONOS[tono][1])
        self.t_vista.configure(text=estilo.trato_y_tono(tono, trato, ui.leer_caja(self.c_estilo)))

    # ---------------------------------------------------------------- Equipo

    def _pagina_equipo(self, f):
        a = self.actual
        ui.titulo(f, "Equipo")
        ui.parrafo(f, "El perfil decide qué modelo de IA se usa, cuánto contexto le cabe y dónde se procesa la voz. "
                      "Elige el que mejor describa tu equipo.")

        ui.campo(f, "Perfil de tu equipo")
        actual = config.EQUIPO
        self.m_perfil = ui.menu(f, list(NOMBRES_PERFIL.values()), NOMBRES_PERFIL[actual],
                                comando=lambda _: self._perfil_cambiado(), ancho=360)
        self.t_perfil = ui.parrafo(f, "", pady=(6, 0))
        fila = ctk.CTkFrame(f, fg_color="transparent")
        fila.pack(anchor="w", pady=(8, 0))
        ui.boton(fila, "Detectar mi equipo", self._detectar, ancho=160, lado="left")
        self.t_deteccion = ctk.CTkLabel(fila, text="", font=tema.ETIQUETA, text_color=tema.TEXTO_SUAVE,
                                        wraplength=380, justify="left", anchor="w")
        self.t_deteccion.pack(side="left", padx=14)
        self.b_usar_sugerencia = ui.boton(f, "Usar la sugerencia", lambda: None, ancho=170)
        self._sugerido = None

        ui.campo(f, "Modelo de conversación",
                 "Déjalo en automático salvo que quieras probar otro. Los de la lista son los que ya tienes descargados.")
        self.m_modelo = ui.menu(f, [AUTOMATICO], a.get("modelo_chat") or AUTOMATICO, ancho=360)
        ui.en_hilo(self, modelos.instalados, self._llenar_modelos)

        ui.campo(f, "Modelos necesarios", "Nox necesita estos para funcionar. Si falta alguno, se descarga desde aquí.")
        self.f_modelos = ctk.CTkFrame(f, fg_color="transparent")
        self.f_modelos.pack(anchor="w", fill="x")
        self._pintar_modelos()

        ui.separador(f)
        ui.campo(f, "Voz (avanzado)", "Estos cambios se aplican al reiniciar Nox.")
        ui.parrafo(f, "Dónde se procesa la voz. «cuda» solo funciona con tarjeta NVIDIA y librerías CUDA 12 + cuDNN 9; "
                      "si falla, Nox usa la CPU solo.", pady=(0, 6))
        self.m_dispositivo = ui.menu(f, ["Automático (el del perfil)", "cpu", "cuda"],
                                     a.get("whisper_device") or "Automático (el del perfil)", ancho=240)
        ui.parrafo(f, "Modelo de reconocimiento de voz al dictar:", pady=(12, 4))
        self.m_whisper = ui.menu(f, ["Automático (el del perfil)"] + list(ajustes.WHISPER_MODELOS),
                                 a.get("modelo_whisper") or "Automático (el del perfil)", ancho=240)
        ui.parrafo(f, "", pady=(0, 24))
        self._perfil_cambiado()

        auto = "Automático (el del perfil)"
        self._lectores.update({
            "equipo": lambda: self._clave_de_perfil(self.m_perfil.get()),
            "modelo_chat": lambda: "" if self.m_modelo.get() == AUTOMATICO else self.m_modelo.get(),
            "whisper_device": lambda: "" if self.m_dispositivo.get() == auto else self.m_dispositivo.get(),
            "modelo_whisper": lambda: "" if self.m_whisper.get() == auto else self.m_whisper.get(),
        })

    @staticmethod
    def _clave_de_perfil(nombre: str) -> str:
        return next((k for k, n in NOMBRES_PERFIL.items() if n == nombre), config.EQUIPO_POR_DEFECTO)

    def _perfil_cambiado(self):
        p = config.PERFILES_EQUIPO[self._clave_de_perfil(self.m_perfil.get())]
        medido = "Medido en el equipo de desarrollo." if self._clave_de_perfil(self.m_perfil.get()) == "estandar_8gb" \
            else "Sin medir en un equipo así: correr evaluar_modelo.py allí confirma la elección."
        self.t_perfil.configure(
            text=f"{p['descripcion']}. Modelo: {p['modelo_chat']} · contexto {p['num_ctx']} · voz en {p['whisper_device']}. {medido}")

    def _detectar(self):
        self.t_deteccion.configure(text="Mirando tu equipo…", text_color=tema.TEXTO_TENUE)
        ui.en_hilo(self, ajustes.detectar_equipo, self._mostrar_deteccion)

    def _mostrar_deteccion(self, ok, datos):
        if not ok:
            self.t_deteccion.configure(text="No pude detectarlo. Elige a mano.", text_color=tema.ROJO)
            return
        ram = f"{datos['ram_gb']} GB de RAM" if datos["ram_gb"] else "RAM desconocida"
        gpu = datos["gpu"] or "sin tarjeta dedicada detectada"
        vram = f" ({datos['vram_gb']} GB)" if datos["vram_gb"] else ""
        self.t_deteccion.configure(text=f"{gpu}{vram}, {ram}. {datos['motivo']}", text_color=tema.TEXTO_SUAVE)
        self._sugerido = datos["sugerido"]
        self.b_usar_sugerencia.configure(
            text=f"Usar: {NOMBRES_PERFIL[self._sugerido]}", width=330, command=self._usar_sugerencia)
        self.b_usar_sugerencia.pack(anchor="w", pady=(8, 0))

    def _usar_sugerencia(self):
        if self._sugerido:
            self.m_perfil.set(NOMBRES_PERFIL[self._sugerido])
            self._perfil_cambiado()

    def _llenar_modelos(self, ok, lista):
        if ok and lista:
            actual = self.m_modelo.get()
            self.m_modelo.configure(values=[AUTOMATICO] + lista)
            self.m_modelo.set(actual)

    def _pintar_modelos(self):
        """Lista de modelos necesarios con su estado, y el boton para bajar los que faltan."""
        for w in self.f_modelos.winfo_children():
            w.destroy()
        ui.en_hilo(self, lambda: (modelos.necesarios(), modelos.instalados(), modelos.ollama_activo()),
                   self._dibujar_modelos)

    def _dibujar_modelos(self, ok, datos):
        if not ok or self._cerrada:
            return
        necesarios, instalados, activo = datos
        for w in self.f_modelos.winfo_children():
            w.destroy()
        if not activo:
            ctk.CTkLabel(self.f_modelos, text="Ollama no responde. Ábrelo (o corre «ollama serve») y vuelve a mirar.",
                         font=tema.ETIQUETA, text_color=tema.ROJO, anchor="w").pack(anchor="w")
            ui.boton(self.f_modelos, "Volver a mirar", self._pintar_modelos, ancho=130).pack(anchor="w", pady=(8, 0))
            return
        faltan = []
        for m in necesarios:
            esta = modelos.esta_instalado(m, instalados)
            if not esta:
                faltan.append(m)
            ctk.CTkLabel(self.f_modelos, text=f"{'✓' if esta else '✗'}  {m}", font=tema.CUERPO,
                         text_color=tema.VERDE if esta else tema.AMBAR, anchor="w").pack(anchor="w")
        if faltan:
            self._barra = ui.barra(self.f_modelos)
            self._t_descarga = ctk.CTkLabel(self.f_modelos, text="", font=tema.ETIQUETA,
                                            text_color=tema.TEXTO_TENUE, anchor="w")
            self._b_descargar = ui.boton(self.f_modelos, f"Descargar lo que falta ({len(faltan)})",
                                         lambda: self._descargar(faltan), primario=True, ancho=240)
            self._b_descargar.pack(anchor="w", pady=(10, 0))

    def _descargar(self, faltan: list[str]):
        self._b_descargar.configure(state="disabled")
        self._barra.pack(anchor="w", pady=(10, 4))
        self._t_descarga.pack(anchor="w")
        progreso = ui.Progreso()

        def trabajo():
            for m in faltan:
                progreso.texto = f"Descargando {m}…"
                ok, msg = modelos.descargar(m, lambda f, t, m=m: setattr(progreso, "fraccion", f) or
                                            setattr(progreso, "texto", f"{m}: {t}"))
                if not ok:
                    return msg
            return ""

        def pintar():
            if self._cerrada:
                return
            self._barra.set(progreso.fraccion)
            self._t_descarga.configure(text=progreso.texto)
            if self._descargando:
                self.after(250, pintar)

        def terminado(ok, error):
            self._descargando = False
            if ok and not error:
                self._pintar_modelos()
            else:
                self._t_descarga.configure(text=str(error), text_color=tema.ROJO)
                self._b_descargar.configure(state="normal")

        self._descargando = True
        pintar()
        ui.en_hilo(self, trabajo, terminado)

    # ------------------------------------------------------------------ Voz

    def _pagina_voz(self, f):
        a = self.actual
        ui.titulo(f, "Voz")
        ui.parrafo(f, "Cómo te oye y cómo te habla Nox.")

        ui.campo(f, "Cuando te respondo")
        _, self.v_voz = ui.interruptor(f, "Nox responde en voz alta", config.VOZ_ACTIVA)

        ui.campo(f, "Cuando te escucho",
                 "El detector de voz distingue tu voz de un ventilador o el teclado, y oye mejor cuando hablas bajo.")
        _, self.v_vad = ui.interruptor(f, "Detectar mi voz con IA (recomendado)", config.USAR_VAD)

        ui.campo(f, "Velocidad de la voz")
        fila = ctk.CTkFrame(f, fg_color="transparent")
        fila.pack(anchor="w")
        ctk.CTkLabel(fila, text="Rápida", font=tema.ETIQUETA, text_color=tema.TEXTO_TENUE).pack(side="left")
        self.sl_velocidad = ctk.CTkSlider(fila, from_=0.7, to=1.4, number_of_steps=14, width=280,
                                          progress_color=tema.AZUL, button_color=tema.AZUL,
                                          button_hover_color=tema.AZUL_HOVER, fg_color=tema.ELEVADO)
        self.sl_velocidad.set(config.VELOCIDAD_VOZ)
        self.sl_velocidad.pack(side="left", padx=10)
        ctk.CTkLabel(fila, text="Lenta", font=tema.ETIQUETA, text_color=tema.TEXTO_TENUE).pack(side="left")
        ui.boton(f, "Probar la voz", self._probar_voz, ancho=130).pack(anchor="w", pady=(12, 0))

        ui.campo(f, "Cuando juegas",
                 "En una tarjeta de 8 GB no caben a la vez un juego moderno y el modelo local.")
        _, self.v_gpu = ui.interruptor(f, "Ceder la tarjeta de video al juego (mandar lo que se pueda a la nube)",
                                       config.CEDER_GPU_AL_JUGAR)
        ui.parrafo(f, "", pady=(0, 24))

        self._lectores.update({
            "voz_activa": lambda: self.v_voz.get(),
            "usar_vad": lambda: self.v_vad.get(),
            "velocidad_voz": lambda: round(float(self.sl_velocidad.get()), 2),
            "ceder_gpu_al_jugar": lambda: self.v_gpu.get(),
        })

    def _probar_voz(self):
        import voz
        config.VELOCIDAD_VOZ = round(float(self.sl_velocidad.get()), 2)   # se restaura al cerrar sin guardar
        voz.hablar_async(f"Hola {config.USUARIO}, así suena mi voz con esta velocidad.")

    # -------------------------------------------------------------- Memoria

    def _pagina_memoria(self, f):
        ui.titulo(f, "Memoria")
        ui.parrafo(f, "Lo que Nox recuerda de ti entre conversaciones. Se guarda solo en tu equipo y nunca se envía a la "
                      "nube. Nox PROPONE qué limpiar, pero nunca borra nada sin que lo confirmes.", ancho=600)
        _, self.v_resumen = ui.interruptor(f, "Resumir mis conversaciones al cerrarlas y guardar lo que valga la pena",
                                           config.MEMORIA_RESUMEN_SESION)
        ui.parrafo(f, "Apagado por defecto. Con el modelo local, Nox extrae como máximo 3 hechos o decisiones que "
                      "contaste (no lo que él respondió). Tardan unos segundos al cerrar.", pady=(4, 6))
        self._lectores["memoria_resumen_sesion"] = lambda: self.v_resumen.get()

        self.t_memoria_stats = ui.parrafo(f, "", color=tema.TEXTO_SUAVE, pady=(14, 6))
        self.vista_memoria = ui.segmentado(f, ["Todos", "Duplicados", "Sin uso"], "Todos",
                                           comando=lambda _: self._pintar_memoria())
        self.f_memoria = ctk.CTkFrame(f, fg_color="transparent")
        self.f_memoria.pack(fill="x", anchor="w", pady=(10, 24))
        self._pintar_memoria()

    def _pintar_memoria(self):
        for w in self.f_memoria.winfo_children():
            w.destroy()
        vista = self.vista_memoria.get()
        if vista == "Duplicados":
            ui.parrafo(self.f_memoria, "Calculando…", color=tema.TEXTO_TENUE)
            ui.en_hilo(self, memoria.candidatos_duplicados, self._mostrar_duplicados)
        elif vista == "Sin uso":
            self._mostrar_sin_uso(memoria.candidatos_olvido())
        else:
            self._mostrar_todos()
        try:
            e = memoria.estadisticas()
            self.t_memoria_stats.configure(
                text=f"{e['total']} recuerdos · {e['sin_uso']} nunca usados · {e['duplicados']} posibles duplicados · "
                     f"{e['para_olvidar']} para considerar olvidar")
        except Exception:
            self.t_memoria_stats.configure(text="No pude leer la memoria (¿Ollama está abierto?).")

    def _fila_recuerdo(self, r, botones):
        fila = ctk.CTkFrame(self.f_memoria, fg_color=tema.SUPERFICIE, corner_radius=tema.RADIO_CHICO,
                            border_width=1, border_color=tema.BORDE)
        fila.pack(fill="x", pady=3)
        ctk.CTkLabel(fila, text=r["contenido"], font=tema.CUERPO, text_color=tema.TEXTO, anchor="w",
                     justify="left", wraplength=460).pack(side="left", fill="x", expand=True, padx=14, pady=(10, 2))
        meta = f"#{r['id']} · {r['categoria']} · {r['fecha'][:10]} · usado {r.get('usos', 0)} veces"
        ctk.CTkLabel(fila, text=meta, font=tema.MICRO, text_color=tema.TEXTO_TENUE, anchor="w").pack(
            side="bottom", anchor="w", padx=14, pady=(0, 8))
        for texto, comando in botones:
            ui.boton(fila, texto, comando, ancho=90).pack(side="right", padx=(0, 10), pady=8)

    def _mostrar_todos(self):
        todos = list(reversed(memoria.listar()))
        if not todos:
            ui.parrafo(self.f_memoria, "Todavía no hay recuerdos. Se guardan cuando le cuentas algo a Nox.")
        for r in todos[:60]:
            self._fila_recuerdo(r, [("Olvidar", lambda i=r["id"]: self._olvidar(i))])
        if len(todos) > 60:
            ui.parrafo(self.f_memoria, f"(y {len(todos) - 60} más antiguos)")

    def _mostrar_duplicados(self, ok, pares):
        if self._cerrada or self.vista_memoria.get() != "Duplicados":
            return
        for w in self.f_memoria.winfo_children():
            w.destroy()
        if not ok:
            ui.parrafo(self.f_memoria, "No pude compararlos (¿Ollama está abierto?).", color=tema.ROJO)
            return
        if not pares:
            ui.parrafo(self.f_memoria, "No encontré recuerdos repetidos.", color=tema.VERDE)
            return
        ui.parrafo(self.f_memoria, "Cada par dice casi lo mismo. «Conservar este» olvida el otro y le suma sus usos.")
        for par in pares:
            ui.parrafo(self.f_memoria, f"Parecido: {int(par['similitud'] * 100)} %", color=tema.AMBAR, pady=(10, 0))
            for este, otro in ((par["a"], par["b"]), (par["b"], par["a"])):
                self._fila_recuerdo(este, [("Conservar este", lambda c=este["id"], b=otro["id"]: self._fusionar(c, b))])

    def _mostrar_sin_uso(self, candidatos):
        if not candidatos:
            ui.parrafo(self.f_memoria, f"Nada que proponer: no hay datos de más de {memoria.DIAS_SIN_USO} días que nunca "
                                       "se hayan usado. (Las preferencias y correcciones no caducan solas.)", color=tema.VERDE)
            return
        ui.parrafo(self.f_memoria, f"Datos de más de {memoria.DIAS_SIN_USO} días que Nox nunca ha necesitado. "
                                   "Revisa cada uno antes de olvidarlo.")
        for r in candidatos:
            self._fila_recuerdo(r, [("Olvidar", lambda i=r["id"]: self._olvidar(i))])

    def _olvidar(self, id_recuerdo: int):
        self._mensaje(memoria.olvidar(id_recuerdo))
        self._pintar_memoria()

    def _fusionar(self, conservar: int, borrar: int):
        self._mensaje(memoria.fusionar(conservar, borrar))
        self._pintar_memoria()

    # ----------------------------------------------------------- Iniciativa

    def _pagina_iniciativa(self, f):
        ui.titulo(f, "Iniciativa")
        ui.parrafo(f, "Que Nox te avise sin que lo llames. Nunca programa nada por su cuenta: solo avisa de lo que le "
                      "pides («recuérdame llamar a mamá a las 6») y de lo que actives aquí. Mientras juegas, los avisos "
                      "esperan a que termines.", ancho=600)
        _, self.v_avisos = ui.interruptor(f, "Avisarme de mis recordatorios", config.AVISAR_RECORDATORIOS)
        _, self.v_avisos_voz = ui.interruptor(f, "Decirlos en voz alta", config.AVISOS_EN_VOZ)
        ui.campo(f, "Saludo de la mañana",
                 "La primera vez que abras Nox cada día (entre las 5 y las 12), te dice la fecha y lo que tienes "
                 "pendiente. Viene apagado: Nox no te habla solo hasta que lo activas.", ancho=600)
        _, self.v_saludo = ui.interruptor(f, "Darme los buenos días con un resumen", config.SALUDO_MATUTINO)
        self._lectores.update({"avisar_recordatorios": lambda: self.v_avisos.get(),
                               "avisos_en_voz": lambda: self.v_avisos_voz.get(),
                               "saludo_matutino": lambda: self.v_saludo.get()})

        ui.separador(f)
        ui.campo(f, "Recordatorios pendientes")
        self.f_recordatorios = ctk.CTkFrame(f, fg_color="transparent")
        self.f_recordatorios.pack(fill="x", anchor="w")
        ui.campo(f, "Programar uno ahora", "También se lo puedes pedir a Nox hablando: «avísame en 20 minutos de sacar la pizza».", ancho=600)
        fila = ctk.CTkFrame(f, fg_color="transparent")
        fila.pack(anchor="w")
        self.e_rec_texto = ui.entrada(fila, "", placeholder="Qué recordarte", ancho=300)
        self.e_rec_texto.pack_forget(); self.e_rec_texto.pack(side="left")
        self.e_rec_min = ui.entrada(fila, "", placeholder="en minutos", ancho=110)
        self.e_rec_min.pack_forget(); self.e_rec_min.pack(side="left", padx=10)
        ui.boton(fila, "Programar", self._programar, primario=True, ancho=110).pack(side="left")
        ui.parrafo(f, "", pady=(0, 24))
        self._pintar_recordatorios()

    def _pintar_recordatorios(self):
        for w in self.f_recordatorios.winfo_children():
            w.destroy()
        pendientes = recordatorios.listar()
        if not pendientes:
            ui.parrafo(self.f_recordatorios, "No hay ninguno pendiente.")
        for r in pendientes:
            fila = ctk.CTkFrame(self.f_recordatorios, fg_color=tema.SUPERFICIE, corner_radius=tema.RADIO_CHICO,
                                border_width=1, border_color=tema.BORDE)
            fila.pack(fill="x", pady=3)
            ctk.CTkLabel(fila, text=recordatorios.describir(r), font=tema.CUERPO, text_color=tema.TEXTO, anchor="w",
                         justify="left", wraplength=470).pack(side="left", fill="x", expand=True, padx=14, pady=10)
            ui.boton(fila, "Cancelar", lambda i=r["id"]: self._cancelar_recordatorio(i), ancho=90).pack(side="right", padx=10)

    def _programar(self):
        try:
            minutos = int(self.e_rec_min.get().strip())
        except ValueError:
            self._mensaje("Los minutos deben ser un número.", tema.ROJO)
            return
        try:
            r = recordatorios.crear(self.e_rec_texto.get(), en_minutos=minutos)
        except recordatorios.RecordatorioInvalido as e:
            self._mensaje(str(e), tema.ROJO)
            return
        self.e_rec_texto.delete(0, "end"); self.e_rec_min.delete(0, "end")
        self._mensaje(f"Programado: {recordatorios.describir(r)}", tema.VERDE)
        self._pintar_recordatorios()

    def _cancelar_recordatorio(self, id_recordatorio: int):
        recordatorios.cancelar(id_recordatorio)
        self._pintar_recordatorios()

    # ---------------------------------------------------------------- Vista

    def _pagina_vista(self, f):
        a = self.actual
        ui.titulo(f, "Vista")
        ui.parrafo(f, "Que Nox pueda MIRAR tu pantalla cuando se lo pidas («mira esto y dime qué error es»). Una pantalla "
                      "puede tener contraseñas, mensajes privados o el banco, así que viene apagada y se rige por estas reglas:",
                   ancho=600)
        for linea in ("La imagen se queda en tu equipo: la ve solo un modelo de visión local. Nunca va a la nube.",
                      "La captura se borra al usarla; no se guarda nada de lo que se ve.",
                      "Solo mira cuando se lo pides. No vigila tu pantalla.",
                      "Lo que ve es información: si la pantalla dice «ignora tus reglas», no lo obedece."):
            ui.parrafo(f, "•  " + linea, color=tema.TEXTO_SUAVE, ancho=600, pady=(0, 2))
        _, self.v_vista = ui.interruptor(f, "Permitir que Nox mire mi pantalla", config.VISTA_ACTIVA)
        _, self.v_vista_pregunta = ui.interruptor(f, "Pedirme permiso cada vez (recomendado)", config.VISTA_PREGUNTAR)

        ui.campo(f, "Modelo de visión",
                 "Necesita memoria de video: en una tarjeta de 8 GB Nox descarga el modelo de conversación mientras mira "
                 "y lo vuelve a cargar después (unos segundos de espera).", ancho=600)
        self.m_vision = ui.menu(f, [config.MODELO_VISION], a.get("modelo_vision") or config.MODELO_VISION, ancho=320)
        ui.en_hilo(self, modelos.instalados, self._llenar_visiones)
        self.t_vision = ui.parrafo(f, "", color=tema.TEXTO_SUAVE, pady=(8, 4))
        self.f_vision = ctk.CTkFrame(f, fg_color="transparent")
        self.f_vision.pack(anchor="w")
        ui.boton(self.f_vision, "Comprobar que funciona", self._comprobar_vision, ancho=190, lado="left")
        self.b_bajar_vision = ui.boton(self.f_vision, "Descargar", self._bajar_vision, primario=True, ancho=110)
        self.t_resultado_vision = ui.parrafo(f, "", color=tema.TEXTO_SUAVE, pady=(8, 0))   # el resultado de «Comprobar»
        self._barra_vision = ui.barra(f, 420)
        self.t_descarga_vision = ctk.CTkLabel(f, text="", font=tema.ETIQUETA, text_color=tema.TEXTO_TENUE, anchor="w")
        ui.parrafo(f, "La comprobación usa una imagen de prueba con un error inventado: no toma ninguna captura de tu pantalla.",
                   pady=(8, 24))
        self._lectores.update({"vista_activa": lambda: self.v_vista.get(),
                               "vista_preguntar": lambda: self.v_vista_pregunta.get(),
                               "modelo_vision": lambda: self.m_vision.get()})
        self._estado_vision()

    def _llenar_visiones(self, ok, lista):
        if not ok:
            return
        candidatos = [m for m in lista if any(x in m for x in ("vl", "qwen3.5", "llava", "gemma3", "minicpm", "vision"))]
        actual = self.m_vision.get()
        valores = sorted(set(candidatos) | {actual})
        self.m_vision.configure(values=valores)
        self.m_vision.set(actual)
        self._estado_vision()

    def _estado_vision(self):
        modelo = self.m_vision.get()
        ui.en_hilo(self, lambda: modelos.esta_instalado(modelo), lambda ok, esta: self._pintar_estado_vision(modelo, ok and esta))

    def _pintar_estado_vision(self, modelo, esta):
        if self._cerrada:
            return
        if esta:
            self.t_vision.configure(text=f"✓ {modelo} está descargado.", text_color=tema.VERDE)
            self.b_bajar_vision.pack_forget()
        else:
            self.t_vision.configure(text=f"✗ {modelo} no está descargado.", text_color=tema.AMBAR)
            self.b_bajar_vision.pack(side="left", padx=10)

    def _comprobar_vision(self):
        self.t_resultado_vision.configure(text="Probando con una imagen de prueba…", text_color=tema.TEXTO_TENUE)
        modelo = self.m_vision.get()
        ui.en_hilo(self, lambda: vista.comprobar_modelo(modelo), self._resultado_vision)

    def _resultado_vision(self, ok, datos):
        if self._cerrada:
            return
        if not ok:
            self.t_resultado_vision.configure(text=f"No pude probarlo: {datos}", text_color=tema.ROJO)
            return
        leyo, dijo = datos
        self.t_resultado_vision.configure(
            text=("✓ Funciona: leyó el código de la imagen. " if leyo else "✗ No leyó bien la imagen de prueba. ") + dijo[:220],
            text_color=tema.VERDE if leyo else tema.AMBAR)

    def _bajar_vision(self):
        modelo = self.m_vision.get()
        progreso = ui.Progreso()
        self._barra_vision.pack(anchor="w", pady=(8, 2))
        self.t_descarga_vision.pack(anchor="w")
        self.b_bajar_vision.configure(state="disabled")
        self._bajando_vision = True

        def pintar():
            if self._cerrada or not self._bajando_vision:
                return
            self._barra_vision.set(progreso.fraccion)
            self.t_descarga_vision.configure(text=progreso.texto)
            self.after(250, pintar)

        def terminado(ok, resultado):
            self._bajando_vision = False
            self.b_bajar_vision.configure(state="normal")
            if ok and resultado[0]:
                self._barra_vision.pack_forget()
                self.t_descarga_vision.pack_forget()
                self._estado_vision()
            elif not self._cerrada:
                self.t_descarga_vision.configure(text=str(resultado[1] if ok else resultado), text_color=tema.ROJO)

        pintar()
        ui.en_hilo(self, lambda: modelos.descargar(modelo, lambda f, t: (setattr(progreso, "fraccion", f),
                                                                       setattr(progreso, "texto", f"{modelo}: {t}"))), terminado)

    # --------------------------------------------------------------- Bóveda

    def _pagina_boveda(self, f):
        ui.titulo(f, "Bóveda")
        ui.parrafo(f, "Una bóveda de Obsidian es una carpeta con tus notas. Si la conectas, Nox las consulta antes de "
                      "responder y puede ampliarlas. Es opcional: sin ella Nox funciona igual.")
        ui.campo(f, "Carpeta de tu bóveda")
        fila = ctk.CTkFrame(f, fg_color="transparent")
        fila.pack(anchor="w")
        self.e_boveda = ui.entrada(fila, self.actual.get("boveda", ""), placeholder="Sin bóveda", ancho=360)
        self.e_boveda.pack_forget()
        self.e_boveda.pack(side="left")
        ui.boton(fila, "Elegir carpeta…", self._elegir_boveda, ancho=130).pack(side="left", padx=10)
        ui.boton(fila, "Quitar", lambda: (self.e_boveda.delete(0, "end"), self._estado_boveda()), ancho=80).pack(side="left")
        self.t_boveda = ui.parrafo(f, "", color=tema.TEXTO_SUAVE, pady=(10, 0))
        self.e_boveda.bind("<KeyRelease>", lambda e: self._estado_boveda())
        self._estado_boveda()
        self._lectores["boveda"] = lambda: self.e_boveda.get()

    def _elegir_boveda(self):
        carpeta = filedialog.askdirectory(parent=self, title="Elige la carpeta de tu bóveda")
        if carpeta:
            self.e_boveda.delete(0, "end")
            self.e_boveda.insert(0, carpeta)
            self._estado_boveda()

    def _estado_boveda(self):
        from pathlib import Path
        ruta = self.e_boveda.get().strip()
        if not ruta:
            self.t_boveda.configure(text="Sin bóveda conectada.", text_color=tema.TEXTO_TENUE)
            return
        carpeta = Path(ruta).expanduser()
        if not carpeta.is_dir():
            self.t_boveda.configure(text="Esa carpeta no existe.", text_color=tema.AMBAR)
        elif not (carpeta / "RAG" / "index.db").exists():
            self.t_boveda.configure(
                text="La carpeta existe, pero no tiene el índice de búsqueda (RAG/index.db). Nox podrá abrir "
                     "notas, no buscar por significado hasta que se genere.", text_color=tema.AMBAR)
        else:
            self.t_boveda.configure(text="✓ Bóveda lista, con índice de búsqueda.", text_color=tema.VERDE)

    # ----------------------------------------------------------------- Nube

    def _pagina_nube(self, f):
        ui.titulo(f, "Nube")
        ui.parrafo(f, "Para preguntas generales y profundas, Nox puede usar un modelo grande en internet (OpenRouter, "
                      "con modelos gratuitos). Por ese canal NUNCA salen tus notas, tu memoria, tus archivos ni tu "
                      "perfil: solo la pregunta y las instrucciones de trato.")
        _, self.v_nube = ui.interruptor(f, "Usar la nube cuando convenga", config.USAR_NUBE)

        ui.campo(f, "Clave de OpenRouter",
                 "Se crea gratis en openrouter.ai. Se guarda en un archivo aparte, que solo tú puedes leer. "
                 "Sin clave, Nox responde todo en tu equipo.")
        self.t_key = ui.parrafo(f, "", color=tema.TEXTO_SUAVE, pady=(0, 6))
        self.e_key = ui.entrada(f, "", placeholder="Pega aquí tu clave (sk-or-…)", ancho=420, oculto=True)
        fila = ctk.CTkFrame(f, fg_color="transparent")
        fila.pack(anchor="w", pady=(10, 0))
        ui.boton(fila, "Guardar clave", self._guardar_key, primario=True, ancho=130, lado="left")
        ui.boton(fila, "Quitar clave", self._quitar_key, ancho=120).pack(side="left", padx=10)
        self._estado_key()
        ui.parrafo(f, "", pady=(0, 24))
        self._lectores["usar_nube"] = lambda: self.v_nube.get()

    def _estado_key(self):
        if ajustes.hay_key():
            self.t_key.configure(text="✓ Hay una clave guardada.", text_color=tema.VERDE)
        else:
            self.t_key.configure(text="Sin clave: todo se resuelve en tu equipo.", text_color=tema.TEXTO_TENUE)

    def _guardar_key(self):
        try:
            ajustes.guardar_key(self.e_key.get())
        except (AjusteInvalido, OSError) as e:
            self._mensaje(str(e), tema.ROJO)
            return
        self.e_key.delete(0, "end")
        self._estado_key()
        self._mensaje("Clave guardada.", tema.VERDE)

    def _quitar_key(self):
        ajustes.borrar_key()
        self._estado_key()
        self._mensaje("Clave eliminada.", tema.TEXTO_TENUE)

    # ------------------------------------------------- Herramientas externas

    def _pagina_externas(self, f):
        ui.titulo(f, "Herramientas externas")
        ui.parrafo(f, "Nox puede conectarse a servidores MCP: programas de terceros que le dan herramientas nuevas (por "
                      "ejemplo, un navegador que abre páginas y rellena formularios).", ancho=580)
        ui.parrafo(f, "⚠  Un servidor MCP es código de otra persona que se ejecuta con tus permisos. Activa solo los que "
                      "conozcas. Cada herramienta nace BLOQUEADA y eliges tú, una por una, si Nox puede usarla: "
                      "«Preguntar siempre» te pide permiso cada vez; «Permitir» la deja correr sola. Las que ejecutan "
                      "código o tocan archivos siempre piden permiso.", color=tema.AMBAR, ancho=580)
        ui.parrafo(f, f"Se recomienda tener pocas activas (máximo {mcp_cliente.MAX_HERRAMIENTAS_ACTIVAS}): cada una "
                      "ocupa memoria del modelo y lo confunde más.", ancho=580)
        self.f_externas = ctk.CTkFrame(f, fg_color="transparent")
        self.f_externas.pack(fill="x", anchor="w")

        ui.separador(f)
        ui.campo(f, "Añadir un servidor")
        fila = ctk.CTkFrame(f, fg_color="transparent")
        fila.pack(anchor="w")
        for clave, plantilla in mcp_cliente.PLANTILLAS.items():
            ui.boton(fila, f"+ {plantilla['nombre']}", lambda c=clave: self._agregar_plantilla(c), ancho=270,
                     lado="left")
        ui.boton(fila, "+ Servidor propio…", self._servidor_propio, ancho=160).pack(side="left", padx=10)
        ui.parrafo(f, "", pady=(0, 24))
        self._firma_externas = None
        self._pintar_externas()

    def _sondear(self, activo: bool):
        """Mientras esta pagina esta a la vista, refresca el estado de los servidores cada segundo."""
        if self._sondeo is not None:
            try:
                self.after_cancel(self._sondeo)
            except Exception:
                pass
            self._sondeo = None
        if activo and not self._cerrada:
            self._sondeo = self.after(1000, self._tick_externas)

    def _tick_externas(self):
        if self._cerrada:
            return
        self._pintar_externas()
        self._sondeo = self.after(1000, self._tick_externas)

    def _pintar_externas(self):
        adm = mcp_cliente.administrador()
        filas = adm.estado_servidores()
        firma = repr([(s["id"], s["activo"], s["estado"], s["error"],
                       [(h["nombre"], h["politica"]) for h in s["herramientas"]]) for s in filas])
        if firma == self._firma_externas:
            return   # nada cambio: no se redibuja, para no perder el foco ni parpadear
        self._firma_externas = firma
        for w in self.f_externas.winfo_children():
            w.destroy()
        if not filas:
            ui.parrafo(self.f_externas, "Todavía no hay ningún servidor. Añade uno abajo.")
            return
        for s in filas:
            self._tarjeta_servidor(adm, s)

    def _tarjeta_servidor(self, adm, s):
        tarjeta = ctk.CTkFrame(self.f_externas, fg_color=tema.SUPERFICIE, corner_radius=tema.RADIO,
                               border_width=1, border_color=tema.BORDE)
        tarjeta.pack(fill="x", pady=(8, 4))
        cab = ctk.CTkFrame(tarjeta, fg_color="transparent")
        cab.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(cab, text="●", font=(tema.FUENTE, 13), text_color=ui.color_estado(s["estado"])).pack(side="left")
        ctk.CTkLabel(cab, text=f"  {s['nombre']}", font=tema.CUERPO_BOLD, text_color=tema.TEXTO).pack(side="left")
        ctk.CTkLabel(cab, text=f"  {ui.TEXTO_ESTADO.get(s['estado'], s['estado'])}", font=tema.ETIQUETA,
                     text_color=ui.color_estado(s["estado"])).pack(side="left")
        ui.boton(cab, "Quitar", lambda sid=s["id"]: self._quitar_servidor(sid), ancho=70).pack(side="right")
        variable = ctk.BooleanVar(value=s["activo"])
        ctk.CTkSwitch(cab, text="Activo", variable=variable, font=tema.ETIQUETA, text_color=tema.TEXTO_SUAVE,
                      progress_color=tema.AZUL, button_color=tema.TEXTO_SUAVE, fg_color=tema.BORDE, width=44,
                      command=lambda sid=s["id"], v=variable: self._activar_servidor(sid, v.get())
                      ).pack(side="right", padx=14)
        ctk.CTkLabel(tarjeta, text=f"{s['comando']} {' '.join(s['args'])}", font=tema.CODIGO,
                     text_color=tema.TEXTO_TENUE, anchor="w", wraplength=520, justify="left").pack(fill="x", padx=16)
        if s["error"]:
            ctk.CTkLabel(tarjeta, text=s["error"], font=tema.ETIQUETA, text_color=tema.ROJO, anchor="w",
                         wraplength=520, justify="left").pack(fill="x", padx=16, pady=(4, 0))

        plantilla = next((p for p in mcp_cliente.PLANTILLAS.values()
                          if p["comando"] == s["comando"] and p["args"] == s["args"]), None)
        if s["herramientas"]:
            activas = sum(1 for h in s["herramientas"] if h["politica"] != "bloquear")
            fila = ctk.CTkFrame(tarjeta, fg_color="transparent")
            fila.pack(fill="x", padx=16, pady=(10, 2))
            ctk.CTkLabel(fila, text=f"{len(s['herramientas'])} herramientas · {activas} activas", font=tema.ETIQUETA,
                         text_color=tema.TEXTO_SUAVE).pack(side="left")
            if plantilla and plantilla.get("recomendadas") and s["estado"] == "conectado":
                ui.boton(fila, "Aplicar la selección recomendada",
                         lambda sid=s["id"], p=plantilla: self._aplicar_recomendadas(sid, p), ancho=250).pack(side="right")
            for h in s["herramientas"]:
                self._fila_herramienta(adm, tarjeta, s["id"], h)
        ctk.CTkFrame(tarjeta, height=10, fg_color="transparent").pack()

    def _fila_herramienta(self, adm, tarjeta, sid, h):
        fila = ctk.CTkFrame(tarjeta, fg_color="transparent")
        fila.pack(fill="x", padx=16, pady=1)
        alto = h.get("riesgo") == "alto"
        ctk.CTkLabel(fila, text=("⚠ " if alto else "   ") + h["nombre"], font=tema.CODIGO,
                     text_color=tema.AMBAR if alto else tema.TEXTO_SUAVE, anchor="w", width=330).pack(side="left")
        valores = [POLITICAS_VISIBLES[p] for p in (("bloquear", "preguntar") if alto else mcp_cliente.POLITICAS)]
        actual = POLITICAS_VISIBLES.get(h["politica"], "Bloqueada")

        def cambiar(texto, nombre=h["nombre"], menu_=None):
            try:
                adm.fijar_politica(sid, nombre, POLITICA_DE_TEXTO[texto])
                self._mensaje("")
            except ConfigInvalida as e:
                self._mensaje(str(e), tema.ROJO)
                self._firma_externas = None   # fuerza el redibujo para volver al valor real
                self._pintar_externas()

        m = ctk.CTkOptionMenu(fila, values=valores, width=170, height=28, font=tema.ETIQUETA,
                              dropdown_font=tema.ETIQUETA, fg_color=tema.ELEVADO, button_color=tema.BORDE,
                              button_hover_color=tema.AZUL_APAGADO, text_color=tema.TEXTO,
                              dropdown_fg_color=tema.SUPERFICIE, dropdown_hover_color=tema.ELEVADO,
                              corner_radius=tema.RADIO_CHICO, command=cambiar)
        m.set(actual)
        m.pack(side="left")

    def _activar_servidor(self, sid: str, activo: bool):
        try:
            mcp_cliente.administrador().fijar_activo(sid, activo)
        except Exception as e:
            self._mensaje(str(e), tema.ROJO)
        self._firma_externas = None

    def _aplicar_recomendadas(self, sid: str, plantilla: dict):
        try:
            n = mcp_cliente.administrador().aplicar_recomendadas(sid, plantilla["recomendadas"])
            self._mensaje(f"Se ajustaron {n} herramientas. Revisa la lista antes de usarlas.", tema.VERDE)
        except ConfigInvalida as e:
            self._mensaje(str(e), tema.ROJO)
        self._firma_externas = None
        self._pintar_externas()

    def _quitar_servidor(self, sid: str):
        mcp_cliente.administrador().quitar(sid)
        self._firma_externas = None
        self._pintar_externas()

    def _agregar_plantilla(self, clave: str):
        p = mcp_cliente.PLANTILLAS[clave]
        if p.get("requiere") == "node" and not shutil.which("node"):
            self._mensaje("Este servidor necesita Node.js (nodejs.org). Instálalo y vuelve a intentar.", tema.AMBAR)
            return
        adm = mcp_cliente.administrador()
        sid = clave if clave not in adm.servidores else mcp_cliente.identificador(p["nombre"] + str(len(adm.servidores)))
        try:
            adm.agregar(sid, {k: p[k] for k in ("nombre", "comando", "args")})
            self._mensaje("Servidor añadido y apagado. Actívalo cuando quieras; la primera vez puede tardar mientras se descarga.",
                          tema.VERDE)
        except ConfigInvalida as e:
            self._mensaje(str(e), tema.ROJO)
        self._firma_externas = None
        self._pintar_externas()

    def _servidor_propio(self):
        DialogoServidor(self, self._servidor_creado)

    def _servidor_creado(self):
        self._firma_externas = None
        self._pintar_externas()

    # ------------------------------------------------------------ Seguridad

    def _pagina_seguridad(self, f):
        ui.titulo(f, "Seguridad")
        ui.parrafo(f, "Esto no se configura: es cómo está construido Nox, y se comprueba con pruebas automáticas.")
        for titulo_, texto in (
            ("Nunca puede", "Borrar archivos (no existe esa herramienta), instalar o desinstalar programas, usar sudo, "
                            "tocar el registro, ni escribir archivos ejecutables (.sh, .bat, .ps1, .exe)."),
            ("Solo escribe en", f"{config.CARPETA_TRABAJO}, {config.DOCUMENTOS} y {config.ESCRITORIO}, y únicamente archivos "
                                "de texto. Tampoco puede tocar su propia carpeta de programa."),
            ("Antes de pisar un archivo", "Guarda una copia y lo anota en una bitácora."),
            ("Pide permiso", "Para cerrar programas y para cualquier herramienta externa que dejes en «Preguntar siempre»."),
            ("La nube", "Solo recibe preguntas generales. Tus notas, memoria, archivos y perfil se quedan en tu equipo."),
            ("Páginas web y archivos", "Lo que Nox lee ahí es información, nunca instrucciones: si una página le dice "
                                       "que haga algo, no lo hace y te avisa."),
        ):
            ui.campo(f, titulo_)
            ui.parrafo(f, texto, color=tema.TEXTO_SUAVE, pady=(0, 2))
        ui.separador(f)
        fila = ctk.CTkFrame(f, fg_color="transparent")
        fila.pack(anchor="w", pady=14)
        ui.boton(fila, "Abrir la bitácora", self._abrir_bitacora, ancho=160, lado="left")
        ui.boton(fila, "Abrir la carpeta de respaldos", self._abrir_respaldos, ancho=220).pack(side="left", padx=10)

    def _abrir_bitacora(self):
        import guardian
        self._abrir(guardian.BITACORA)

    def _abrir_respaldos(self):
        import guardian
        self._abrir(guardian.CARPETA_RESPALDOS)

    def _abrir(self, ruta):
        if not ruta.exists():
            self._mensaje("Todavía no hay nada que mostrar: Nox no ha hecho ninguna acción que registrar.")
            return
        try:
            plataforma.abrir_con_predeterminado(ruta)
        except OSError as e:
            self._mensaje(f"No pude abrirlo: {e}", tema.ROJO)

    # --------------------------------------------------------------- Guardar

    def _guardar(self):
        valores = {clave: lector() for clave, lector in self._lectores.items()}
        antes = {k: self.actual.get(k, "") for k in ("modelo_whisper", "whisper_device", "equipo")}
        try:
            guardado = ajustes.guardar(valores)
        except AjusteInvalido as e:
            self._mensaje(str(e), tema.ROJO)
            return
        except OSError as e:
            self._mensaje(f"No pude guardar el archivo: {e}", tema.ROJO)
            return
        self.actual = guardado
        self._velocidad_original = config.VELOCIDAD_VOZ
        despues = {k: guardado.get(k, "") for k in antes}
        self.al_guardar()
        if despues != antes:
            self._mensaje("Guardado. El cambio de voz o de equipo se aplica al reiniciar Nox.", tema.VERDE)
            if self.al_reiniciar:
                self.boton_reiniciar.pack(side="left", padx=(0, 10))
        else:
            self._mensaje("Guardado. Ya está aplicado.", tema.VERDE)

    def _reiniciar(self):
        if self.al_reiniciar:
            self._cerrar()
            self.al_reiniciar()

    def _cerrar(self):
        self._cerrada = True
        config.VELOCIDAD_VOZ = self._velocidad_original   # si probaste una velocidad y no guardaste
        self._sondear(False)
        try:
            self.destroy()
        except Exception:
            pass


class DialogoServidor(ctk.CTkToplevel):
    """Formulario para añadir un servidor MCP propio."""

    def __init__(self, padre, al_crear):
        super().__init__(padre)
        self.al_crear = al_crear
        self.title("Añadir un servidor MCP")
        self.geometry("560x560")
        self.configure(fg_color=tema.FONDO)
        self.transient(padre)
        marco = ctk.CTkFrame(self, fg_color="transparent")
        marco.pack(fill="both", expand=True, padx=28, pady=20)
        ui.titulo(marco, "Servidor propio")
        ui.parrafo(marco, "Un servidor MCP es código de terceros que se ejecuta con tus permisos. Añade solo los "
                          "que conozcas. Nace apagado y con todas sus herramientas bloqueadas.", color=tema.AMBAR, ancho=500)
        ui.campo(marco, "Nombre")
        self.e_nombre = ui.entrada(marco, "", placeholder="Mi servidor", ancho=460)
        ui.campo(marco, "Programa que lo inicia", "Solo el programa, por ejemplo «npx» o «python». Sin comillas ni símbolos.", ancho=500)
        self.e_comando = ui.entrada(marco, "", placeholder="npx", ancho=460)
        ui.campo(marco, "Argumentos", "Separados por espacios, por ejemplo: -y @playwright/mcp@latest --headless", ancho=500)
        self.e_args = ui.entrada(marco, "", placeholder="-y paquete@latest", ancho=460)
        self.t_error = ui.parrafo(marco, "", color=tema.ROJO, ancho=500, pady=(14, 0))
        fila = ctk.CTkFrame(marco, fg_color="transparent")
        fila.pack(side="bottom", anchor="e", pady=(10, 0))
        ui.boton(fila, "Cancelar", self.destroy, ancho=100, lado="left")
        ui.boton(fila, "Añadir", self._crear, primario=True, ancho=110).pack(side="left", padx=(10, 0))
        self.after(150, lambda: (self.lift(), self.focus_force()))

    def _crear(self):
        nombre = self.e_nombre.get().strip() or "Servidor"
        try:
            args = shlex.split(self.e_args.get(), posix=not plataforma.ES_WINDOWS)
            if plataforma.ES_WINDOWS:
                args = [a[1:-1] if len(a) >= 2 and (a[0] == a[-1] and a[0] in ('"', "'")) else a for a in args]
        except ValueError as e:
            self.t_error.configure(text=f"No entiendo los argumentos: {e}")
            return
        adm = mcp_cliente.administrador()
        sid = mcp_cliente.identificador(nombre)
        base, n = sid, 2
        while sid in adm.servidores:
            sid, n = f"{base}_{n}"[:24], n + 1
        try:
            adm.agregar(sid, {"nombre": nombre, "comando": self.e_comando.get().strip(), "args": args})
        except ConfigInvalida as e:
            self.t_error.configure(text=str(e))
            return
        self.al_crear()
        self.destroy()
