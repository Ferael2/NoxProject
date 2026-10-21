"""
Interfaz grafica de Nox.

Chat escrito, microfono y escucha continua. Todo el trabajo pesado (modelo,
transcripcion, voz) corre en hilos aparte para que la ventana nunca se congele.

El diseño vive en tema.py. Aca solo esta la estructura y el comportamiento.

Uso:
    python gui.py
"""
import sys
import threading
import traceback

import customtkinter as ctk

import ajustes
import config
import mcp_cliente
import nucleo
import plataforma
import recordatorios
import tema

if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

ctk.set_appearance_mode("dark")


class VentanaNox(ctk.CTk):
    def __init__(self):
        # Clase de ventana propia: asi KDE la asocia a nox.desktop y el dock muestra su
        # icono, en vez de agruparla como una ventana "Tk" generica.
        super().__init__(className=config.NOMBRE)

        self.title(config.NOMBRE)
        self._poner_icono()
        self.geometry("1040x760")
        self.minsize(720, 520)
        self.configure(fg_color=tema.FONDO)

        self.conversacion = nucleo.Conversacion(al_usar_herramienta=self._aviso_herramienta)
        self.grabadora = None
        self.grabando = False
        self.ocupado = False
        self.voz_activa = ctk.BooleanVar(value=config.VOZ_ACTIVA)
        self.escucha_activa = ctk.BooleanVar(value=False)
        self.escucha = None
        self.esperando_orden = False
        # Marca de la ultima respuesta: durante unos segundos despues, Nox sigue
        # atento sin que haya que repetir su nombre.
        self.ultima_respuesta = 0.0
        self.etiquetas = []
        self.fila_actividad = None

        self._construir()
        self.bind("<Configure>", self._al_redimensionar)

        # El guardian necesita poder preguntarle a Brian antes de lo irreversible.
        import guardian
        guardian.registrar_confirmador(self.pedir_confirmacion)

        self.ajustes_abiertos = None
        self.protocol("WM_DELETE_WINDOW", self._al_cerrar)
        self.after(100, self._verificar_entorno)
        self.after(1500, self._arrancar_externas)
        self.after(2500, self._saludo_de_la_manana)
        self.after(4000, self._revisar_recordatorios)
        if ajustes.necesita_bienvenida():
            self.after(500, self._bienvenida)

    def _poner_icono(self):
        """Icono de la ventana. Si falta el PNG, la ventana arranca igual."""
        from pathlib import Path
        from tkinter import PhotoImage, TclError

        ruta = config.PROYECTO / "icono.png"
        try:
            self._icono = PhotoImage(file=str(ruta))  # guardado: si no, Tk lo descarta
            self.iconphoto(True, self._icono)
        except TclError:
            pass

    # ------------------------------------------------------------------ layout

    def _construir(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._construir_barra()
        self._construir_chat()
        self._construir_entrada()

        self._mensaje_bienvenida()

    def _construir_barra(self):
        barra = ctk.CTkFrame(self, height=64, fg_color=tema.SUPERFICIE, corner_radius=0)
        barra.grid(row=0, column=0, sticky="ew")
        barra.grid_propagate(False)
        barra.grid_columnconfigure(1, weight=1)

        # Identidad: punto de estado + nombre
        izquierda = ctk.CTkFrame(barra, fg_color="transparent")
        izquierda.grid(row=0, column=0, padx=(tema.AIRE + 4, 0), pady=tema.AIRE, sticky="w")

        self.punto = ctk.CTkLabel(
            izquierda, text="●", font=(tema.FUENTE, 13), text_color=tema.TEXTO_TENUE, width=14
        )
        self.punto.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            izquierda, text=config.NOMBRE, font=tema.TITULO, text_color=tema.TEXTO
        ).pack(side="left")

        self.etiqueta_estado = ctk.CTkLabel(
            izquierda, text="iniciando", font=tema.ETIQUETA, text_color=tema.TEXTO_TENUE
        )
        self.etiqueta_estado.pack(side="left", padx=(12, 0))

        # Controles
        derecha = ctk.CTkFrame(barra, fg_color="transparent")
        derecha.grid(row=0, column=2, padx=(0, tema.AIRE), pady=tema.AIRE, sticky="e")

        self.switch_escucha = ctk.CTkSwitch(
            derecha, text=f'Escuchar "{config.NOMBRE}"', variable=self.escucha_activa,
            command=self._alternar_escucha, font=tema.ETIQUETA,
            text_color=tema.TEXTO_SUAVE, progress_color=tema.AZUL,
            button_color=tema.TEXTO_SUAVE, button_hover_color=tema.TEXTO,
            fg_color=tema.BORDE, width=44, height=22,
        )
        self.switch_escucha.pack(side="left", padx=(0, 18))

        ctk.CTkSwitch(
            derecha, text="Voz", variable=self.voz_activa, font=tema.ETIQUETA,
            text_color=tema.TEXTO_SUAVE, progress_color=tema.AZUL,
            button_color=tema.TEXTO_SUAVE, button_hover_color=tema.TEXTO,
            fg_color=tema.BORDE, width=44, height=22,
        ).pack(side="left", padx=(0, 18))

        ctk.CTkButton(
            derecha, text="⚙  Ajustes", width=96, height=30, command=self._abrir_ajustes,
            font=tema.ETIQUETA, fg_color="transparent", hover_color=tema.ELEVADO,
            text_color=tema.TEXTO_SUAVE, border_width=1, border_color=tema.BORDE,
            corner_radius=tema.RADIO_CHICO,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            derecha, text="Limpiar", width=76, height=30, command=self._limpiar,
            font=tema.ETIQUETA, fg_color="transparent", hover_color=tema.ELEVADO,
            text_color=tema.TEXTO_SUAVE, border_width=1, border_color=tema.BORDE,
            corner_radius=tema.RADIO_CHICO,
        ).pack(side="left")

        # Linea divisoria de un pixel: separa sin dibujar una reja
        ctk.CTkFrame(self, height=1, fg_color=tema.BORDE, corner_radius=0).grid(
            row=0, column=0, sticky="sew"
        )

    def _construir_chat(self):
        self.chat = ctk.CTkScrollableFrame(
            self, fg_color=tema.FONDO, corner_radius=0,
            scrollbar_button_color=tema.BORDE,
            scrollbar_button_hover_color=tema.AZUL_APAGADO,
        )
        self.chat.grid(row=1, column=0, sticky="nsew", padx=tema.AIRE * 2, pady=(tema.AIRE, 0))
        self.chat.grid_columnconfigure(0, weight=1)

    def _construir_entrada(self):
        contenedor = ctk.CTkFrame(self, fg_color="transparent")
        contenedor.grid(row=2, column=0, sticky="ew", padx=tema.AIRE * 2,
                        pady=(tema.AIRE_CHICO, tema.AIRE + 4))
        contenedor.grid_columnconfigure(0, weight=1)

        # Campo con borde sutil que se ilumina al enfocar
        self.marco_campo = ctk.CTkFrame(
            contenedor, fg_color=tema.ELEVADO, corner_radius=tema.RADIO,
            border_width=1, border_color=tema.BORDE,
        )
        self.marco_campo.grid(row=0, column=0, sticky="ew", padx=(0, tema.AIRE_CHICO))
        self.marco_campo.grid_columnconfigure(0, weight=1)

        self.campo = ctk.CTkTextbox(
            self.marco_campo, height=52, font=tema.CUERPO, wrap="word",
            fg_color="transparent", text_color=tema.TEXTO, border_width=0,
            scrollbar_button_color=tema.BORDE,
        )
        self.campo.grid(row=0, column=0, sticky="ew", padx=14, pady=10)
        self.campo.bind("<Return>", self._enter)
        self.campo.bind("<FocusIn>", lambda e: self.marco_campo.configure(border_color=tema.AZUL_APAGADO))
        self.campo.bind("<FocusOut>", lambda e: self.marco_campo.configure(border_color=tema.BORDE))

        botones = ctk.CTkFrame(contenedor, fg_color="transparent")
        botones.grid(row=0, column=1)

        self.boton_mic = ctk.CTkButton(
            botones, text="Hablar", width=88, height=72, command=self._alternar_grabacion,
            font=tema.CUERPO, fg_color="transparent", hover_color=tema.ELEVADO,
            text_color=tema.TEXTO_SUAVE, border_width=1, border_color=tema.BORDE,
            corner_radius=tema.RADIO,
        )
        self.boton_mic.pack(side="left", padx=(0, tema.AIRE_CHICO))

        self.boton_enviar = ctk.CTkButton(
            botones, text="Enviar", width=88, height=72, command=self._enviar,
            font=tema.CUERPO_BOLD, fg_color=tema.AZUL, hover_color=tema.AZUL_HOVER,
            text_color="#FFFFFF", corner_radius=tema.RADIO,
        )
        self.boton_enviar.pack(side="left")

    # ----------------------------------------------------------------- mensajes

    def _ancho_texto(self) -> int:
        return max(360, self.winfo_width() - 180)

    def _al_redimensionar(self, evento=None):
        if evento is not None and evento.widget is not self:
            return
        ancho = self._ancho_texto()
        for etiqueta in self.etiquetas:
            try:
                etiqueta.configure(wraplength=ancho)
            except Exception:
                pass

    def _burbuja(self, texto: str, quien: str, meta: str = ""):
        """
        Un mensaje. El usuario va alineado a la derecha con fondo azul tenue; Nox va a
        la izquierda sobre la superficie elevada; el sistema, discreto y sin fondo.
        """
        fila = ctk.CTkFrame(self.chat, fg_color="transparent")
        fila.grid(sticky="ew", pady=(0, 14))
        fila.grid_columnconfigure(0, weight=1)

        if quien == "sistema":
            etiqueta = ctk.CTkLabel(
                fila, text=texto, font=tema.ETIQUETA, text_color=tema.TEXTO_TENUE,
                justify="left", anchor="w", wraplength=self._ancho_texto(),
            )
            etiqueta.grid(sticky="w", padx=4)
            self.etiquetas.append(etiqueta)
            self._al_fondo()
            return etiqueta

        es_usuario = quien == "vos"
        burbuja = ctk.CTkFrame(
            fila,
            fg_color=tema.AZUL_TENUE if es_usuario else tema.ELEVADO,
            corner_radius=tema.RADIO,
            border_width=0 if es_usuario else 1,
            border_color=tema.BORDE_SUAVE,
        )
        burbuja.grid(row=0, column=0, sticky="e" if es_usuario else "w")
        burbuja.grid_columnconfigure(0, weight=1)

        cabecera = ctk.CTkLabel(
            burbuja,
            text=config.NOMBRE if not es_usuario else "Vos",
            font=tema.ETIQUETA_BOLD,
            text_color=tema.AZUL if not es_usuario else tema.TEXTO_SUAVE,
            anchor="w",
        )
        cabecera.grid(row=0, column=0, sticky="w", padx=16, pady=(10, 0))

        etiqueta = ctk.CTkLabel(
            burbuja, text=texto, font=tema.CUERPO, text_color=tema.TEXTO,
            justify="left", anchor="w", wraplength=self._ancho_texto(),
        )
        etiqueta.grid(row=1, column=0, sticky="ew", padx=16, pady=(3, 12 if not meta else 3))
        self.etiquetas.append(etiqueta)

        if meta:
            ctk.CTkLabel(
                burbuja, text=meta, font=tema.MICRO, text_color=tema.TEXTO_TENUE, anchor="w"
            ).grid(row=2, column=0, sticky="w", padx=16, pady=(0, 10))

        self._al_fondo()
        return etiqueta

    def _mensaje_bienvenida(self):
        self._burbuja(
            f'Escribe abajo, pulsa "Hablar" para dictar, o activa el interruptor para '
            f'llamarlo por su nombre.',
            "sistema",
        )

    def _al_fondo(self):
        self.after(60, lambda: self.chat._parent_canvas.yview_moveto(1.0))

    # --------------------------------------------------------------- actividad

    def _fila_actividad(self, texto: str):
        """Linea tenue que muestra que esta haciendo Nox mientras trabaja."""
        if self.fila_actividad is None:
            self.fila_actividad = ctk.CTkLabel(
                self.chat, text="", font=tema.CODIGO, text_color=tema.TEXTO_TENUE,
                justify="left", anchor="w",
            )
            self.fila_actividad.grid(sticky="w", padx=4, pady=(0, 10))
        self.fila_actividad.configure(text=texto)
        self._al_fondo()

    def _limpiar_actividad(self):
        if self.fila_actividad is not None:
            self.fila_actividad.destroy()
            self.fila_actividad = None

    def _aviso_herramienta(self, nombre: str, args: dict):
        if nombre == "nube":
            texto = f"→ consultando {args.get('modelo', 'la nube')}"
        elif nombre == "nube_fallo":
            texto = f"× la nube no respondio ({args.get('motivo', '')}) — sigo local"
        else:
            resumen = ", ".join(f"{k}={str(v)[:34]}" for k, v in args.items())
            texto = f"· {nombre}({resumen})"
        self.after(0, lambda: self._fila_actividad(texto))

    def _estado(self, texto: str, color: str = None):
        self.etiqueta_estado.configure(text=texto)
        if color:
            self.punto.configure(text_color=color)

    # ----------------------------------------------------------------- acciones

    def _enter(self, evento):
        if not evento.state & 0x1:  # Shift+Enter hace salto de linea
            self._enviar()
            return "break"

    def _enviar(self):
        texto = self.campo.get("1.0", "end").strip()
        if not texto or self.ocupado:
            return
        self.campo.delete("1.0", "end")
        self._procesar(texto)

    def _procesar(self, texto: str, por_voz: bool = False):
        self._limpiar_actividad()
        self._burbuja(texto, "vos")

        self.ocupado = True
        self.boton_enviar.configure(state="disabled", fg_color=tema.AZUL_APAGADO)
        self._estado("pensando", tema.AMBAR)

        def trabajo():
            try:
                respuesta = self.conversacion.enviar(texto)
            except Exception as e:
                respuesta = f"Se me rompio algo: {e}"
                traceback.print_exc()
            self.after(0, lambda: self._mostrar_respuesta(respuesta, por_voz))

        threading.Thread(target=trabajo, daemon=True).start()

    def _mostrar_respuesta(self, respuesta: str, por_voz: bool):
        self._limpiar_actividad()

        origen = self.conversacion.ultimo_origen
        motivo = self.conversacion.ultimo_motivo_ruta
        if origen.startswith("nube") or origen.startswith("openrouter"):
            modelo = origen.split("(")[-1].rstrip(")").split("/")[-1].replace(":free", "")
            meta = f"nube · {modelo}" + (f" · {motivo}" if motivo else "")
        else:
            modelo = origen.split("(")[-1].rstrip(")") if "(" in origen else config.MODELO_CHAT
            meta = f"local · {modelo}" + (f" · {motivo}" if motivo else "")

        self._burbuja(respuesta, "asistente", meta)

        self.ocupado = False
        self.boton_enviar.configure(state="normal", fg_color=tema.AZUL)

        if self.voz_activa.get() or por_voz:
            import time

            import voz

            escuchaba = self.escucha is not None and self.escucha.activa
            if escuchaba:
                self.escucha.detener()

            def hablar_y_reanudar():
                voz.hablar(respuesta)
                # La ventana de conversacion arranca cuando TERMINA de hablar, no
                # cuando empieza: si no, se consumiria mientras Brian lo escucha.
                self.ultima_respuesta = time.time()
                if escuchaba and self.escucha_activa.get():
                    self.escucha.iniciar()
                    self.after(0, lambda: self._estado("seguí, te escucho", tema.AZUL))

            threading.Thread(target=hablar_y_reanudar, daemon=True).start()
        else:
            self._estado("listo", tema.VERDE)

    def _guardar_resumen_de_la_sesion(self, esperar: float = 0.0):
        """Si la persona lo activo en Ajustes, resume la conversacion y guarda lo que valga la pena."""
        if not config.MEMORIA_RESUMEN_SESION:
            return
        import memoria
        mensajes = list(self.conversacion.mensajes)
        hilo = threading.Thread(target=lambda: memoria.guardar_resumen_de_sesion(mensajes), daemon=True)
        hilo.start()
        if esperar:
            hilo.join(timeout=esperar)   # al cerrar, se da un rato para que termine; no se cuelga la salida

    def _limpiar(self):
        self._guardar_resumen_de_la_sesion()
        for w in self.chat.winfo_children():
            w.destroy()
        self.etiquetas.clear()
        self.fila_actividad = None
        self.conversacion.reiniciar()
        self._burbuja("Conversación reiniciada. La memoria permanente se mantiene.", "sistema")

    # ------------------------------------------------------- escucha por nombre

    def _alternar_escucha(self):
        import voz

        if self.escucha_activa.get():
            if self.escucha is None:
                self.escucha = voz.EscuchaContinua(
                    al_activarse=self._me_llamaron,
                    al_oir=self._escuche_algo,
                    al_hablar=self._mientras_habla,
                )
            self._burbuja(
                f'Escuchando. Di "{config.NOMBRE}" seguido de lo que quieras. '
                "La primera vez tarda unos segundos en cargar el modelo.",
                "sistema",
            )
            self._estado("escuchando", tema.AZUL)
            self.escucha.iniciar()
        else:
            if self.escucha is not None:
                self.escucha.detener()
            self.esperando_orden = False
            self._estado("listo", tema.VERDE)
            self._burbuja("Dejo de escuchar.", "sistema")

    def _me_llamaron(self, orden: str):
        self.after(0, lambda: self._procesar_llamado(orden))

    def _procesar_llamado(self, orden: str):
        import random

        import voz

        if self.ocupado:
            return

        # "Hey Nox" pide atencion: se contesta y se espera. "Hola Nox" o "como estas
        # Nox" ya son un mensaje entero y merecen una respuesta de verdad.
        if voz.EscuchaContinua.es_solo_llamada(orden):
            self.esperando_orden = True
            self._estado("te escucho", tema.AZUL)
            voz.hablar_async(random.choice(config.RESPUESTAS_AL_LLAMADO))
            return

        self.esperando_orden = False
        self._procesar(orden, por_voz=True)

    def _mientras_habla(self, segundos: float):
        """
        Mientras Brian habla, mostrar el contador. Sin esto, en un dictado largo la
        ventana parece colgada justo cuando mas atencion le esta prestando.
        """
        # Actualizar cada medio segundo alcanza; mas seguido solo satura la interfaz.
        if int(segundos * 2) == getattr(self, "_ultimo_tick", -1):
            return
        self._ultimo_tick = int(segundos * 2)
        self.after(0, lambda: self._estado(f"te escucho… {segundos:.0f}s", tema.AZUL))

    def _escuche_algo(self, texto: str):
        """
        Todo lo transcripto pasa por aca, se haya nombrado a Nox o no.

        Dos motivos para seguir escuchando sin el nombre:
          - te llamo ("hey Nox") y la orden viene en la frase siguiente
          - acaba de responderte y seguis la conversacion naturalmente
        """
        import time

        self.after(0, lambda: self._estado(f'"{texto[:44]}"', tema.AZUL))

        if self.ocupado:
            return

        limpio = texto.strip()
        if len(limpio.split()) <= 1:
            return  # una palabra suelta suele ser ruido o un "ajá"

        en_conversacion = (
            config.VENTANA_CONVERSACION > 0
            and time.time() - self.ultima_respuesta < config.VENTANA_CONVERSACION
        )

        if not (self.esperando_orden or en_conversacion):
            return

        self.esperando_orden = False
        self.after(0, lambda: self._procesar(limpio, por_voz=True))

    # ------------------------------------------------------------- microfono

    def _alternar_grabacion(self):
        if self.ocupado:
            return
        if not self.grabando:
            self._empezar_a_grabar()
        else:
            self._terminar_de_grabar()

    def _empezar_a_grabar(self):
        import voz

        try:
            self.grabadora = voz.Grabadora(al_grabar=self._mientras_graba)
            self.grabadora.iniciar()
        except Exception as e:
            self._burbuja(f"No pude abrir el micrófono: {e}", "sistema")
            return

        self.grabando = True
        self.boton_mic.configure(
            text="Detener", fg_color=tema.ROJO_HUNDIDO, hover_color=tema.ROJO,
            text_color="#FFFFFF", border_width=0,
        )
        self._estado("grabando · habla tranquilo, sin apuro", tema.ROJO)

    def _mientras_graba(self, segundos: float):
        """Contador durante la grabacion manual. No hay limite de tiempo."""
        if int(segundos) == getattr(self, "_ultimo_seg", -1):
            return
        self._ultimo_seg = int(segundos)
        self.after(0, lambda: self._estado(f"grabando · {segundos:.0f}s", tema.ROJO))

    def _terminar_de_grabar(self):
        import voz

        self.grabando = False
        self.boton_mic.configure(
            text="Hablar", fg_color="transparent", hover_color=tema.ELEVADO,
            text_color=tema.TEXTO_SUAVE, border_width=1,
        )
        self._estado("transcribiendo", tema.AMBAR)

        audio = self.grabadora.detener()
        self.grabadora = None

        if audio.size < config.FRECUENCIA_AUDIO // 2:
            self._estado("listo", tema.VERDE)
            self._burbuja("No escuché nada. Prueba de nuevo.", "sistema")
            return

        def trabajo():
            try:
                texto = voz.transcribir(audio)
            except Exception as e:
                texto = ""
                print("Error transcribiendo:", e)

            if texto:
                self.after(0, lambda: self._procesar(texto, por_voz=True))
            else:
                self.after(0, lambda: (
                    self._estado("listo", tema.VERDE),
                    self._burbuja("No entendí lo que dijiste.", "sistema"),
                ))

        threading.Thread(target=trabajo, daemon=True).start()

    # ---------------------------------------------------------------- ajustes

    def _abrir_ajustes(self, pagina: str = "tu"):
        """Abre la ventana de Ajustes (o la trae al frente si ya estaba abierta)."""
        import ajustes_ui
        if self.ajustes_abiertos is not None and self.ajustes_abiertos.winfo_exists():
            self.ajustes_abiertos.lift()
            self.ajustes_abiertos.focus_force()
            return
        self.ajustes_abiertos = ajustes_ui.VentanaAjustes(
            self, al_guardar=self._ajustes_guardados, al_reiniciar=self._reiniciar_nox, pagina=pagina)

    def _ajustes_guardados(self):
        """Aplica lo recien guardado sin borrar la conversacion."""
        self.voz_activa.set(config.VOZ_ACTIVA)
        self.conversacion.actualizar_prompt()
        self._verificar_entorno()
        self._burbuja("Ajustes aplicados. Desde ahora te hablaré así.", "sistema")

    def _bienvenida(self):
        """La primera vez: el asistente que pregunta como quieres que te hable."""
        import bienvenida_ui
        bienvenida_ui.AsistenteBienvenida(self, al_terminar=self._tras_bienvenida)

    def _tras_bienvenida(self):
        self.voz_activa.set(config.VOZ_ACTIVA)
        self.conversacion.actualizar_prompt()
        self._verificar_entorno()
        self._burbuja(f"Encantado, {config.USUARIO}. Cuando quieras, escríbeme o pulsa «Hablar».", "sistema")

    # ------------------------------------------------------ iniciativa (avisos)

    def _avisar(self, texto: str, titulo: str = "Nox"):
        """Un aviso por iniciativa de Nox: en la ventana, por voz si esta activa, y como notificacion."""
        self._burbuja(texto, "sistema")
        if config.AVISOS_EN_VOZ and self.voz_activa.get():
            import voz
            voz.hablar_async(texto)
        plataforma.notificar(titulo, texto)

    def _saludo_de_la_manana(self):
        """Solo si la persona lo activo en Ajustes (viene apagado) y si todavia no lo dio hoy."""
        try:
            saludo = recordatorios.saludo_matutino()
        except Exception:
            return
        if saludo:
            self._avisar(saludo, "Buenos días")

    def _revisar_recordatorios(self):
        """Cada 15 s mira si algun recordatorio ya toca. Mientras juegas, esperan."""
        try:
            if config.AVISAR_RECORDATORIOS:
                import sistema
                jugando = config.CEDER_GPU_AL_JUGAR and sistema.hay_juego_corriendo()
                if not jugando:
                    for r in recordatorios.vencidos():
                        self._avisar(f"⏰ Recordatorio: {r['texto']}", "Recordatorio")
                        recordatorios.marcar_avisado(r["id"])
        except Exception as e:   # un fallo aqui nunca debe tumbar la ventana
            print(f"No pude revisar los recordatorios: {e}")
        self.after(15000, self._revisar_recordatorios)

    def _arrancar_externas(self):
        """Conecta, en segundo plano, los servidores de herramientas externas que estan activos."""
        try:
            mcp_cliente.administrador().arrancar()
        except Exception as e:   # un servidor roto nunca debe impedir que Nox abra
            print(f"No pude arrancar las herramientas externas: {e}")

    def _reiniciar_nox(self):
        """Cierra Nox y lo vuelve a abrir (para lo que solo se aplica al arrancar)."""
        from pathlib import Path
        plataforma.lanzar([sys.executable, str(Path(__file__).resolve())])
        self._al_cerrar()

    def _al_cerrar(self):
        """Cierre ordenado: apaga la escucha y los servidores externos antes de salir."""
        try:
            self._guardar_resumen_de_la_sesion(esperar=25)
            if self.escucha is not None:
                self.escucha.detener()
            mcp_cliente.administrador().detener_todo(3)
        except Exception:
            pass
        self.destroy()

    # ----------------------------------------------------------- confirmacion

    def pedir_confirmacion(self, herramienta: str, args: dict) -> bool:
        """
        Le pregunta a Brian antes de una accion que ningun respaldo puede deshacer.

        La llama guardian.py desde el hilo de trabajo, asi que hay que rebotar el
        dialogo al hilo de la interfaz y esperar la respuesta.
        """
        import queue

        respuesta = queue.Queue(maxsize=1)

        detalle = ", ".join(f"{k}: {v}" for k, v in args.items())
        titulos = {"cerrar_programa": "Cerrar un programa"}
        titulo = titulos.get(herramienta, herramienta)
        aviso = "Si el programa tiene trabajo sin guardar, se puede perder."
        if herramienta.startswith("mcp_"):
            titulo = "Usar una herramienta externa"
            detalle = f"{mcp_cliente.administrador().describir(herramienta)}\n{detalle}".strip()
            aviso = "Es de un servidor externo (código de terceros). Revisa qué va a hacer antes de permitirlo."

        def mostrar():
            dialogo = ctk.CTkToplevel(self)
            dialogo.title("Confirmar")
            dialogo.geometry("460x230")
            dialogo.configure(fg_color=tema.SUPERFICIE)
            dialogo.resizable(False, False)
            dialogo.transient(self)
            dialogo.grab_set()

            # Centrado sobre la ventana principal
            self.update_idletasks()
            x = self.winfo_x() + (self.winfo_width() - 460) // 2
            y = self.winfo_y() + (self.winfo_height() - 230) // 2
            dialogo.geometry(f"+{max(x, 0)}+{max(y, 0)}")

            ctk.CTkLabel(
                dialogo, text=titulo, font=tema.TITULO, text_color=tema.TEXTO
            ).pack(pady=(26, 6), padx=26, anchor="w")

            ctk.CTkLabel(
                dialogo, text=detalle, font=tema.CUERPO, text_color=tema.TEXTO_SUAVE,
                wraplength=400, justify="left",
            ).pack(padx=26, anchor="w")

            ctk.CTkLabel(
                dialogo,
                text=aviso,
                font=tema.ETIQUETA, text_color=tema.TEXTO_TENUE,
                wraplength=400, justify="left",
            ).pack(padx=26, pady=(10, 0), anchor="w")

            botones = ctk.CTkFrame(dialogo, fg_color="transparent")
            botones.pack(side="bottom", fill="x", padx=26, pady=22)

            def responder(valor):
                if respuesta.empty():
                    respuesta.put(valor)
                dialogo.grab_release()
                dialogo.destroy()

            ctk.CTkButton(
                botones, text="Cancelar", width=110, height=34,
                command=lambda: responder(False), font=tema.CUERPO,
                fg_color="transparent", hover_color=tema.ELEVADO,
                text_color=tema.TEXTO_SUAVE, border_width=1, border_color=tema.BORDE,
                corner_radius=tema.RADIO_CHICO,
            ).pack(side="right")

            ctk.CTkButton(
                botones, text="Permitir", width=110, height=34,
                command=lambda: responder(True), font=tema.CUERPO_BOLD,
                fg_color=tema.AZUL, hover_color=tema.AZUL_HOVER,
                text_color="#FFFFFF", corner_radius=tema.RADIO_CHICO,
            ).pack(side="right", padx=(0, 10))

            # Cerrar la ventana con la X equivale a cancelar.
            dialogo.protocol("WM_DELETE_WINDOW", lambda: responder(False))

        self.after(0, mostrar)

        try:
            return respuesta.get(timeout=120)
        except Exception:
            return False  # sin respuesta a tiempo, no se hace

    # -------------------------------------------------------------- arranque

    def _verificar_entorno(self):
        ok, mensaje = nucleo.verificar_ollama()
        if not ok:
            self._estado("sin modelo local", tema.ROJO)
            self._burbuja(
                mensaje + "\n\nAbre Ollama y reinicia esta ventana.", "sistema"
            )
            return

        import nube
        if nube.disponible():
            self._estado("listo · local + nube", tema.VERDE)
        else:
            self._estado("listo · solo local", tema.VERDE)


def main():
    VentanaNox().mainloop()


if __name__ == "__main__":
    main()
