# Hoja de ruta: acercar Nox a un "Jarvis"

Investigado el **2026-10-20**. Cada dato dice de dónde sale. Regla de este documento: una
herramienta entra solo si su página oficial (repositorio o biblioteca de Ollama) confirma lo
que se afirma; lo que solo dice un blog queda marcado como **sin verificar**.

## 1. En qué modelos se basa Nox hoy

| Pieza | Qué usa Nox | Notas |
|---|---|---|
| **Conversación** | **Qwen3 8B** (`qwen3:8b` en Ollama) | Familia Qwen3, publicada el 28 abr 2025 con licencia Apache 2.0. En Ollama: 5,2 GB, contexto de 40K, con herramientas y razonamiento. |
| Búsqueda por significado | `nomic-embed-text` | Convierte texto en vectores. |
| Escuchar | `faster-whisper`, modelos `medium` / `small` | Corre en **CPU** (ver 3.1). |
| Hablar | Piper, voz `es_MX-claude-high` | Local, ~0,3 s por frase. |
| Nube (opcional) | `nemotron-3-super-120b` vía OpenRouter | Solo preguntas que no tocan nada personal. |

También hay un `qwen3:14b` instalado, pero **no se usa**: medido en este equipo iba a 2,2
tokens/s contra 6,8 del 8B, porque se desborda a la RAM.

**Qwen3 es de abril de 2025; la familia ya avanzó bastante.** Estado verificado hoy:

| Familia | Fecha | Sobre Ollama (biblioteca oficial) | ¿Cabe en 8 GB de VRAM? |
|---|---|---|---|
| Qwen3 | abr 2025 | 0,6b a 235b | `8b` sí (es el actual) |
| **Qwen3.5** | feb 2026 | 0,8b, 2b, 4b, **9b**, 27b, 35b, 122b. Todas con visión, herramientas, razonamiento y contexto de 256K | `4b` (3,3–4,0 GB) sí; `9b` (6,6–7,6 GB) **justo** |
| Qwen3.6 | abr 2026, Apache 2.0 | solo 27b y 35b | No (18–24 GB) |
| Qwen3.8 | ago 2026 | solo 27b abierto (Apache 2.0); el resto es propietario o con licencia restrictiva | No |
| Qwen 4 | — | Solo anunciado; `qwen3.8-flash-next` es una vista previa experimental de su arquitectura | — |

Conclusión: **para esta tarjeta (8 GB) los candidatos reales son `qwen3.5:4b` y `qwen3.5:9b`.**
Los modelos grandes de Qwen3.6 y 3.8 no caben, y el 14B ya demostró que la RAM sola no alcanza.

> ⚠️ **No cambies el modelo "a ojo".** Hay un error documentado de `qwen3.5:9b` con Ollama:
> a veces escribe la llamada a la herramienta como texto en vez de ejecutarla (issue #14745,
> reportado en marzo de 2026 con Ollama 0.17.x, cerrado el 27 mar 2026 por el PR #15022;
> la página no dice en qué versión quedó el arreglo). Ollama va hoy por la 0.40.6. Debería
> estar resuelto, pero hay que **medirlo con las herramientas de Nox** (fase 1).
>
> **Ya se midió (2026-10-20): no está resuelto en este equipo.** Con Ollama 0.40.3,
> `qwen3.5:9b` no pidió la herramienta en 15 de 81 pruebas e **inventó la hora** en vez de
> consultarla. Ver la sección 7. (Ollama ya va por la 0.40.6; no se probó con esa versión.)

## 2. La idea central

Un "Jarvis" no es un modelo más grande: es **más sentidos, más manos y más iniciativa**
sobre un modelo suficiente. Las mejoras se agrupan así:

| Sentidos | Cerebro | Memoria | Manos | Iniciativa |
|---|---|---|---|---|
| oír mejor, ver la pantalla | modelo más nuevo, bien medido | recordar mejor | más herramientas, con permiso | avisar sin que se lo pidan |

Y siempre bajo la regla de Nox: **lista blanca, confirmación en lo irreversible, y lo
personal no sale.**

## 3. Herramientas verificadas, por área

### 3.1 Oídos (voz de entrada)

| Herramienta | Qué aporta | Lo verificado | Cuidado |
|---|---|---|---|
| **openWakeWord** | Detectar "Nox" sin transcribir la frase. Hoy la escucha continua espera a oír una voz y entonces transcribe la frase entera con Whisper `small`, para buscar "Nox" en el texto. | Código Apache 2.0, `pip install openwakeword`, funciona en Linux y Windows. Se entrenan palabras propias con voz sintética (cuaderno de Colab, menos de 1 hora). | Los modelos ya entrenados son **CC BY-NC-SA** (no comercial; para la universidad sirve). La página dice **solo inglés**: hay que probar si "Nox" en español se detecta bien. |
| **Silero VAD** | Saber qué es voz y cuándo terminaste de hablar. Antes se usaba un umbral de volumen (`UMBRAL_SILENCIO`), que se confunde con ruido. | MIT, ~2 MB, menos de 1 ms por bloque de 30 ms, 8 y 16 kHz. | ✅ **HECHO (Fase 2).** `faster-whisper` ya trae el modelo empaquetado y `onnxruntime` ya estaba instalado, así que **no hizo falta `torch` ni ninguna dependencia nueva** (`vad.py`). |
| **whisper.cpp** | Transcribir en la **GPU AMD**. | MIT; soporta Vulkan y ROCm/HIP (la página cita tarjetas AMD), Windows y Linux, y tiene transcripción en tiempo real. | Competiría por los 8 GB de VRAM con el modelo de conversación: hay que medir si compensa. |
| `faster-whisper` (el actual) | — | MIT. Su GPU es **solo NVIDIA** (CUDA); por eso en una Radeon corre en CPU. | — |

### 3.2 Boca (voz de salida)

| Herramienta | Lo verificado | Cuidado |
|---|---|---|
| **Piper** (el actual) | `pip install piper-tts`, licencia GPL-3.0. | La Open Home Foundation anuncia que **busca mantenedores**: riesgo de que se estanque. |
| **Kokoro** | 82 millones de parámetros, Apache 2.0, `pip install kokoro`, **soporta español** (código `e`) y Windows. | La página no lista voces en español: hay que escucharlas y comparar con la actual. Necesita `espeak-ng` y `torch`. |

### 3.3 Cerebro (modelo)

Ver la tabla de la sección 1. Qué hacer: **medir** `qwen3.5:4b` y `qwen3.5:9b` contra el
actual con las mismas tareas (fase 1). Las ventajas que prometen sobre el actual (visión
nativa, contexto de 256K) son reales según Ollama; que sean *mejores en herramientas* en
este equipo, no está demostrado.

### 3.4 Conocimiento (bóveda)

| Herramienta | Lo verificado |
|---|---|
| **Qwen3-Embedding** (0.6b, 4b, 8b) | Está en la biblioteca de Ollama como modelo de embeddings. Varias guías lo ubican por encima de `nomic-embed-text` en calidad (**sin verificar** con una prueba propia); el 0.6b ocupa ~1,5 GB. |
| Re-ranking | Un modelo que reordena los fragmentos encontrados suele mejorar más que cambiar el generador (afirmación de blogs, **sin verificar**). Que exista en Ollama tampoco está confirmado. |

Se prueba con **tus propias consultas** sobre tu bóveda (944 fragmentos). Cambiar el modelo de
embeddings obliga a reindexar, y el índice lo comparte la bóveda con Nox.

### 3.5 Memoria

| Herramienta | Lo verificado | Veredicto |
|---|---|---|
| **Mem0** | Apache 2.0. Pero su README usa OpenAI por defecto, **no confirma** que funcione 100 % con Ollama, y las funciones avanzadas son de la versión de pago. | No adoptar ahora. |
| **Letta (MemGPT)** | Es una plataforma de agentes completa, no una librería. Solo conocido por guías de comparación. | Demasiado grande para lo que Nox necesita. |

La memoria propia de Nox (`memoria.py`, SQLite + embeddings) ya hace lo esencial. Es mejor
**mejorarla en casa**: resumir recuerdos viejos, detectar duplicados, y un resumen diario.

### 3.6 Manos (acciones)

| Herramienta | Lo verificado |
|---|---|
| **MCP (Model Context Protocol)** | SDK oficial de Python con licencia MIT, Python 3.11+, transportes stdio, HTTP y SSE. Permite que Nox sea un *cliente* y use las herramientas de cualquier servidor MCP. Ollama no habla MCP directamente: hace falta un puente que traduzca los esquemas (existe el cliente `ollmcp`, MIT, como ejemplo). |
| **Playwright MCP** | Apache 2.0. Deja que el modelo navegue y rellene páginas usando el árbol de accesibilidad (**no necesita visión**). Requiere Node.js 18+. ✅ **Probado en la práctica** (sección 7.3): trae 25 herramientas, varias que ejecutan código. |

**Esta es la mejora con más potencial y la que más cuidado pide.** Un servidor MCP es código
de terceros con acceso real. Para que encaje en Nox tiene que cumplir su filosofía:
**lista blanca** de servidores y de herramientas permitidas, `guardian.py` confirmando lo
irreversible, y nada de lo personal expuesto a esos servidores.

### 3.7 Vista

`qwen3-vl` (2b, 4b, 8b) y toda la familia `qwen3.5` tienen visión en Ollama. Permitiría
"mira mi pantalla y dime qué error es éste". Cuidado con los 8 GB: modelo de chat y modelo de
visión a la vez no caben; hay que cargarlos por turnos. En Wayland capturar la pantalla
exige pasar por los portales del sistema.

## 4. Plan por fases

Cada fase es pequeña y se prueba antes de pasar a la siguiente.

| Fase | Qué se hace | Por qué en este orden | Resultado esperado |
|---|---|---|---|
| **1. Medir** ✅ | `evaluar_modelo.py`: una batería de pedidos reales (abrir un programa, buscar en la bóveda, escribir un archivo, rechazar algo peligroso) que mide aciertos, tiempo y VRAM. | Sin esto, cualquier cambio de modelo es una apuesta. | **Hecho.** Tabla comparable en la sección 7: gana `qwen3:8b`. |
| **2. Oído** | ✅ Silero VAD en lugar del umbral de volumen. ⏳ openWakeWord entrenado con "Nox" (pendiente: sus modelos son solo en inglés). ⏳ Interrumpir a Nox mientras habla. | Mejora la experiencia diaria y baja el uso de CPU, sin tocar el modelo. | Escucha continua que ignora ruidos y oye voces suaves. **Resultado medido: ver sección 7.** |
| **3. Cerebro** ✅ | Adoptar el modelo que gane la fase 1, **solo si gana**. | Ya hay con qué decidir. | **Decidido: se queda `qwen3:8b`** (no hubo cambio). |
| **4. Manos** ✅ | Cliente MCP con lista blanca + Playwright MCP, confirmando lo irreversible. | Es lo que más se parece a un Jarvis, pero exige que la seguridad ya esté medida. | **Hecho.** Nox navega y lee páginas con un navegador real, pidiendo permiso. Ver sección 7.3. |
| **5. Conocimiento** ✅ | Probar Qwen3-Embedding (y re-ranking) con tus consultas; reindexar solo si mejora. | **Prioridad pedida por Brian (2026-10-20):** subió de la 6 a la 5. Requiere coordinar con la bóveda. | **Medido: no hace falta cambiar nada** (sección 7.5). |
| **6. Vista** ✅ | Herramienta "mirar pantalla" con un modelo de visión cargado por turnos. | Bajó de la 5 a la 6. Depende de la fase 3 (qué modelo tenemos). | **Hecho** (sección 7.6): lee el error de una consola, un formulario o una tabla, con permiso cada vez. |
| **7. Memoria** ✅ | Resumen diario, duplicados, olvido inteligente, en `memoria.py`. | Independiente del resto. | **Hecho** (sección 7.7): aprende qué se usa, propone fusionar duplicados y olvidar lo que no sirve, nunca borra solo. |
| **8. Iniciativa** ✅ | Rutinas: resumen de la mañana, recordatorios, avisos. Siempre pidiendo permiso la primera vez. | Es lo que hace sentir que "está ahí"; necesita lo anterior estable. | **Hecho** (sección 7.8): recordatorios y saludo de la mañana (apagado por defecto). |

## 5. Lo que NO conviene hacer

- **Saltar a Qwen3.6 o 3.8** de 27B: no caben en 8 GB, y el 14B ya fue 3 veces más lento.
- **Instalar Mem0 o Letta** esperando que sean "memoria lista": no está confirmado que
  funcionen sin servicios externos, y reemplazarían algo que ya funciona.
- **Conectar servidores MCP sin lista blanca**: rompería la garantía central de Nox.
- **Activar las 25 herramientas de un servidor «por si acaso»**: cada una gasta contexto del modelo y
  amplía lo que puede hacer una página con instrucciones escondidas. Activa solo las que uses.
- **Cambiar de modelo sin la fase 1**: un cambio de modelo puede romper las herramientas
  (el caso de `qwen3.5:9b` lo muestra).

## 7. Resultados medidos (Fases 1 a 8)

### 7.1 Qué modelo conversa mejor — `evaluar_modelo.py`

Equipo: Ryzen 5 5600G · Radeon RX 7600 (8 GB) · 16 GB de RAM · Linux · Ollama 0.40.3 ·
contexto de 8192 · 27 pedidos × 3 repeticiones por modelo (el informe completo está en
[`resultados_modelos/`](resultados_modelos/)). No se ejecutó ninguna herramienta real.

| Modelo | Aciertos | Seguridad | Trampas | Tok/s | Mediana por pedido | En la GPU |
|---|---|---|---|---|---|---|
| **`qwen3:8b`** | **81/81 (100 %)** | 12/12 | 0 | 37,5 | 0,9 s | 100 % (6,2 GB) |
| `qwen3.5:4b` | 76/81 (93,8 %) | 11/12 | 0 | 54,6 | 1,0 s | 100 % (3,3 GB) |
| `qwen3.5:9b` | 63/81 (77,8 %) | 12/12 | 0 | 36,3 | 1,1 s | 100 % (5,7 GB) |
| `qwen3:14b` *(solo 4 pedidos)* | 4/4 | — | — | **4,2** | 10,1 s | **67 %** (10,8 GB) |

**Decisión: Nox se queda con `qwen3:8b`.** Gana en aciertos, no cae en ninguna trampa y
cabe entero en la tarjeta. Por pedido:

- **`qwen3.5:9b` es el peor, y por una razón preocupante.** En acciones (abrir, cerrar,
  pausar, escribir) acertó 18 de 30. Peor: cuando se le preguntó la hora, en vez de usar la
  herramienta **la inventó** ("04:27", "12:06", "13:06") las 3 veces que se le preguntó. Un asistente que
  inventa datos con tanta seguridad no sirve, aunque sea más nuevo.
- **`qwen3.5:4b` es la alternativa si hace falta ligereza**: ocupa la mitad de memoria y es un
  45 % más rápido, a cambio de ~6 puntos de aciertos (las 3 veces que se le pidió crear un documento
  no usó ninguna herramienta, una vez escribió mal el nombre de una, y una no leyó la página).
- **`qwen3:14b` no compensa en 8 GB**: solo el 67 % entra en la GPU y el resto se reparte en la
  RAM; va 9 veces más lento.

**Lo que esta medición NO dice (para no pasarse de confiado):**
- 100 % significa que *esta batería es fácil para este modelo*, no que sea perfecto. Son 27
  casos con respuestas verificables; no miden la calidad de las explicaciones largas.
- Qwen3.5 se probó con **Ollama 0.40.3**; la versión actual es la 0.40.6. Podría comportarse
  mejor con ella (el error de herramientas de `qwen3.5:9b` se reportó y se cerró en marzo).
  Repetir `python evaluar_modelo.py` tras actualizar es barato.
- Solo se midió en *este* equipo. La laptop con RTX 4060 tiene la misma VRAM, así que es
  razonable esperar el mismo reparto, pero las velocidades pueden cambiar. Hay que medir allí.

**Un hallazgo de paso:** la primera medición mostró que Nox decía "no puedo acceder a esa
página" cuando le pasaban un enlace. El prompt no le decía que sí podía. Se corrigió
(`INTERNET:` en `construir_system_prompt`) y ahora lee las páginas. Es el tipo de fallo que
solo aparece al medir. El informe de antes del arreglo se conserva como evidencia.

### 7.2 Qué tan bien oye — `test_voz.py`

Audio **sintético** (la voz de Piper mezclada con ruidos fabricados), comparando el umbral de
volumen anterior contra Silero VAD. Porcentaje de trozos de 100 ms que cada método da por voz:

| Señal | Umbral de volumen (antes) | Silero VAD (ahora) | Correcto |
|---|---|---|---|
| Silencio | 0 % | 0 % | 0 % |
| Ruido blanco | **100 %** | 0 % | 0 % |
| Ventilador (grave) | **100 %** | 0 % | 0 % |
| Teclado | 25 % | 0 % | 0 % |
| Voz normal | 89 % | 95 % | ~95 % |
| Voz muy baja | **9 %** | **93 %** | ~95 % |
| Voz con ruido de fondo | 100 % | 95 % | ~95 % |

El umbral de volumen se activaba con cualquier ruido (gastando CPU en transcribir nada) y no
oía las voces suaves. Con Silero VAD las dos cosas se corrigen, y analizar 100 ms de audio
tarda 0,26 ms.

También se probó dentro del bucle real de la escucha continua, con un micrófono simulado que
entrega 5 s de ventilador, silencio y una frase: con el VAD Whisper transcribe **1 vez** (la
frase) y se entiende la orden; con el umbral de volumen de antes transcribía **2** (la segunda
era el ventilador).

**Límite:** es audio fabricado. Un micrófono real capta eco, soplidos y un cuarto que aquí no
existen. Falta probarlo hablándole a Nox con tu propia voz. Lo que **no** se hizo: entrenar
un detector de "Nox" con openWakeWord (sus modelos ya entrenados son solo en inglés) ni la
interrupción mientras Nox habla.

**Seguimiento — nombres mal escuchados (probado por Brian con su voz):** la voz funcionaba, pero Whisper
escribía «desktop» al oír «Vesktop». Dos causas, dos arreglos (`test_nombres.py`): (1) el vocabulario que se le
da a Whisper estaba lleno de herramientas que casi nadie nombra y cortaba justo antes de «Vesktop»; ahora
prioriza **lo que más usas** (se aprende de lo que abres y cierras) y lo que tienes **abierto ahora**, y quita el
ruido de mantenimiento; (2) si aun así llega mal, Nox acepta el programa que **más se parece** («desktop» →
Vesktop, 0,86) y lo avisa («Entendí «desktop» y supuse que es Vesktop»); si hay dos igual de parecidos,
pregunta, y las palabras sin relación («banana») no coinciden con nada.

### 7.3 Herramientas externas (MCP) — Fase 4

**Qué se construyó:** `mcp_cliente.py` (cliente MCP con lista blanca por herramienta), integrado al
mismo `guardian.py` que las herramientas propias, a `herramientas.py` y al panel de Ajustes.
Detalle de las barreras en el README y la arquitectura.

**Cómo se verificó (de menos a más real):**

| Prueba | Resultado |
|---|---|
| Servidor MCP propio de prueba, por stdio, con 7 herramientas hechas para romper las barreras (lee el entorno, devuelve instrucciones escondidas, es lento, enorme, falla) | Todas las barreras pasan (`test_mcp.py`). |
| El mismo cliente contra el SDK de Python **v1.30.0** y **v2.3.0** | Funciona con las dos. |
| Conexión a **Playwright MCP** real (servidor de terceros) | Se conecta en 3 s, descubre **25 herramientas**, todas bloqueadas por defecto. |
| Navegador real (tu Brave en modo oculto) leyendo una página local | Navega y devuelve su contenido. |
| **Nox completo**: modelo `qwen3:8b` + guardián + MCP + navegador | Pidió permiso para navegar, leyó la página y respondió el dato exacto (`MANZANA-42`). Ante una página con instrucciones escondidas la resumió **sin obedecerlas** (no llamó a `abrir_programa` ni a `escribir_archivo`; no se creó ningún archivo). |
| Medición del modelo tras todos estos cambios (`evaluar_modelo.py`) | `qwen3:8b`: **87/87** con 29 casos; sin regresión. |

**Cuatro problemas reales que solo aparecieron al probar de verdad** (y cómo se resolvieron):

1. **Herramientas sin parámetros.** La v2 del SDK renombró los campos (`input_schema` en vez de
   `inputSchema`); mi primer cliente le habría mostrado al modelo herramientas sin argumentos. Ahora
   lee ambos nombres, con prueba contra las dos versiones.
2. **Un servidor con 25 herramientas, varias peligrosas** (`browser_run_code_unsafe`,
   `browser_evaluate`, `browser_file_upload`). Llevó a la regla de **alto riesgo**: nunca pueden
   quedar en «permitir», ni siquiera editando el archivo a mano.
3. **El modelo inventaba contenido.** Pedido «entra a esta página y dime X», usaba `abrir_web`
   (que solo la muestra en pantalla) y **fabricaba** la respuesta ("PROMO2023", una noticia
   inexistente). Se arregló en tres capas: `abrir_web` ahora avisa que *no* entrega el contenido,
   el prompt prohíbe inventar lo que no se leyó, y el enrutador añade una pista cuando el pedido
   trae un enlace y quiere *leerlo*.
4. **El servidor ensuciaba la carpeta de Nox** (`.playwright-mcp/`). Ahora cada servidor trabaja en
   su propia carpeta.

**Límites (para no pasarse de confiado):**
- Solo se probó en **Linux**. En Windows, `npx` y Playwright no se han probado (el código resuelve
  `npx.cmd` con `shutil.which`, pero no se ha corrido allí).
- El navegador se probó **sin ventana** y con una página local; no con sitios reales, que traen
  banners de cookies, inicios de sesión y contenido dinámico.
- Que el modelo elija bien entre sus herramientas y las externas depende del enrutador y de la
  pista de enlaces: es una heurística, y con otras frases puede fallar. El caso se midió con 2
  pedidos reales, no con una batería amplia.
- El «alto riesgo» se decide por el **nombre** de la herramienta, que lo pone el servidor: es una red
  de seguridad, no una garantía. Lo normal sigue siendo dejar bloqueado todo lo que no se use.
- Un solo servidor de plantilla (Playwright), porque fue el único cuya página oficial y licencia se
  verificaron. Los demás se pueden añadir como «Servidor propio», bajo la misma política.

### 7.4 Interfaz sin tocar código

Ajustes (10 páginas) y asistente de bienvenida (5 pasos), descritos en el README. Verificado con:
`test_ajustes.py` (54 pruebas de la lógica: validación, guardado atómico, clave, detección del equipo
y descarga de modelos con progreso) y `test_interfaz.py` (54 pruebas que construyen las ventanas
**ocultas**, cambian campos como una persona y comprueban que se guarde y se aplique), más capturas
de cada página revisadas a ojo.

**Límites:** se verificó en Linux (KDE). No se ha visto cómo se renderiza en Windows (fuentes,
tamaños). La detección del equipo en Windows usa PowerShell y no se probó allí. El botón «Probar la
voz» y «Descargar modelos» se probaron con simulación, no con una descarga real de varios GB.

### 7.5 Conocimiento (Fase 5, la que se pidió con urgencia) — `evaluar_busqueda.py`

**Pregunta:** ¿vale la pena cambiar `nomic-embed-text` por Qwen3-Embedding, o agregar un re-ranking?

**Cómo se midió:** 70 consultas (47 preguntas habladas y 23 búsquedas por palabras) que un LLM local
escribió a partir de 70 notas distintas de tu bóveda, cada una con su nota correcta conocida. Cada variante
vuelve a calcular los vectores de los 944 fragmentos **en memoria** y busca con la **tubería real de Nox**
(semántica + palabras + penalizaciones). No se tocó tu `RAG/index.db`. Informe completo en
[`resultados_busqueda/`](resultados_busqueda/).

| Variante | Acierta a la 1ª | En las 3 primeras | En las 5 | MRR | Solo semántica (MRR) | ms por consulta |
|---|---|---|---|---|---|---|
| **`nomic` (el actual)** | 79 % | **93 %** | 96 % | 0,857 | 0,781 | 20 |
| `nomic` + prefijos de tarea | 81 % | 91 % | 96 % | 0,870 | 0,838 | 21 |
| `qwen3-embedding:0.6b` | 79 % | 93 % | 96 % | 0,862 | 0,818 | 64 |
| `qwen3-embedding:0.6b` + instrucción | 80 % | 93 % | 96 % | 0,871 | 0,834 | 122 |
| + re-ranking con `qwen3:8b` (8 candidatos) | 80 % | 94 % | 97 % | 0,871 (sin cambio) | — | **+2.400** |

**Conclusión: no cambiar nada.**
- En la tubería real, todas las variantes quedan dentro del ruido (con 70 consultas, una sola mueve 1,4
  puntos). La búsqueda por palabras (BM25) que Nox ya combina con los embeddings cubre lo que un modelo
  mejor aportaría.
- Qwen3-Embedding no gana y es de 3 a 6 veces más lento por consulta. Los modelos de embeddings corren en
  **CPU** en este equipo (así ya funciona hoy `nomic`), y en una tarjeta de 8 GB el de 4B tampoco cabría
  junto al modelo de conversación.
- El re-ranking con `qwen3:8b` no mejora nada y suma 2,4 s por búsqueda. (Los re-rankers dedicados que hay en
  Ollama son subidas de terceros sin garantías: no se instalaron.)
- Los **prefijos de tarea** de `nomic` sí mejoran la búsqueda *solo semántica* (MRR 0,78 → 0,84, gratis), pero
  en la tubería completa la mejora desaparece en el ruido, y aplicarlos exige modificar el indexador de tu
  bóveda y reindexar. No compensa.

**Por qué fallan las pocas que fallan:** 5 de 70 no acertaron en las 3 primeras, y casi todas devuelven una
respuesta **legítima** de otra nota (p. ej. «¿qué tecnología usa el backend de *esta aplicación*?» no dice de
qué aplicación; «etiquetas semánticas» devolvió la nota específica de etiquetas semánticas). La búsqueda ya
está cerca de su techo en esta bóveda.

**Límites:** las preguntas las escribe un modelo y se parecen al texto de origen (favorece a las palabras;
vale para *comparar* variantes, no para saber cuánto aciertas con tus preguntas reales). Son 70 consultas y una
bóveda de 944 fragmentos: si crece mucho, conviene repetir `python evaluar_busqueda.py`.

### 7.6 Vista (Fase 6) — `vista.py`, `evaluar_vista.py`

«Mira mi pantalla y dime qué error es éste». Captura la pantalla o la ventana activa (spectacle en KDE,
PowerShell en Windows), la reduce a 1.280 px y se la muestra a un modelo de visión **local**.

**Modelo elegido: `qwen3.5:4b`** (el mismo que ya viene con visión; 3,3 GB). Medido con 6 imágenes de
prueba generadas (error de consola, tabla, formulario, aviso, letra chica, página con una instrucción
escondida), 2 veces cada una, por el camino real de Nox:

| Modelo | Aciertos | Mediana por pregunta (con carga del modelo) | Memoria | En GPU |
|---|---|---|---|---|
| **`qwen3.5:4b`** | **12/12** | **5,9 s** | 3,3 GB | 100 % |
| `qwen3.5:9b` | 12/12 | 7,8 s | 5,7 GB | 100 % |
| `qwen3-vl:4b` | 7/12 | 7,0 s | 4,2 GB | 100 % |

`qwen3-vl:4b` (el modelo "de visión" de la familia) falló 5 pruebas, varias con respuesta vacía; el `qwen3.5`
de 4B lee igual de bien que el de 9B con la mitad de memoria. Ninguno obedeció la instrucción escondida.

**Barreras** (probadas en `test_vista.py`): viene **apagada**; el modelo no la conoce hasta que se activa en
Ajustes > Vista; pide permiso **cada vez** (se puede quitar a propósito); la imagen solo va a Ollama en esta PC
(a la nube nunca llega); la captura se borra siempre; lo que se ve se marca como información y no como
instrucciones; cuenta para el límite de acciones por turno y queda en la bitácora.

**Límites:** las imágenes de prueba son limpias y generadas; una pantalla real (varias ventanas, letra
antialias, modo oscuro) puede leerse peor. La captura real con spectacle **no se probó con tu pantalla** (a
propósito, por privacidad): solo se probó con simulaciones. En Wayland, spectacle puede pedir permiso la primera
vez. Mientras mira, Nox descarga el modelo de conversación y lo recarga después (unos segundos). En Windows el
script de captura no se ha probado.

### 7.7 Memoria (Fase 7) — `memoria.py`

- **Aprende qué se usa:** cada vez que un recuerdo sirve para responder, se anota (`usos`, `ultimo_uso`). Al
  arrancar, Nox elige lo que ya sabe por **importancia** (tipo, uso y frescura), acotado por largo, en vez de
  por orden de categoría: la memoria ya no se come el contexto del modelo al crecer.
- **Duplicados:** `candidatos_duplicados()` propone pares casi iguales; `fusionar()` deja uno y le suma los usos.
- **Olvido propuesto, no automático:** datos sueltos de más de 90 días que **nunca** se usaron. Las
  preferencias, correcciones y proyectos no caducan solos. Nada se borra sin que lo confirmes (Ajustes > Memoria).
- **Resumen de conversaciones (opcional, apagado):** al cerrar, el modelo local extrae como máximo 3 hechos que
  *contaste* (no lo que respondió Nox) y los guarda como «sesión».
- **Cambio de modelo de embeddings:** si cambia `MODELO_EMBED`, los vectores guardados se recalculan solos.
- Se corrigió un resto de personalización: el encabezado decía «LO QUE YA SABES DE BRIAN» fijo; ahora usa el nombre
  de quien usa Nox.

### 7.8 Iniciativa (Fase 8) — `recordatorios.py`

- **Recordatorios:** «recuérdame llamar a mamá en 20 minutos» / «mañana a las 9» (tres herramientas nuevas:
  `crear_recordatorio`, `listar_recordatorios`, `cancelar_recordatorio`). Cada mensaje lleva la fecha y hora de
  *ahora* para que el modelo pueda calcular «mañana»; la respuesta repite lo programado, para que un error de
  cálculo se note al instante. Se guardan en un archivo, sobreviven a cerrar Nox y avisan al abrirlo si se pasaron.
  Admiten repetición diaria o semanal. Tope de 50 pendientes.
- **Avisos:** la ventana revisa cada 15 s y avisa con un mensaje, por voz y con notificación del escritorio
  (Linux). **Mientras juegas esperan** a que termines.
- **Saludo de la mañana (opcional, APAGADO por defecto):** la primera vez que abres Nox cada día (5:00 a 12:00),
  la fecha y lo que tienes para hoy. Es determinista (sin modelo ni internet). Nox no empieza a hablarte solo
  hasta que lo activas en Ajustes > Iniciativa.
- Nada se programa por iniciativa del modelo: solo lo que pides o activas. No ejecuta nada: solo muestra y dice
  un texto.

**Límites comunes de las fases 7 y 8:** probadas con simulaciones y la hora controlada (`test_memoria.py`,
`test_iniciativa.py`), no esperando días reales. El aviso por voz y las notificaciones no se probaron con tu
micrófono ni tus parlantes. La notificación del escritorio es solo de Linux.

## 8. Laptop con RTX 4060 (8 GB de VRAM, 24 GB de RAM)

Hay un perfil listo: `"equipo": "laptop_rtx4060"` en `config_local.json` (o
`python configurar.py`). **Está sin medir en esa máquina.** Lo que se decidió y por qué:

| Decisión | Motivo |
|---|---|
| Modelo: **`qwen3:8b`** | Misma VRAM (8 GB) que la PC medida, y ahí ocupa 6,2 GB: cabe entero. Un modelo más grande se reparte con la RAM y la velocidad se hunde (el 14B cayó a 4,2 tok/s); los 24 GB de RAM de la laptop no cambian cuánto cabe en la GPU. |
| Contexto: 8192 | El valor con el que se midió. Subirlo agranda la memoria que usa el modelo. |
| Whisper en **CPU** por defecto | Los 8 GB de VRAM ya los usa el modelo de conversación. |
| Opción: Whisper en la GPU NVIDIA | Transcribe mucho más rápido, pero necesita CUDA 12 + cuDNN 9 y quita memoria de video. Se activa con `"whisper_device": "cuda"`; si falla, vuelve solo a la CPU. Pasos en `INSTALACION.md`. |

**Qué hacer cuando la laptop esté a mano** (20 minutos): `python evaluar_modelo.py --modelos
qwen3:8b,qwen3.5:4b,qwen3.5:9b --etiqueta laptop`. El informe dice si la decisión se mantiene y,
si la laptop va muy sobrada, se puede probar `qwen3:14b` ahí: el evaluador lo descarta solo si
no cabe entero en la GPU.

## 9. Límites de esta investigación

- Solo se dieron por buenos los datos de páginas oficiales (biblioteca de Ollama, GitHub de
  cada proyecto, Wikipedia para las fechas de Qwen). Las comparaciones de calidad entre
  modelos que aparecen en blogs **no** se tomaron como prueba.
- Una fuente de terceros afirmaba que el último Qwen abierto era el 3.6; otra, que era el
  3.8. Wikipedia y la biblioteca de Ollama confirman el **3.8** (27B).
- Nada de esto se probó en tu equipo todavía. La fase 1 existe justamente para eso.

## Fuentes

- [Qwen3 en Ollama](https://ollama.com/library/qwen3) · [Qwen3.5](https://ollama.com/library/qwen3.5) · [Qwen3.6](https://ollama.com/library/qwen3.6) · [Búsqueda Qwen en Ollama](https://ollama.com/search?q=qwen)
- [Qwen (Wikipedia)](https://en.wikipedia.org/wiki/Qwen) — fechas y licencias
- [Issue #14745 de Ollama](https://github.com/ollama/ollama/issues/14745) · [Versiones de Ollama](https://github.com/ollama/ollama/releases)
- [openWakeWord](https://github.com/dscripka/openWakeWord) · [Silero VAD](https://github.com/snakers4/silero-vad) · [whisper.cpp](https://github.com/ggml-org/whisper.cpp) · [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [Kokoro](https://github.com/hexgrad/kokoro) · [Piper](https://github.com/OHF-Voice/piper1-gpl)
- [SDK de Python de MCP](https://github.com/modelcontextprotocol/python-sdk) · [Playwright MCP](https://github.com/microsoft/playwright-mcp)
- [Mem0](https://github.com/mem0ai/mem0)
