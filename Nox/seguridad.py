"""
Validaciones de seguridad. Todo lo que decide "esto se puede o no se puede" vive aca,
en un solo archivo, para que se pueda auditar de una sola lectura.

Principios:

1. LISTA BLANCA POR DEFECTO. Lo que no esta explicitamente permitido, se rechaza.
   Una lista negra siempre tiene agujeros: basta una forma de escribirlo que no
   este contemplada.

2. COMPARAR RUTAS COMO RUTAS, NO COMO TEXTO. `str(ruta).startswith(carpeta)` es un
   bug clasico: "/home/arkanis/Escritorio" tambien hace match con
   "/home/arkanis/EscritorioMalicioso". Se usa Path.is_relative_to sobre rutas ya
   resueltas (que ademas siguen symlinks, cerrando esa via de escape).

3. NADA DE ENCADENAR. Un comando de consulta que puede encadenar otro comando ya no
   es un comando de consulta.
"""
import sys
import unicodedata
from pathlib import Path

import plataforma

if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")


class Rechazado(Exception):
    """La operacion no esta permitida. El mensaje explica por que."""


# --- Rutas ---

def resolver(ruta) -> Path:
    """
    Ruta absoluta y real: resuelve '..', symlinks y junctions.
    strict=False permite validar archivos que todavia no existen (los que se van a crear).
    """
    return Path(ruta).expanduser().resolve(strict=False)


def dentro_de(destino, carpetas_permitidas) -> bool:
    """
    True si 'destino' esta dentro de alguna carpeta permitida.
    Compara rutas resueltas con is_relative_to, no texto con startswith.
    """
    destino = resolver(destino)
    for carpeta in carpetas_permitidas:
        try:
            if destino.is_relative_to(resolver(carpeta)):
                return True
        except (OSError, ValueError):
            continue
    return False


# Rutas que nunca se leen ni se escriben, aunque cayeran dentro de una carpeta permitida.
# Son secretos o cosas del sistema: no hay caso de uso legitimo para el asistente.

# Bloquea si el texto aparece en cualquier parte de la ruta.
FRAGMENTOS_PROHIBIDOS = (
    ".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker",
    "credentials", "id_rsa", "id_ed25519", ".pem", ".pfx", ".key",
    "ntuser.dat", "system32", "syswow64",
    "appdata\\local\\microsoft\\credentials",
    "appdata\\roaming\\microsoft\\credentials",
    "login data", "cookies.sqlite", "key4.db", "logins.json",
    ".env", "secrets", "password", "passwd", "token",
)

# Bloquea solo si una carpeta o archivo de la ruta se llama EXACTAMENTE asi.
# Como fragmento, "security" bloqueaba notas como "Spring Security.md".
NOMBRES_PROHIBIDOS = frozenset({
    "sam", "security",                             # registro de Windows
    "shadow", "gshadow", "sudoers",                # contraseñas y permisos de Linux
    "cookies",                                     # cookies de Chrome/Brave (archivo sin extension)
    "bravesoftware", "google-chrome", "chromium",  # perfiles de navegador completos
    "kwalletd", "keyrings",                        # llaveros de KDE y GNOME
    "environ",                                     # /proc/<pid>/environ: variables con claves
})


def es_sensible(ruta) -> bool:
    """True si la ruta parece contener credenciales o cosas del sistema."""
    destino = resolver(ruta)
    texto = str(destino).lower()
    if any(f in texto for f in FRAGMENTOS_PROHIBIDOS):
        return True
    return any(parte.lower() in NOMBRES_PROHIBIDOS for parte in destino.parts)


def validar_lectura(ruta, carpetas_permitidas=None) -> Path:
    """
    Valida que un archivo se pueda leer. Lanza Rechazado si no.

    `carpetas_permitidas=None` significa acceso amplio (cualquier disco). Aun asi se
    bloquean credenciales, salvo que se apague explicitamente en config.
    """
    import config

    destino = resolver(ruta)

    if getattr(config, "BLOQUEAR_ARCHIVOS_SENSIBLES", True) and es_sensible(destino):
        raise Rechazado(
            "Esa ruta parece contener credenciales o archivos del sistema. No la leo. "
            "(Se desactiva con BLOQUEAR_ARCHIVOS_SENSIBLES=False en config.py)"
        )
    if carpetas_permitidas and not dentro_de(destino, carpetas_permitidas):
        permitidas = ", ".join(str(c) for c in carpetas_permitidas)
        raise Rechazado(f"Solo puedo leer dentro de: {permitidas}")
    if not destino.exists():
        raise Rechazado(f"No existe: {destino}")
    if not destino.is_file():
        raise Rechazado(f"No es un archivo: {destino}")

    return destino


def validar_escritura(ruta, carpetas_permitidas, extensiones_permitidas) -> Path:
    """Valida que un archivo se pueda escribir. Lanza Rechazado si no."""
    destino = resolver(ruta)

    if destino.suffix.lower() not in extensiones_permitidas:
        extension = destino.suffix or "(sin extension)"
        raise Rechazado(
            f"No escribo archivos '{extension}'. "
            f"Permitidas: {', '.join(sorted(extensiones_permitidas))}"
        )
    if es_sensible(destino):
        raise Rechazado("Esa ruta esta protegida. No escribo ahi.")
    import config
    if dentro_de(destino, [config.CARPETA_PROYECTO]):
        raise Rechazado("Esa es mi propia carpeta de programa. No escribo ahi.")
    if not dentro_de(destino, carpetas_permitidas):
        permitidas = ", ".join(str(c) for c in carpetas_permitidas)
        raise Rechazado(f"Solo puedo escribir dentro de: {permitidas}")

    # Si ya existe y es un enlace, alguien podria estar redirigiendo la escritura afuera.
    if destino.is_symlink():
        raise Rechazado("El destino es un enlace simbolico. No escribo ahi.")

    return destino


# --- URLs ---

ESQUEMAS_PERMITIDOS = ("http", "https")


def validar_url(url: str) -> str:
    """
    Solo http y https. Bloquea file://, javascript:, data:, y demas esquemas que
    podrian leer archivos locales o ejecutar codigo en el navegador.
    """
    from urllib.parse import urlparse

    limpio = url.strip()
    partes = urlparse(limpio)

    if partes.scheme.lower() not in ESQUEMAS_PERMITIDOS:
        raise Rechazado(
            f"Solo abro enlaces http o https, no '{partes.scheme or 'sin esquema'}'."
        )
    if not partes.netloc:
        raise Rechazado("Esa URL no tiene un dominio valido.")

    return limpio


# --- Comandos de consulta ---
#
# Hay un validador por sistema: el de Linux (este bloque) y el de PowerShell (mas abajo).
# Los dos viven aca y se pueden probar desde cualquiera de los dos sistemas;
# validar_comando_consulta elige el que corresponde.
#
# --- Linux ---
#
# No se usa una shell: el comando se parte con shlex y cada tramo del pipeline corre
# como un proceso aparte, con sus argumentos tal cual. Asi ';', '&&', '$()' o '>' no
# tienen ningun efecto especial... y aun asi se rechazan, para que el modelo reciba un
# "no" claro en vez de un error raro.

# Lista blanca de programas. Ninguno modifica nada por si solo; los que tienen opciones
# que si modifican (sort -o escribe un archivo, systemctl stop, ollama rm...) se
# revisan uno por uno en _revisar_tramo.
COMANDOS_CONSULTA = frozenset({
    # estado del equipo
    "uptime", "uname", "whoami", "id", "hostname", "nproc", "date", "free", "df",
    "lsblk", "findmnt", "lscpu", "lspci", "lsusb", "sensors", "ps", "which",
    # archivos: listar, medir, y leer lo que no sea sensible
    "ls", "du", "stat", "file", "wc", "cat", "head", "tail",
    # filtros para pipelines
    "grep", "sort", "uniq", "cut", "tr",
    # servicios, paquetes, red y modelos
    "systemctl", "journalctl", "pacman", "ip", "ss", "ollama",
})

# De donde se toman los programas. No se usa el PATH completo a proposito: incluye
# ~/.local/bin, y un "ls" falso puesto ahi se ejecutaria en lugar del real.
RUTAS_DE_COMANDOS = "/usr/bin:/bin:/usr/sbin:/usr/local/bin"

MAX_TRAMOS = 4

# Opciones cortas prohibidas, letra por letra: asi tambien se atrapan combinadas
# ("grep -rn" lleva la r de recursivo adentro).
LETRAS_PROHIBIDAS = {
    "sort": "o",         # -o ARCHIVO escribe la salida en un archivo
    "grep": "rRd",       # recorrer carpetas enteras podria leer credenciales
    "tail": "fF",        # -f se queda esperando para siempre
    "journalctl": "f",
    "ss": "KF",          # -K corta conexiones; -F lee filtros de un archivo
    "sensors": "s",      # -s cambia la configuracion de los sensores
    "file": "C",         # -C compila y escribe un archivo de firmas
    "systemctl": "H",    # -H se conecta a otra maquina por SSH
}

# Opciones largas prohibidas (por prefijo: "--vacuum" cubre --vacuum-size y demas).
LARGAS_PROHIBIDAS = {
    "sort": ("--output",),
    "grep": ("--recursive", "--dereference-recursive", "--directories"),
    "tail": ("--follow",),
    "journalctl": (
        "--follow", "--vacuum", "--rotate", "--flush", "--sync", "--relinquish-var",
        "--smart-relinquish-var", "--setup-keys", "--update-catalog", "--cursor-file",
    ),
    "ss": ("--kill", "--filter"),
    "sensors": ("--set",),
    "file": ("--compile",),
    "systemctl": ("--host",),
    "date": ("--set", "--file"),
    "hostname": ("--file", "--boot"),
}

# systemctl y ollama mezclan consultas con acciones en el mismo comando: se permite
# solo el verbo, nunca "stop", "disable", "rm", "run"...
VERBOS_SYSTEMCTL = frozenset({
    "status", "list-units", "list-timers", "list-unit-files", "list-sockets",
    "is-active", "is-enabled", "is-failed", "show", "cat",
})
VERBOS_OLLAMA = frozenset({"ps", "list", "ls", "show", "--version", "-v"})

# ip: que se puede mirar y con que verbo. Cualquier otro (add, del, set, flush) cambia
# la red.
OBJETOS_IP = frozenset({
    "addr", "address", "a", "link", "l", "route", "r", "ro", "neigh", "neighbour", "n",
})
VERBOS_IP = frozenset({"show", "sh", "list", "ls", "lst", "get"})
OPCIONES_IP = frozenset({
    "-4", "-6", "-br", "-brief", "-c", "-color", "-s", "-stats", "-statistics",
    "-j", "-json", "-p", "-pretty", "-d", "-details", "-o", "-oneline", "-h", "-human",
})

# ps: las opciones que llevan valor. Su valor ("-C brave") no es una opcion BSD.
OPCIONES_PS_CON_VALOR = frozenset({
    "-o", "-O", "-p", "-q", "-u", "-U", "-C", "-G", "-g", "-t", "--sort", "--pid",
    "--ppid", "--user", "--format",
})

# Leer un archivo enorme entero (una ISO, un video) llenaria la memoria por nada.
MAX_MB_LECTURA = 20
LEEN_ARCHIVOS_ENTEROS = frozenset({"cat", "grep", "sort", "uniq", "cut"})


def _partir(comando: str) -> list[list[str]]:
    """Parte el comando en tramos de pipeline, respetando las comillas."""
    import shlex

    lexer = shlex.shlex(comando, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError as e:  # comillas sin cerrar
        raise Rechazado(f"No entiendo el comando: {e}")

    tramos, actual = [], []
    for token in tokens:
        if token == "|":
            tramos.append(actual)
            actual = []
        elif token and set(token) <= set("();<>|&"):
            raise Rechazado(
                f"Rechazado: contiene '{token}'. Solo acepto consultas simples, "
                "como mucho unidas con '|'. Para abrir programas usa abrir_programa; "
                "para escribir archivos, escribir_archivo."
            )
        elif "`" in token or "$(" in token:
            raise Rechazado("Rechazado: no acepto sustituciones de comandos.")
        else:
            actual.append(token)
    tramos.append(actual)
    return tramos


def _revisar_ruta(arg: str, programa: str):
    """Rechaza argumentos que apunten a credenciales, a /dev o a archivos gigantes."""
    import os

    ruta = Path(os.path.expanduser(arg))
    if not ruta.is_absolute():
        ruta = Path.home() / ruta  # los comandos corren parados en la carpeta personal
    ruta = resolver(ruta)

    if es_sensible(ruta):
        raise Rechazado(f"Rechazado: '{arg}' parece contener credenciales. No lo toco.")
    if ruta.is_relative_to("/dev") and ruta != Path("/dev/null"):
        raise Rechazado("Rechazado: no leo dispositivos (/dev).")
    if programa in LEEN_ARCHIVOS_ENTEROS:
        try:
            if ruta.is_file() and ruta.stat().st_size > MAX_MB_LECTURA * 1024 * 1024:
                raise Rechazado(
                    f"'{arg}' pesa mas de {MAX_MB_LECTURA} MB. Usa head o tail para ver "
                    "una parte."
                )
        except OSError:
            pass


def _revisar_tramo(tramo: list[str]) -> list[str]:
    """Valida un tramo y devuelve el argv listo para ejecutar (con ruta absoluta)."""
    import os
    import shutil

    if not tramo:
        raise Rechazado("Hay un tramo vacio en el pipeline.")

    programa, args = tramo[0], tramo[1:]
    if programa not in COMANDOS_CONSULTA:
        raise Rechazado(
            f"Rechazado: '{programa}' no esta en la lista de comandos de consulta "
            "permitidos."
        )

    cortas = [a for a in args if a.startswith("-") and not a.startswith("--") and len(a) > 1]
    largas = [a for a in args if a.startswith("--")]

    for a in cortas:
        for letra in LETRAS_PROHIBIDAS.get(programa, ""):
            if letra in a[1:]:
                raise Rechazado(f"Rechazado: '{programa} -{letra}' puede modificar algo o colgarse.")
    for a in largas:
        if a.startswith(LARGAS_PROHIBIDAS.get(programa, ())):
            raise Rechazado(f"Rechazado: '{programa} {a.split('=')[0]}' no es de consulta.")

    posicionales = [a for a in args if not a.startswith("-")]

    if programa == "systemctl":
        verbo = posicionales[0] if posicionales else "list-units"
        if verbo not in VERBOS_SYSTEMCTL:
            raise Rechazado(f"Rechazado: 'systemctl {verbo}' cambia algo. Solo consultas (status, list-units...).")
        args = ["--no-pager"] + args

    elif programa == "journalctl":
        if not any(a in ("-n", "--lines") or a.startswith(("-n", "--lines=")) for a in args):
            args = ["-n", "300"] + args  # sin limite, el diario entero son cientos de MB
        args = ["--no-pager"] + args

    elif programa == "ollama":
        if not args or args[0] not in VERBOS_OLLAMA:
            raise Rechazado("Rechazado: de ollama solo consulto 'ps', 'list' y 'show'.")

    elif programa == "pacman":
        if not args or not (args[0] == "--query" or (args[0].startswith("-Q") and args[0][1:].isalpha())):
            raise Rechazado("Rechazado: de pacman solo consulto lo instalado (-Q...).")
        for a in args[1:]:
            if (a.startswith("-") and not a.startswith("--") and any(c in "SRUDFT" for c in a[1:])) \
                    or a.startswith(("--sync", "--remove", "--upgrade", "--database", "--files")):
                raise Rechazado("Rechazado: pacman solo para consultar, no para instalar ni quitar.")

    elif programa == "ip":
        i = 0
        while i < len(args) and args[i].startswith("-"):
            if args[i] not in OPCIONES_IP:
                raise Rechazado(f"Rechazado: 'ip {args[i]}' no esta permitido.")
            i += 1
        if i < len(args):
            if args[i] not in OBJETOS_IP:
                raise Rechazado(f"Rechazado: 'ip {args[i]}' no esta permitido.")
            resto = args[i + 1:]
            if resto and resto[0] not in VERBOS_IP:
                raise Rechazado(f"Rechazado: 'ip ... {resto[0]}' cambia la red.")

    elif programa == "date":
        for previo, a in zip([""] + args, args):
            if a.startswith("-") and not a.startswith("--") and a[1:2] in ("s", "f"):
                raise Rechazado("Rechazado: date solo para ver la hora, no para cambiarla.")
            if not a.startswith(("-", "+")) and previo not in ("-d", "--date"):
                raise Rechazado("Rechazado: date solo para ver la hora, no para cambiarla.")

    elif programa == "hostname":
        if posicionales or any(a in ("-F", "-b") for a in cortas):
            raise Rechazado("Rechazado: hostname solo para verlo, no para cambiarlo.")

    elif programa == "uniq":
        if len(posicionales) > 1:  # "uniq entrada salida" escribe el segundo archivo
            raise Rechazado("Rechazado: uniq con dos archivos escribe el segundo.")

    elif programa == "ps":
        # Las opciones estilo BSD (sin guion) con 'e' muestran las variables de entorno
        # de cada proceso, que pueden tener claves de API.
        for previo, a in zip([""] + args, args):
            if previo in OPCIONES_PS_CON_VALOR:
                continue
            if a.isalpha() and "e" in a:
                raise Rechazado("Rechazado: 'ps e' muestra variables de entorno (pueden tener claves).")

    # Todo argumento que no sea opcion (y el valor de las --opcion=valor) se trata como
    # posible ruta. Si no lo es, la revision no cuesta nada.
    for a in args:
        valor = a.split("=", 1)[1] if a.startswith("--") and "=" in a else a
        if valor and not valor.startswith("-"):
            _revisar_ruta(valor, programa)

    ruta = shutil.which(programa, path=RUTAS_DE_COMANDOS)
    if ruta is None:
        raise Rechazado(f"'{programa}' no esta instalado en este equipo.")
    return [ruta] + [os.path.expanduser(a) for a in args]


def validar_consulta_linux(comando: str) -> list[list[str]]:
    """
    Acepta solo comandos de consulta. Permite pipelines (ps aux | grep brave) pero
    exige que CADA tramo sea un programa de la lista blanca, sin opciones que
    modifiquen. Devuelve los tramos listos para ejecutar sin shell, o lanza Rechazado.
    """
    limpio = comando.strip()
    if not limpio:
        raise Rechazado("Comando vacio.")
    if len(limpio) > 500:
        raise Rechazado("Comando demasiado largo para ser una consulta simple.")
    if "\n" in limpio or "\r" in limpio:
        raise Rechazado("Rechazado: un solo comando por vez, sin saltos de linea.")

    tramos = _partir(limpio)
    if len(tramos) > MAX_TRAMOS:
        raise Rechazado(f"Demasiados tramos en el pipeline (maximo {MAX_TRAMOS}).")
    return [_revisar_tramo(t) for t in tramos]


# --- Windows (PowerShell) ---

# Lista blanca de verbos. Todos leen informacion; ninguno modifica nada.
VERBOS_POWERSHELL = frozenset({
    "get-process", "get-service", "get-date", "get-childitem", "get-content",
    "get-location", "get-computerinfo", "get-ciminstance", "get-wmiobject",
    "get-volume", "get-psdrive", "get-host", "get-command", "get-module",
    "get-hotfix", "get-timezone", "get-culture", "get-item", "get-itemproperty",
    "get-netadapter", "get-nettcpconnection", "get-nettcpsetting", "get-counter",
    "get-eventlog", "get-winevent", "get-disk", "get-partition", "get-physicaldisk",
    "test-path", "test-connection", "test-netconnection",
    "measure-object", "select-object", "where-object", "sort-object",
    "group-object", "format-table", "format-list", "out-string",
    "select-string", "convertto-json", "convertfrom-json",
    "resolve-path", "split-path", "join-path", "compare-object",
    "ls", "dir", "gci", "cat", "gc", "pwd", "select", "where", "sort", "ft", "fl",
})

# Tokens que permiten salirse de la lista blanca aunque el primer verbo sea valido.
TOKENS_PROHIBIDOS_POWERSHELL = (
    ";", "&", "`", "$(", "@(", "&&", "||", ">", ">>", "<",
    "iex", "invoke-expression", "invoke-command", "invoke-webrequest", "invoke-restmethod",
    "start-process", "new-object", "add-type", "downloadstring", "downloadfile",
    "-encodedcommand", "-enc ", "frombase64", "reflection", "scriptblock",
    "set-", "new-", "remove-", "clear-", "stop-", "restart-", "rename-", "move-",
    "copy-", "out-file", "add-content", "export-", "import-module", "register-",
    "unregister-", "disable-", "enable-", "suspend-", "resume-", "wait-",
    "rm ", "del ", "rd ", "rmdir", "mkdir", "md ", "cp ", "mv ", "ni ", "si ",
    "sc ", "curl", "wget", "cmd", "powershell", "pwsh", "wmic", "reg ", "regedit",
    "schtasks", "net ", "netsh", "shutdown", "taskkill", "bcdedit", "vssadmin",
)


def validar_consulta_powershell(comando: str) -> str:
    """
    Acepta solo comandos de consulta de PowerShell. Permite pipelines (Get-Process |
    Select-Object) pero exige que CADA segmento del pipeline empiece con un verbo de la
    lista blanca. Devuelve el comando limpio, o lanza Rechazado si algo no cuadra.
    """
    limpio = comando.strip()
    if not limpio:
        raise Rechazado("Comando vacio.")
    if len(limpio) > 500:
        raise Rechazado("Comando demasiado largo para ser una consulta simple.")
    if "\n" in limpio or "\r" in limpio:
        raise Rechazado("Rechazado: un solo comando por vez, sin saltos de linea.")

    bajo = limpio.lower()

    for token in TOKENS_PROHIBIDOS_POWERSHELL:
        if token in bajo:
            raise Rechazado(
                f"Rechazado: contiene '{token.strip()}'. Solo acepto comandos de "
                "consulta simples. Para abrir programas usa abrir_programa; para "
                "escribir archivos, escribir_archivo."
            )

    # Get-Content y compania leen archivos: las credenciales no se tocan, igual que en
    # la lectura normal (en Linux esto lo hace _revisar_ruta).
    for fragmento in FRAGMENTOS_PROHIBIDOS:
        if fragmento in bajo:
            raise Rechazado(
                f"Rechazado: '{fragmento}' parece apuntar a credenciales o archivos del "
                "sistema. No lo toco."
            )

    # Cada tramo del pipeline tiene que empezar con un verbo permitido.
    for tramo in bajo.split("|"):
        palabras = tramo.strip().split()
        if not palabras:
            raise Rechazado("Hay un tramo vacio en el pipeline.")
        if palabras[0] not in VERBOS_POWERSHELL:
            raise Rechazado(
                f"Rechazado: '{palabras[0]}' no esta en la lista de comandos de consulta "
                "permitidos."
            )

    return limpio


def validar_comando_consulta(comando: str):
    """El validador del sistema en el que corre Nox (ver los dos de arriba)."""
    if plataforma.ES_WINDOWS:
        return validar_consulta_powershell(comando)
    return validar_consulta_linux(comando)


# --- Procesos que nunca se cierran ---

# Aunque coincidan con algo del catalogo: cerrarlos rompe la sesion (Windows o Linux) o
# deja a Nox sin piso. Se compara con el nombre normalizado, sin extension.
INTOCABLES = frozenset({
    # Windows
    "explorer", "dwm", "csrss", "winlogon", "wininit", "services", "lsass",
    "svchost", "smss", "system", "registry", "fontdrvhost", "sihost", "taskhostw",
    "ctfmon", "audiodg", "conhost", "runtimebroker", "searchhost", "startmenuexperiencehost",
    "shellexperiencehost", "textinputhost", "applicationframehost", "ollama app", "pythonw",
    # Linux / KDE Plasma
    "systemd", "kwin_wayland", "kwin_x11", "plasmashell", "ksmserver", "kded6",
    "xwayland", "pipewire", "pipewire-pulse", "wireplumber", "dbus-daemon", "dbus-broker",
    "xdg-desktop-portal", "xdg-desktop-portal-kde", "org_kde_powerdevil",
    "polkit-kde-authentication-agent-1", "networkmanager", "plasma-login-manager",
    "kwalletd6", "kglobalacceld", "xdg-desktop-portal-gtk",
    # Comunes: el propio Nox y su modelo
    "ollama", "python", "python3",
})


def es_intocable(nombre: str) -> bool:
    """True si un proceso es del sistema, de Ollama o del propio Nox (cualquier Python)."""
    n = nombre.lower().removesuffix(".exe")
    return n in INTOCABLES or n.startswith("python")


# --- Texto ---

def normalizar(texto: str) -> str:
    """Minusculas sin tildes, para comparar nombres sin depender de como se escribieron."""
    texto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")
