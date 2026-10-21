# Nox — Guía paso a paso (para instalarlo y usarlo)

Nox es un asistente personal que corre **en tu propio computador**: conversas con él (escribiendo o
hablando), recuerda lo que le cuentas, te avisa de tus recordatorios, abre programas, busca en tus notas
y puede mirar tu pantalla si tú se lo permites. Casi todo ocurre en tu equipo, sin mandar tus cosas a
internet.

> **Aviso honesto:** Nox se desarrolló y probó en **Linux**. La versión de **Windows** está hecha y
> pasa sus pruebas simuladas, pero **nadie la ha probado todavía en un Windows real**: tú serás de
> los primeros. Si algo falla, no te frustres: al final hay una sección de "Qué mandar si algo falla".

---

## 1. Lo que necesitas

| Qué | Recomendado | Mínimo |
|---|---|---|
| Sistema | Windows 10/11 (o Linux) | — |
| Memoria RAM | 16 GB | 8 GB (perfil "Básico") |
| Tarjeta de video | NVIDIA o AMD con **8 GB** de memoria de video | Sin tarjeta dedicada (más lento) |
| Espacio en disco | 12 GB libres | 8 GB |
| Internet | Solo para instalar y descargar los modelos | — |
| Micrófono | Solo si quieres hablarle (escribirle siempre funciona) | — |

---

## 2. Instalar los dos programas que Nox necesita

### 2.1. Python 3.12
1. Ve a <https://www.python.org/downloads/> y descarga **Python 3.12**.
2. Abre el instalador y, **en la primera pantalla, marca la casilla "Add python.exe to PATH"**.
   Sin esa casilla, el instalador de Nox no encuentra Python.
3. Pulsa "Install Now".

### 2.2. Ollama (el programa que corre la inteligencia artificial)
1. Ve a <https://ollama.com/download> y descarga la versión de Windows.
2. Instálalo (siguiente, siguiente, finalizar). Queda funcionando en segundo plano.

---

## 3. Descomprimir Nox

1. Recibirás un archivo llamado **`Nox_para_compartir.zip`**.
2. Haz clic derecho → **"Extraer todo…"** y elige una carpeta normal, por ejemplo `Documentos`.
   *(Hay que extraerlo: no funciona abriéndolo desde dentro del zip.)*
3. Queda una carpeta **`Nox`**. Ábrela.

---

## 4. Instalar Nox (un solo doble clic)

1. Dentro de la carpeta `Nox`, haz **doble clic en `instalar.bat`**.
2. Se abre una ventana negra. Déjala trabajar (**entre 10 y 30 minutos**). Hace esto, en orden:
   1. Crea un entorno de Python propio dentro de la carpeta (no toca tu Python).
   2. Instala las librerías que Nox necesita.
   3. Descarga la voz de Nox (unos 63 MB).
   4. Arma la lista de programas de tu equipo (los que Nox podrá abrir).
   5. Si Ollama está instalado, te pregunta: **"Descargar los modelos de Ollama ahora (unos 5.5 GB)? [s/N]"**.
      Escribe **`s`** y pulsa Enter.
   6. Corre una revisión final y te dice qué está listo y qué falta.
3. Al final dice **"Nox esta listo"**. Pulsa una tecla para cerrar.

**Si dijiste que no a los modelos**, descárgalos luego abriendo una ventana de comandos (tecla Windows,
escribe `cmd`, Enter) y ejecutando:

```
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

`qwen3:8b` es el cerebro (5,2 GB) y `nomic-embed-text` permite buscar por significado en tus notas
y recuerdos (274 MB). Son **los únicos dos obligatorios**.

---

## 5. Abrir Nox por primera vez

1. Haz **doble clic en `Asistente.bat`**.
2. La primera vez aparece un **asistente de bienvenida** de 5 pasos:
   1. **Cómo te llamas.**
   2. **Cómo quieres que Nox se dirija a ti:** tú o usted, un tono (natural, cercano, al grano, formal,
      detallado) y, si quieres, tus propias instrucciones ("sé breve", "explícame con ejemplos").
   3. **Tu equipo:** Nox detecta tu tarjeta de video y te sugiere un perfil. Si falta algún modelo de IA,
      aquí puedes descargarlo con una barra de progreso.
   4. **Voz y privacidad:** si Nox responde en voz alta y si puede usar internet para preguntas generales.
   5. **Resumen** de lo que elegiste.
3. Pulsa **Empezar**. Todo lo que elegiste se puede cambiar después en el botón **⚙ Ajustes**.

### Qué puedes probar para ver que funciona

| Escríbele (o dile) | Qué debería pasar |
|---|---|
| "Hola, ¿cómo estás?" | Te responde con el nombre y el tono que elegiste. |
| "¿Qué hora es?" | Te dice la fecha y la hora. |
| "Abre la calculadora" | Abre la calculadora de tu equipo. |
| "Recuérdame llamar a mi mamá en 2 minutos" | Confirma lo programado y te avisa a los 2 minutos. |
| "Recuerda que mi comida favorita es la pizza" | Lo guarda. En otra conversación, pregúntale: "¿cuál es mi comida favorita?". |
| "Sube el volumen" | Sube el volumen del equipo. |
| "Busca en internet cuántos habitantes tiene Chile" | Busca y te resume lo que encontró. |

Para **hablarle**: pulsa **"Hablar"**, di tu frase y pulsa **"Detener"**. O activa el interruptor
**"Escuchar «Nox»"** y di, por ejemplo, *"Nox, abre Steam"*.

---

## 6. Cosas opcionales (todo se activa en ⚙ Ajustes)

| Quiero… | Dónde | Qué hay que hacer |
|---|---|---|
| **Usar la nube para preguntas difíciles** | Ajustes → Nube | Crea una cuenta gratis en <https://openrouter.ai>, copia tu clave (empieza con `sk-or-`) y pégala. Tus notas y tu memoria **nunca** van a la nube. Sin clave, todo se responde en tu equipo. |
| **Conectar mis notas de Obsidian** | Ajustes → Bóveda | Elige la carpeta de tu bóveda. Es opcional. |
| **Que Nox mire mi pantalla** | Ajustes → Vista | Actívalo (viene apagado) y pulsa **Descargar** para bajar el modelo `qwen3.5:4b` (3,3 GB). Te pide permiso cada vez que va a mirar. |
| **Que Nox navegue por internet por mí** | Ajustes → Herramientas externas | Instala antes **Node.js** (<https://nodejs.org>). Pulsa "+ Navegador web (Playwright)", actívalo y luego "Aplicar la selección recomendada". Cada acción te pide permiso. Necesita un navegador instalado (se probó con uno basado en Chromium; **Chrome** es lo más probable que funcione). Si no abre, avísame: es de lo menos probado en Windows. |
| **Un saludo de buenos días con mis pendientes** | Ajustes → Iniciativa | Activa "Darme los buenos días con un resumen" (viene apagado). |
| **Que Nox guarde un resumen de mis conversaciones** | Ajustes → Memoria | Actívalo (viene apagado). Se guarda solo en tu equipo. |
| **Abrir y convertir documentos .docx** | — | Instala LibreOffice (o ten Word). |
| **Un equipo con poca memoria** | Ajustes → Equipo | Elige el perfil **"Básico"** (usa un modelo más chico, `qwen3:4b`). |

---

## 7. Comprobar que todo está bien

Abre una ventana de comandos **dentro de la carpeta `Nox`** (en el Explorador, clic en la barra de
direcciones, escribe `cmd` y Enter) y ejecuta:

```
.venv\Scripts\python chequeo.py
```

Te dice, con ✓ y ✗, si Ollama, los modelos, la voz y lo demás están listos.

Para correr **todas las pruebas** (tarda unos minutos, no necesita internet):

```
.venv\Scripts\python probar_todo.py
```

Al final debe decir **"TODO EN ORDEN"**. Si una falla, es útil para saber qué parte no funciona en tu Windows.

---

## 8. Si algo no funciona

| Síntoma | Qué hacer |
|---|---|
| "`python` no se reconoce" al instalar | Reinstala Python marcando **"Add python.exe to PATH"**. |
| `instalar.bat` falla instalando librerías | Copia el mensaje de error (ver sección 9). |
| Nox no abre y no sale ninguna ventana | Usa **`Asistente_con_consola.bat`**: deja la consola abierta y ahí se ve el error. |
| "Ollama no responde" | Abre Ollama desde el menú Inicio, o ejecuta `ollama serve`. |
| Dice que falta un modelo | `ollama pull qwen3:8b` y `ollama pull nomic-embed-text`. |
| Responde muy lento | Elige el perfil "Básico" en Ajustes → Equipo, o cierra juegos y programas pesados. |
| Nox no te oye o entiende mal | Prueba `.venv\Scripts\python diagnostico_voz.py`: te hace hablar y mide cada etapa (micrófono, detector de voz, reconocimiento). Revisa que el micrófono correcto esté elegido en la configuración de sonido de Windows. |
| Entiende mal un nombre de programa | Normal con nombres raros. Nox aprende de lo que abres y cierras, y si algo se parece mucho, lo asume y te lo dice. |
| No suena la voz natural | Usa la voz de Windows como respaldo. Comprueba que `voces\es_MX-claude-high.onnx` exista. |

---

## 9. Qué mandar si algo falla

Para poder ayudarte rápido, manda estas **tres cosas**:

1. Una captura o texto de lo que sale al ejecutar `.venv\Scripts\python chequeo.py`.
2. El mensaje de error de `Asistente_con_consola.bat` (se queda abierto).
3. Tu versión de Windows y cuánta RAM y qué tarjeta de video tienes.

---

## 10. Cosas buenas de saber

- **Es privado.** Lo que le cuentas se guarda en tu equipo (en `Documentos\Nox`). La nube solo recibe
  preguntas generales, y solo si activas esa opción y pones tu clave.
- **Tiene límites a propósito.** Nox **no puede borrar archivos**, no instala ni desinstala programas, no
  escribe archivos ejecutables y solo escribe en Documentos, el Escritorio y su propia carpeta. Antes de
  cerrar un programa te pregunta. Las cosas delicadas (mirar la pantalla, usar herramientas externas)
  vienen **apagadas** y piden permiso.
- **Para desinstalar:** borra la carpeta `Nox`. Quedan aparte `Documentos\Nox` (lo que Nox creó) y los
  modelos de Ollama (`ollama rm qwen3:8b`).

---

## 11. Resumen de comandos (por si los necesitas)

Todos se ejecutan **dentro de la carpeta `Nox`**.

| Para… | Windows | Linux |
|---|---|---|
| Instalar | doble clic en `instalar.bat` | `./instalar.sh` |
| Abrir Nox | doble clic en `Asistente.bat` | `./Asistente.sh` |
| Abrir viendo errores | `Asistente_con_consola.bat` | `.venv/bin/python gui.py` |
| Revisar que todo esté listo | `.venv\Scripts\python chequeo.py` | `.venv/bin/python chequeo.py` |
| Correr todas las pruebas | `.venv\Scripts\python probar_todo.py` | `.venv/bin/python probar_todo.py` |
| Probar la voz | `.venv\Scripts\python diagnostico_voz.py` | `.venv/bin/python diagnostico_voz.py` |
| Cambiar nombre, tono, equipo… | botón **⚙ Ajustes** dentro de Nox | igual |
| Modelos obligatorios | `ollama pull qwen3:8b` y `ollama pull nomic-embed-text` | igual |
| Modelo de visión (opcional) | `ollama pull qwen3.5:4b` | igual |

### Si usas Linux
Antes de `./instalar.sh` instala `tk` y `portaudio` (el instalador te dice el comando exacto si faltan):

- Arch / CachyOS: `sudo pacman -S tk portaudio`
- Debian / Ubuntu: `sudo apt install python3-tk libportaudio2`

Para que Nox pueda mirar la pantalla en KDE hace falta `spectacle` (ya viene con Plasma).

---

*Más detalle técnico: `INSTALACION.md` (instalación), `README.md` (qué hace y sus límites de seguridad),
`ARQUITECTURA.md` (cómo está hecho) y `HOJA_DE_RUTA.md` (lo medido y lo que falta).*
