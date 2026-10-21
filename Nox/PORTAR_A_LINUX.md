# Portar Nox a CachyOS — plan por etapas

> **Actualización 2026-10-20:** el código ya no es solo de Linux: corre en Linux **y** en
> Windows (`plataforma.py`, `so_linux.py`, `so_windows.py`). Este documento queda como
> historia del port a Linux; la compatibilidad actual está en el README. Ya no se calcula
> `BOVEDA` relativa al archivo: ahora sale de `config_local.json` (ver `config.py`).

Revisión hecha el 2026-10-03.

**Estado:** TODAS las etapas hechas. 0-2 el 2026-10-03; 3-7 el 2026-10-15.
test_seguridad, test_barreras y test_privacidad pasan completos, y chequeo.py da todo OK.
Copia de la version de Windows: `~/claude_obsidian/asistente_antes_linux_2026-10-15/`.

Lo que quedo distinto al plan original:
- Cerrar programas: en vez de `kill`, KWin por D-Bus (`/WindowsRunner`, accion 1 = cerrar),
  que equivale a la X. `kill` solo con forzar=true (SIGTERM, y SIGKILL a los 3 s).
- Multimedia: atajos de Plasma via kglobalaccel (`kmix`, `mediacontrol`) en vez de
  playerctl; wpctl/playerctl quedan de respaldo.
- `consultar_sistema` (era PowerShell) paso a lista blanca de comandos de Linux sin shell.
- Ventana con clase propia (`Nox`), icono `icono.svg`/`icono.png`, lanzador en
  `~/.local/share/applications/nox.desktop`.

Instalados el 2026-10-15: `libreoffice-fresh` (+ `-es`), `espeak-ng`, `playerctl`. Los
.docx abren en Writer, la conversion a PDF funciona y el catalogo incluye LibreOffice.

Cada etapa es pequeña y se puede probar antes de pasar a la siguiente. Tras cualquier cambio en permisos: correr `test_seguridad.py` y
`test_barreras.py`.

## Etapa 0 — Entorno (requiere sudo una vez)
- Falta la librería de Tk del sistema (customtkinter la necesita):
  `sudo pacman -S tk` (y para la voz: `portaudio`, que usa sounddevice).
- Venv propio: `python -m venv ~/.venvs/nox` e instalar solo lo que pida cada módulo:
  `customtkinter ddgs beautifulsoup4 requests numpy` (y más adelante `sounddevice
  faster-whisper piper-tts` para la voz).

## Etapa 1 — Rutas (`config.py`)
- `BOVEDA` apunta a `C:\Users\USUARIO\Desktop\claude_obsidian\Claude` → calcularla relativa al
  propio archivo (`Path(__file__).resolve().parent.parent / "Claude"`), así no se rompe si la
  carpeta se mueve.
- `CARPETA_TRABAJO = Path.home() / "Documents" / "Nox"`: en este sistema la carpeta se llama
  `Documentos` (ver `xdg-user-dir DOCUMENTS`).
- Revisar la lista de carpetas permitidas (`Desktop`, `Documents`…) con los nombres en
  español de Linux (`Escritorio`, `Documentos`, `Descargas`).

## Etapa 2 — Seguridad (`seguridad.py`) — revisar con calma
- Las listas negras de rutas sensibles son de Windows (`appdata\local\microsoft\credentials`).
  En Linux los equivalentes son `~/.ssh`, `~/.gnupg`, `~/.local/share/keyrings`,
  `~/.claude/.credentials.json`, `~/.mozilla`, `~/.config/BraveSoftware`, `/etc`, etc.
- La comparación con `Path.is_relative_to` ya es correcta en Linux; ojo con que Linux
  distingue mayúsculas/minúsculas.
- Ejecutables prohibidos: además de `.exe/.bat/.ps1`, en Linux importa el bit de ejecución y
  `.sh`/`.desktop`.
- Lista de procesos protegidos (`explorer`, `csrss`, `lsass`…): pasar a los de Linux
  (`kwin_wayland`, `plasmashell`, `systemd`, `ollama`, `python`…).

## Etapa 3 — Abrir programas (`sistema.py`, `escanear_programas.py`, `programas.json`)
- Ojo: en Linux `ps`/`/proc/<pid>/comm` recorta los nombres a 15 caracteres
  (`org_kde_powerde`). Comparar contra `INTOCABLES` con el nombre completo (psutil).
- `programas.json` tiene 139 entradas con accesos `.lnk` de Windows → regenerarlo leyendo los
  `.desktop` de `/usr/share/applications` y `~/.local/share/applications`.
- Juegos de Steam: en vez de `winreg`, leer `~/.local/share/Steam/steamapps/libraryfolders.vdf`
  y abrir con `steam steam://rungameid/<appid>`.
- `os.startfile(...)` → `subprocess.Popen(["xdg-open", ruta])` o `gtk-launch <app>.desktop`.
- `procesos_visibles()` / `cerrar_programa()` usan comandos de Windows → `ps`/`psutil` y
  `kill`/`pkill`.
- Control multimedia (volumen, pausa, siguiente) → `playerctl` y `wpctl` (PipeWire).

## Etapa 4 — Documentos (`documentos.py`)
- Buscar `soffice` en el PATH (`shutil.which("soffice")`) en vez de `C:\Program Files\...`
  (LibreOffice: `sudo pacman -S libreoffice-fresh` si hace falta).

## Etapa 5 — Voz (`voz.py`)
- `pyttsx3` usa SAPI5 (solo Windows) como respaldo → en Linux usar solo Piper
  (`voces/es_MX-claude-high.onnx` ya está) o `espeak-ng` como respaldo.
- Whisper (faster-whisper) y sounddevice funcionan en Linux con `portaudio`.

## Etapa 6 — Lanzador y empaquetado
- `Asistente.bat` → `Asistente.sh`:
  `cd "$(dirname "$0")" && exec ~/.venvs/nox/bin/python gui.py`
  más un `.desktop` en `~/.local/share/applications` para tenerlo en el menú y el dock.
- PyInstaller: `Asistente.spec` incluye `pyttsx3.drivers.sapi5` y `comtypes` (Windows) →
  quitarlos. En Linux el ejecutable congelado aporta poco; el lanzador `.sh` toma los cambios
  del código sin recompilar, igual que hacía el `.bat`.

## Etapa 7 — Textos de las herramientas (`herramientas.py`)
- Descripciones con ejemplos `C:\Users\USUARIO\...` y `Documentos\Nox` → ejemplos con rutas
  de Linux, para que el modelo no proponga rutas de Windows.
