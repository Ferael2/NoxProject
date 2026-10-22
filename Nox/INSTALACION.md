# Instalar Nox — paso a paso

> Si solo quieres instalarlo y usarlo, la guía corta es [`PASO_A_PASO.md`](PASO_A_PASO.md). Este archivo es la versión con más detalle.

Nox corre en **Linux** y en **Windows 10/11**. Los pasos son los mismos; solo cambia el
instalador. Toma entre 15 y 40 minutos, casi todo descargando modelos.

## Lo que necesitas antes

| Qué | Para qué | Dónde |
|---|---|---|
| **Python 3.12** | Es el lenguaje en el que está escrito Nox. | <https://www.python.org/downloads/> |
| **Ollama** | Corre el modelo de IA en tu propio equipo. | <https://ollama.com/download> |
| ~10 GB libres | Modelos (5,5 GB), voz (63 MB), librerías. | — |
| 8 GB de RAM o más | 16 GB recomendado. | — |
| Un micrófono | Solo si quieres hablarle. Escribirle funciona sin él. | — |

> **Windows:** al instalar Python, marca la casilla **"Add python.exe to PATH"** en la
> primera pantalla. Sin ella el instalador de Nox no encuentra Python.
>
> **Linux:** instala también `tk` y `portaudio` del sistema.
> Arch/CachyOS: `sudo pacman -S tk portaudio` · Debian/Ubuntu: `sudo apt install python3-tk libportaudio2`

## Paso a paso

### 1. Descomprimir
Extrae el `.zip` en una carpeta normal (por ejemplo, Documentos). Hay que **extraerlo**; no
funciona abriéndolo desde dentro del zip. Queda una carpeta `Nox`.

### 2. Correr el instalador

| Sistema | Qué hacer |
|---|---|
| Windows | Doble clic en **`instalar.bat`** |
| Linux | En una terminal, dentro de la carpeta: **`./instalar.sh`** |

El instalador hace, en orden:

1. Crea un entorno de Python propio dentro de la carpeta (`.venv`), para no tocar el Python
   del sistema.
2. Instala las librerías de `requirements.txt`.
3. Descarga la voz de Nox.
4. Arma el catálogo de programas de tu equipo (los que Nox podrá abrir).
5. Si Ollama está instalado, ofrece descargar los modelos (~5,5 GB).
6. Corre `chequeo.py`, que muestra qué está listo y qué falta.

### 3. Los modelos de Ollama
Si no los descargaste en el paso anterior, hazlo ahora (con Ollama ya instalado):

```
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

`qwen3:8b` es el modelo que conversa; `nomic-embed-text` es el que permite buscar por
significado en tus notas y recuerdos.

### 4. Abrir Nox y la primera vez

| Sistema | Cómo |
|---|---|
| Windows | Doble clic en **`Asistente.bat`** |
| Linux | **`./Asistente.sh`** |

Si en Windows no se abre ninguna ventana, usa `Asistente_con_consola.bat`: deja la consola
abierta y ahí se ve el error.

**La primera vez aparece un asistente de bienvenida** que te pregunta, sin tocar ningún
archivo: cómo te llamas, **cómo quieres que Nox se dirija a ti** (tú o usted, un tono, tus
propias instrucciones), qué equipo tienes (lo detecta y te sugiere un perfil) y, si falta algún
modelo de IA, lo descarga con una barra de progreso. Todo se puede cambiar después en el botón
**⚙ Ajustes**.

El `.exe` guarda tus preferencias en `%APPDATA%\Nox\config_local.json`, una carpeta personal
que sigue siendo escribible aunque el programa esté instalado en una ubicación protegida. Si
ya tenías preferencias en `config_local.json` junto al `.exe`, Nox las conserva y las usa; la
próxima vez que guardes desde **Ajustes** quedan en la carpeta personal.

## Elegir el perfil de tu equipo

Nox trae tres perfiles que fijan el modelo de IA, el contexto y dónde corre Whisper. El
asistente de bienvenida te lo sugiere; después se cambia en **Ajustes → Equipo**.

| Perfil | Para qué equipo | Estado |
|---|---|---|
| `estandar_8gb` (por defecto) | Tarjeta de video de 8 GB (AMD o NVIDIA) y 16 GB de RAM | **Medido** en la PC de desarrollo (Radeon RX 7600) |
| `laptop_rtx4060` | Laptop con RTX 4060 (8 GB de VRAM) y 24 GB de RAM | **Sin medir** en esa máquina: ver abajo |
| `basico` | Sin tarjeta dedicada, o con 4 GB | Sin medir |

### Laptop con RTX 4060

1. Instala Ollama y mantén al día el controlador de NVIDIA. Ollama usa la GPU sola.
2. Elige el perfil en el asistente de bienvenida o en **Ajustes → Equipo** (el botón «Detectar mi equipo» lo sugiere solo).
3. **Mide en esa máquina**, porque el perfil parte de los números de otra tarjeta:

   ```
   python evaluar_modelo.py --modelos qwen3:8b,qwen3.5:4b,qwen3.5:9b --etiqueta laptop
   ```

   Deja un informe en `resultados_modelos/` que dice cuál conviene (tarda unos 15–25
   minutos). Con ese resultado elígelo en **Ajustes → Equipo → Modelo de conversación**. Con 24 GB de RAM
   puedes probar también un modelo más grande que se reparta entre la GPU y la RAM (por
   ejemplo `qwen3:14b`), pero en la PC de desarrollo eso resultó 3 veces más lento: mídelo
   antes de adoptarlo. `evaluar_modelo.py` marca como descartado a todo modelo que no entre
   entero en la GPU.
4. **Opcional, Whisper en la GPU** (transcribe mucho más rápido). Solo para tarjetas NVIDIA, y
   le quita memoria de video al modelo de conversación, que ya ocupa casi toda. Según el
   README de faster-whisper necesita CUDA 12 (cuBLAS) y cuDNN 9:
   - Linux: `pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"` en el entorno de Nox, y
     apuntar `LD_LIBRARY_PATH` a esas librerías antes de abrir Nox.
   - Windows: faster-whisper no documenta un método con pip; indica el archivo de
     [whisper-standalone-win](https://github.com/Purfview/whisper-standalone-win), cuyas
     librerías hay que dejar en una carpeta del `PATH`.

   Después elige «cuda» en **Ajustes → Equipo → Voz (avanzado)**. Si algo falla, Nox vuelve
   solo a la CPU y lo avisa en la consola.

## Opcional

- **Cambiar tu nombre, el tono, la bóveda, el modelo, la voz…:** botón **⚙ Ajustes** de Nox. (Sin pantalla: `python configurar.py`.)
- **Nube (OpenRouter):** en **Ajustes → Nube** pega tu clave (se guarda en `openrouter.key`, solo legible por ti). Sirve para preguntas profundas que no tocan datos tuyos. Sin ella, todo se resuelve
  en tu equipo.
- **Equipo modesto:** elige el perfil `basico` (ver arriba).
- **Mirar la pantalla (opcional, apagado):** en **Ajustes → Vista**. En Linux necesita `spectacle` (viene con KDE Plasma) y en Windows usa PowerShell. Necesita el modelo `qwen3.5:4b` (3,3 GB; se descarga desde esa misma página).
- **Herramientas externas (MCP):** para el navegador Playwright hace falta [Node.js](https://nodejs.org). Se activan en **Ajustes → Herramientas externas** (ver el README).
- **LibreOffice** (o Word): para abrir y convertir los `.docx` que Nox crea.

## Si algo falla

| Síntoma | Qué hacer |
|---|---|
| `python` no se reconoce (Windows) | Reinstala Python marcando "Add python.exe to PATH". |
| Falla `tkinter` (Linux) | Instala `tk` / `python3-tk` (ver arriba). |
| Falla al instalar `sounddevice` (Linux) | Instala `portaudio` / `libportaudio2`. |
| "Ollama no responde" | Abre Ollama (Windows: desde el menú Inicio) o corre `ollama serve`. |
| Nox no abre y no sabes por qué | Windows: `Asistente_con_consola.bat`. Linux: `journalctl --user -t nox`. |
| No oye o no habla | Revisa el micrófono del sistema. Sin la voz de Piper usa la del sistema. |
| Cualquier otra cosa | `python chequeo.py` dice qué falta. |

Con el Python del entorno: `.venv/bin/python` en Linux, `.venv\Scripts\python` en Windows.

## Comprobar que todo está bien

```
python probar_todo.py
```

Corre las pruebas de seguridad, privacidad, compatibilidad y nombre de usuario. No necesita
Ollama ni internet.

## Desinstalar

Borra la carpeta `Nox`. Las dos cosas que quedan fuera son la carpeta de trabajo
(`Documentos/Nox`, con los documentos y respaldos que Nox creó) y los modelos de Ollama
(`ollama rm qwen3:8b`).
