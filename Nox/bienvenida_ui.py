"""
El asistente de bienvenida: lo primero que ve quien abre Nox por primera vez.

Pregunta, en pocos pasos y sin tocar ningun archivo: como te llamas, como quieres que te
hable, que equipo tienes (lo detecta y lo sugiere), y descarga los modelos que falten. Todo se
guarda con ajustes.py, igual que la ventana de Ajustes, y se puede cambiar despues alli.
"""
import customtkinter as ctk

import ajustes
import config
import modelos
import tema
import ui_comun as ui
from ajustes import AjusteInvalido
from ajustes_ui import NOMBRES_PERFIL


class AsistenteBienvenida(ctk.CTkToplevel):
    PASOS = ["Hola", "Cómo hablarte", "Tu equipo", "Voz y privacidad", "Listo"]

    def __init__(self, padre, al_terminar=None):
        super().__init__(padre)
        self.al_terminar = al_terminar or (lambda: None)
        self.paso = 0
        self._cerrada = False
        self._terminado = False
        self._descargando = False
        self._sugerido = None

        self.title("Bienvenida a Nox")
        self.geometry("720x700")
        self.minsize(640, 600)
        self.configure(fg_color=tema.FONDO)
        self.transient(padre)

        # Lo que se va juntando; se guarda todo junto al final.
        self.v_usuario = ctk.StringVar(value=config.USUARIO)
        self.v_trato = ctk.StringVar(value="Tú")
        self.v_tono = ctk.StringVar(value="natural")
        self.v_estilo = ""
        self.v_equipo = ctk.StringVar(value=NOMBRES_PERFIL[config.EQUIPO])
        self.v_voz = ctk.BooleanVar(value=True)
        self.v_nube = ctk.BooleanVar(value=True)

        self._construir_marco()
        self.protocol("WM_DELETE_WINDOW", self._cerrar)
        self.after(150, lambda: (self.lift(), self.focus_force()))
        self._mostrar()

    # ----------------------------------------------------------------- marco

    def _construir_marco(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        cabecera = ctk.CTkFrame(self, fg_color=tema.SUPERFICIE, corner_radius=0, height=56)
        cabecera.grid(row=0, column=0, sticky="ew")
        cabecera.grid_propagate(False)
        self.puntos = []
        fila = ctk.CTkFrame(cabecera, fg_color="transparent")
        fila.pack(expand=True)
        for _ in self.PASOS:
            p = ctk.CTkLabel(fila, text="●", font=(tema.FUENTE, 14), text_color=tema.BORDE)
            p.pack(side="left", padx=6)
            self.puntos.append(p)

        self.cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        self.cuerpo.grid(row=1, column=0, sticky="nsew", padx=44, pady=(26, 8))

        pie = ctk.CTkFrame(self, fg_color=tema.SUPERFICIE, corner_radius=0, height=68)
        pie.grid(row=2, column=0, sticky="ew")
        pie.grid_propagate(False)
        pie.grid_columnconfigure(0, weight=1)
        self.aviso = ctk.CTkLabel(pie, text="", font=tema.ETIQUETA, text_color=tema.ROJO, anchor="w",
                                  wraplength=360, justify="left")
        self.aviso.grid(row=0, column=0, padx=24, sticky="w")
        botones = ctk.CTkFrame(pie, fg_color="transparent")
        botones.grid(row=0, column=1, padx=20, pady=16, sticky="e")
        self.b_saltar = ui.boton(botones, "Configurar después", self._saltar, ancho=170)
        self.b_saltar.pack(side="left", padx=(0, 10))
        self.b_atras = ui.boton(botones, "Atrás", self._atras, ancho=90)
        self.b_atras.pack(side="left", padx=(0, 10))
        self.b_siguiente = ui.boton(botones, "Siguiente", self._siguiente, primario=True, ancho=130)
        self.b_siguiente.pack(side="left")

    def _mostrar(self):
        for w in self.cuerpo.winfo_children():
            w.destroy()
        for i, p in enumerate(self.puntos):
            p.configure(text_color=tema.AZUL if i == self.paso else (tema.AZUL_APAGADO if i < self.paso else tema.BORDE))
        self.aviso.configure(text="")
        getattr(self, f"_paso_{self.paso}")(self.cuerpo)
        ultimo = self.paso == len(self.PASOS) - 1
        self.b_siguiente.configure(text="Empezar" if ultimo else "Siguiente")
        if self.paso == 0:
            self.b_atras.pack_forget()
        else:
            self.b_atras.pack(side="left", padx=(0, 10), before=self.b_siguiente)
        if ultimo:
            self.b_saltar.pack_forget()

    # ---------------------------------------------------------------- pasos

    def _paso_0(self, f):
        ui.titulo(f, f"Hola, soy {config.NOMBRE}", tamano=26)
        ui.parrafo(f, "Soy un asistente que vive en tu equipo: converso contigo, recuerdo lo que me cuentas, y puedo "
                      "abrir programas, buscar en tus notas y ayudarte con documentos. Casi todo ocurre aquí, sin "
                      "enviar tus cosas a internet.", ancho=620, pady=(6, 18))
        ui.campo(f, "Para empezar, ¿cómo te llamas?", "Así me dirigiré a ti.")
        self.e_usuario = ui.entrada(f, self.v_usuario.get(), placeholder="Tu nombre", ancho=360)
        self.e_usuario.focus()
        ui.parrafo(f, "Esto tarda un minuto y todo se puede cambiar después en Ajustes.", pady=(24, 0))

    def _paso_1(self, f):
        ui.titulo(f, "¿Cómo quieres que me dirija a ti?")
        ui.parrafo(f, "Elige el trato y el tono. Lo puedes afinar después con tus propias instrucciones.", ancho=620)
        ui.campo(f, "Trato")
        self.s_trato = ui.segmentado(f, ["Tú", "Usted"], self.v_trato.get(), comando=self.v_trato.set)
        ui.campo(f, "Tono")
        for clave, (etiqueta, descripcion) in config.TONOS.items():
            fila = ctk.CTkFrame(f, fg_color="transparent")
            fila.pack(anchor="w", fill="x", pady=2)
            ctk.CTkRadioButton(fila, text=etiqueta, variable=self.v_tono, value=clave, font=tema.CUERPO_BOLD,
                               text_color=tema.TEXTO, fg_color=tema.AZUL, hover_color=tema.AZUL_HOVER,
                               border_color=tema.BORDE, width=120).pack(side="left")
            ctk.CTkLabel(fila, text=descripcion, font=tema.ETIQUETA, text_color=tema.TEXTO_TENUE,
                         anchor="w").pack(side="left", padx=(6, 0))
        ui.campo(f, "¿Algo más sobre cómo responder? (opcional)",
                 "Por ejemplo: «Explícame con ejemplos» o «Evita las metáforas».", ancho=620)
        self.c_estilo = ui.caja_texto(f, self.v_estilo, alto=64, ancho=620)

    def _paso_2(self, f):
        ui.titulo(f, "Tu equipo")
        if config.MOTOR_CHAT == "openrouter":
            ui.parrafo(f, "Nox utiliza OpenRouter en la nube como motor principal. No necesitas descargar modelos pesados ni tener una tarjeta gráfica potente.", ancho=620)
        else:
            ui.parrafo(f, "Elijo el modelo de IA según tu tarjeta de video. Lo miro yo; tú decides.", ancho=620)
        self.t_equipo = ui.parrafo(f, "Mirando tu equipo…", color=tema.TEXTO_SUAVE, ancho=620, pady=(8, 4))
        ui.campo(f, "Perfil")
        ui.menu(f, list(NOMBRES_PERFIL.values()), self.v_equipo.get(), comando=self.v_equipo.set, ancho=360)
        if config.MOTOR_CHAT == "openrouter":
            ui.campo(f, "Modelos de IA", "En modo nube, Nox usa OpenRouter directamente. La descarga de modelos locales es opcional.", ancho=620)
        else:
            ui.campo(f, "Modelos de IA", "Se descargan una sola vez (unos 5,5 GB en total) y se quedan en tu equipo.", ancho=620)
        self.f_modelos = ctk.CTkFrame(f, fg_color="transparent")
        self.f_modelos.pack(anchor="w", fill="x")
        ui.en_hilo(self, ajustes.detectar_equipo, self._deteccion)
        self._pintar_modelos()

    def _deteccion(self, ok, datos):
        if self._cerrada or self.paso != 2:
            return
        if not ok:
            self.t_equipo.configure(text="No pude detectar tu equipo. Elige el perfil a mano.", text_color=tema.AMBAR)
            return
        gpu = datos["gpu"] or "Sin tarjeta dedicada"
        vram = f" ({datos['vram_gb']} GB)" if datos["vram_gb"] else ""
        ram = f", {datos['ram_gb']} GB de RAM" if datos["ram_gb"] else ""
        self.t_equipo.configure(text=f"Encontré: {gpu}{vram}{ram}. {datos['motivo']}", text_color=tema.TEXTO_SUAVE)
        self.v_equipo.set(NOMBRES_PERFIL[datos["sugerido"]])
        self._mostrar_perfil_elegido()

    def _mostrar_perfil_elegido(self):
        """Redibuja el menu para que muestre la sugerencia (el widget no sigue a la variable)."""
        if self.paso == 2 and not self._cerrada:
            for w in self.cuerpo.winfo_children():
                if isinstance(w, ctk.CTkOptionMenu):
                    w.set(self.v_equipo.get())

    def _pintar_modelos(self):
        ui.en_hilo(self, lambda: (modelos.necesarios(), modelos.instalados(), modelos.ollama_activo()),
                   self._dibujar_modelos)

    def _dibujar_modelos(self, ok, datos):
        if not ok or self._cerrada or self.paso != 2:
            return
        for w in self.f_modelos.winfo_children():
            w.destroy()
        necesarios, instalados, activo = datos
        if config.MOTOR_CHAT == "openrouter":
            ctk.CTkLabel(self.f_modelos,
                         text=f"✓  Motor en la nube activo: {config.MODELO_OPENROUTER}",
                         font=tema.CUERPO_BOLD, text_color=tema.VERDE, anchor="w").pack(anchor="w", pady=(0, 2))
            ctk.CTkLabel(self.f_modelos,
                         text="Las memorias y herramientas funcionan de forma privada en tu equipo sin descargas pesadas.",
                         font=tema.ETIQUETA, text_color=tema.TEXTO_SUAVE, anchor="w").pack(anchor="w", pady=(0, 6))
            if activo:
                faltan = [m for m in necesarios if not modelos.esta_instalado(m, instalados)]
                if faltan:
                    ctk.CTkLabel(self.f_modelos,
                                 text="Modelos locales de Ollama (opcionales para modo sin conexión):",
                                 font=tema.ETIQUETA, text_color=tema.TEXTO_TENUE, anchor="w").pack(anchor="w", pady=(4, 2))
                    for m in necesarios:
                        esta = m not in faltan
                        ctk.CTkLabel(self.f_modelos, text=f"{'✓' if esta else '✗'}  {m} (opcional)", font=tema.ETIQUETA,
                                     text_color=tema.VERDE if esta else tema.TEXTO_TENUE).pack(anchor="w")
                    self._b_descargar = ui.boton(self.f_modelos, f"Descargar modelos locales opcionales ({len(faltan)})",
                                                 lambda: self._descargar(faltan), primario=False, ancho=290)
                    self._b_descargar.pack(anchor="w", pady=(8, 0))
            return

        if not activo:
            ctk.CTkLabel(self.f_modelos, text="Ollama (el programa que corre los modelos) no responde. Instálalo desde "
                         "ollama.com y ábrelo; después pulsa «Volver a mirar». Puedes seguir y hacerlo más tarde.",
                         font=tema.ETIQUETA, text_color=tema.AMBAR, anchor="w", wraplength=600, justify="left").pack(anchor="w")
            ui.boton(self.f_modelos, "Volver a mirar", self._pintar_modelos, ancho=130).pack(anchor="w", pady=(8, 0))
            return
        faltan = [m for m in necesarios if not modelos.esta_instalado(m, instalados)]
        for m in necesarios:
            esta = m not in faltan
            ctk.CTkLabel(self.f_modelos, text=f"{'✓' if esta else '✗'}  {m}", font=tema.CUERPO,
                         text_color=tema.VERDE if esta else tema.AMBAR).pack(anchor="w")
        if faltan:
            self._barra = ui.barra(self.f_modelos, 460)
            self._t_descarga = ctk.CTkLabel(self.f_modelos, text="", font=tema.ETIQUETA, text_color=tema.TEXTO_TENUE)
            self._b_descargar = ui.boton(self.f_modelos, f"Descargar lo que falta ({len(faltan)})",
                                         lambda: self._descargar(faltan), primario=True, ancho=250)
            self._b_descargar.pack(anchor="w", pady=(10, 0))

    def _descargar(self, faltan):
        self._b_descargar.configure(state="disabled")
        self._barra.pack(anchor="w", pady=(10, 4))
        self._t_descarga.pack(anchor="w")
        progreso = ui.Progreso()
        self._descargando = True

        def trabajo():
            for m in faltan:
                ok, msg = modelos.descargar(m, lambda f, t, m=m: (setattr(progreso, "fraccion", f),
                                                                   setattr(progreso, "texto", f"{m}: {t}")))
                if not ok:
                    return msg
            return ""

        def pintar():
            if self._cerrada or self.paso != 2:
                return
            self._barra.set(progreso.fraccion)
            self._t_descarga.configure(text=progreso.texto)
            if self._descargando:
                self.after(250, pintar)

        def terminado(ok, error):
            self._descargando = False
            if self._cerrada or self.paso != 2:
                return
            if ok and not error:
                self._pintar_modelos()
            else:
                self._t_descarga.configure(text=str(error), text_color=tema.ROJO)
                self._b_descargar.configure(state="normal")

        pintar()
        ui.en_hilo(self, trabajo, terminado)

    def _guardar_key_paso3(self):
        if hasattr(self, "e_key"):
            val = self.e_key.get().strip()
            if val.startswith("sk-or-"):
                ajustes.guardar_key(val)
                self.t_key_estado.configure(text="✓ Clave guardada correctamente.", text_color=tema.VERDE)
            else:
                self.t_key_estado.configure(text="La clave debe comenzar con 'sk-or-'.", text_color=tema.ROJO)

    def _paso_3(self, f):
        ui.titulo(f, "Voz y privacidad")
        ui.parrafo(f, "Dos decisiones rápidas. Ambas se pueden cambiar en Ajustes.", ancho=620)
        ui.campo(f, "Voz", "Puedo responderte en voz alta. Para hablarme necesitas un micrófono; escribirme siempre funciona.", ancho=620)
        ui.interruptor(f, "Responder en voz alta", self.v_voz.get(), variable=self.v_voz)
        ui.campo(f, "Internet y nube", "Nox se apoya en OpenRouter en la nube para conversar. Tus notas, tu memoria, "
                 "tus archivos y lo que me cuentas de ti NUNCA salen de tu equipo; solo viaja la pregunta.", ancho=620)
        ui.interruptor(f, "Usar OpenRouter para conversar",
                       self.v_nube.get(), variable=self.v_nube)
        import nube
        if nube.disponible():
            ctk.CTkLabel(f, text="✓ Clave de OpenRouter configurada en openrouter.key.",
                         font=tema.ETIQUETA, text_color=tema.VERDE).pack(anchor="w", pady=(4, 0))
        else:
            fila_k = ctk.CTkFrame(f, fg_color="transparent")
            fila_k.pack(anchor="w", fill="x", pady=(6, 2))
            self.e_key = ui.entrada(fila_k, "", placeholder="Pega tu clave sk-or-v1-...", ancho=380)
            self.e_key.pack_configure(side="left")
            ui.boton(fila_k, "Guardar clave", self._guardar_key_paso3, ancho=120, lado="left").pack(side="left", padx=(8, 0))
            self.t_key_estado = ctk.CTkLabel(f, text="Se necesita una clave de OpenRouter (gratuita en openrouter.ai) para conversar.",
                                              font=tema.ETIQUETA, text_color=tema.TEXTO_TENUE)
            self.t_key_estado.pack(anchor="w")

    def _paso_4(self, f):
        ui.titulo(f, f"Todo listo, {self.v_usuario.get()}", tamano=26)
        ui.parrafo(f, "Esto es lo que quedó:", ancho=620, pady=(6, 10))
        trato = "de usted" if self.v_trato.get() == "Usted" else "de tú"
        resumen = [
            f"Te llamaré {self.v_usuario.get()} y te hablaré {trato}, con un tono {config.TONOS[self.v_tono.get()][0].lower()}.",
            f"Tu equipo: {self.v_equipo.get()}.",
            "Responderé en voz alta." if self.v_voz.get() else "Te responderé solo por escrito.",
            "Motor de conversación: OpenRouter en la nube (rápido y sin descargas pesadas)." if config.MOTOR_CHAT == "openrouter" else ("Usaré la nube para preguntas generales." if self.v_nube.get() else "Todo se responderá en tu equipo."),
        ]
        for linea in resumen:
            ctk.CTkLabel(f, text="•  " + linea, font=tema.CUERPO, text_color=tema.TEXTO, anchor="w",
                         justify="left", wraplength=620).pack(anchor="w", pady=3)
        ui.parrafo(f, "Si algo no te convence, abre Ajustes (el engranaje de arriba) y cámbialo cuando quieras.",
                   ancho=620, pady=(20, 0))

    # ------------------------------------------------------------ navegacion

    def _recoger(self):
        """Guarda en memoria lo que la persona puso en el paso actual."""
        if self.paso == 0:
            self.v_usuario.set(self.e_usuario.get().strip() or config.USUARIO)
        elif self.paso == 1:
            self.v_estilo = ui.leer_caja(self.c_estilo)
        elif self.paso == 3:
            if hasattr(self, "e_key"):
                val = self.e_key.get().strip()
                if val.startswith("sk-or-"):
                    ajustes.guardar_key(val)

    def _siguiente(self):
        if self._descargando:
            self.aviso.configure(text="Espera a que termine la descarga.")
            return
        self._recoger()
        if self.paso == len(self.PASOS) - 1:
            self._finalizar()
            return
        self.paso += 1
        self._mostrar()

    def _atras(self):
        if self._descargando:
            return
        self._recoger()
        if self.paso > 0:
            self.paso -= 1
            self._mostrar()

    def _finalizar(self):
        clave_perfil = next((k for k, n in NOMBRES_PERFIL.items() if n == self.v_equipo.get()), config.EQUIPO_POR_DEFECTO)
        try:
            ajustes.guardar({
                "usuario": self.v_usuario.get(),
                "trato": "usted" if self.v_trato.get() == "Usted" else "tu",
                "tono": self.v_tono.get(),
                "estilo": self.v_estilo,
                "equipo": clave_perfil,
                "voz_activa": self.v_voz.get(),
                "usar_nube": self.v_nube.get(),
                "bienvenida_hecha": True,
            })
        except (AjusteInvalido, OSError) as e:
            self.aviso.configure(text=str(e))
            return
        self._terminado = True
        self._cerrar()
        self.al_terminar()

    def _saltar(self):
        """Usar los valores por defecto y no volver a preguntar; todo queda en Ajustes."""
        try:
            ajustes.guardar({"bienvenida_hecha": True})
        except (AjusteInvalido, OSError):
            pass
        self._terminado = True
        self._cerrar()
        self.al_terminar()

    def _cerrar(self):
        """Cerrar la ventana a medias NO marca la bienvenida como hecha: se vuelve a ofrecer."""
        self._cerrada = True
        self._descargando = False
        try:
            self.destroy()
        except Exception:
            pass
