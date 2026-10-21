"""
Barreras de seguridad para las acciones que modifican algo.

La idea de fondo: no alcanza con impedir lo prohibido, porque el daño real casi nunca
viene de lo prohibido — viene de lo permitido hecho mal. Sobrescribir el archivo
equivocado esta "permitido"; perder el trabajo igual duele.

Cuatro capas, de menos a mas intrusiva:

1. RESPALDO — antes de pisar un archivo existente, se guarda una copia. Nada de lo que
   Nox haga sobre archivos es irreversible.
2. BITACORA — todo lo que modifica algo queda registrado con fecha, para poder auditar
   despues "¿que hizo?" sin depender de la memoria del chat.
3. LIMITE POR TURNO — un modelo confundido (o engañado por una pagina web) podria
   encadenar acciones. Se corta despues de N.
4. CONFIRMACION — las acciones que no se pueden deshacer con un respaldo (cerrar un
   programa con trabajo sin guardar) le preguntan a Brian.
"""
import shutil
import sys
from datetime import datetime
from pathlib import Path

import config

if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

CARPETA_RESPALDOS = config.CARPETA_TRABAJO / "respaldos"
BITACORA = config.CARPETA_TRABAJO / "bitacora.log"

# Acciones que modifican algo. Todo lo que no este aca es de solo lectura.
ACCIONES_QUE_MODIFICAN = {
    "escribir_archivo", "crear_documento", "convertir_documento",
    "crear_nota", "agregar_a_nota", "registrar_en_log",
    "cerrar_programa", "abrir_programa", "control_multimedia",
    "recordar", "olvidar", "reindexar_boveda", "abrir_web",
    "reproducir_en_youtube", "crear_recordatorio", "cancelar_recordatorio", "mirar_pantalla",
}

# Las que pueden causar una perdida que ningun respaldo recupera.
NECESITAN_CONFIRMACION = {"cerrar_programa"}

# Contador por turno, para cortar cadenas descontroladas.
_acciones_del_turno = []
_origen_externo_leido = False
_ultimo_origen_externo = ""

# La interfaz enchufa aca su dialogo de confirmacion. Si nadie lo enchufa, se niega
# por defecto: preferimos no hacer nada antes que hacer algo sin preguntar.
_pedir_confirmacion = None


def registrar_contenido_externo(tipo: str, origen: str):
    """Marca que en este turno se leyó contenido no confiable de internet o fuentes externas."""
    global _origen_externo_leido, _ultimo_origen_externo
    _origen_externo_leido = True
    _ultimo_origen_externo = f"{tipo}:{origen[:60]}"
    _escribir_bitacora(f"CONTENIDO_EXTERNO_LEIDO  {_ultimo_origen_externo}")


def registrar_confirmador(funcion):
    """La GUI llama esto al arrancar para poder preguntarle al usuario."""
    global _pedir_confirmacion
    _pedir_confirmacion = funcion


def nuevo_turno():
    """Reinicia el contador. Lo llama el nucleo al empezar cada mensaje."""
    global _origen_externo_leido, _ultimo_origen_externo
    _acciones_del_turno.clear()
    _origen_externo_leido = False
    _ultimo_origen_externo = ""


def _escribir_bitacora(texto: str):
    try:
        BITACORA.parent.mkdir(parents=True, exist_ok=True)
        marca = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with BITACORA.open("a", encoding="utf-8") as f:
            f.write(f"{marca}  {texto}\n")
    except OSError:
        pass  # no poder escribir la bitacora nunca debe frenar el trabajo


def respaldar(ruta) -> Path | None:
    """
    Copia un archivo antes de que lo pisen. Devuelve la ruta del respaldo, o None si
    el archivo no existia (nada que respaldar).
    """
    origen = Path(ruta)
    if not origen.exists() or not origen.is_file():
        return None

    try:
        CARPETA_RESPALDOS.mkdir(parents=True, exist_ok=True)
        marca = datetime.now().strftime("%Y%m%d-%H%M%S")
        destino = CARPETA_RESPALDOS / f"{origen.stem}_{marca}{origen.suffix}"
        shutil.copy2(origen, destino)
        _escribir_bitacora(f"RESPALDO  {origen} -> {destino.name}")
        return destino
    except OSError as e:
        _escribir_bitacora(f"RESPALDO FALLIDO  {origen}: {e}")
        return None


def revisar(nombre: str, args: dict) -> tuple[bool, str]:
    """
    Se llama antes de ejecutar cada herramienta.

    Devuelve (permitido, motivo). Si permitido es False, la herramienta no corre y el
    motivo se le devuelve al modelo para que se lo explique a quien usa Nox.

    Las herramientas externas (MCP, nombres que empiezan con 'mcp_') se tratan siempre como
    acciones que modifican algo, porque no sabemos que hace el codigo de un tercero: cuentan
    para el limite por turno, y si la persona las dejo en "preguntar" se le pide permiso.
    """
    externa = nombre.startswith("mcp_")
    politica = None

    # Una herramienta apagada no debe ni mostrar un cuadro de permiso: no existe para el modelo.
    if nombre == "mirar_pantalla" and not config.VISTA_ACTIVA:
        return False, "La vista está desactivada (se activa en Ajustes > Vista, y viene apagada a propósito)."

    if externa:
        import mcp_cliente
        politica = mcp_cliente.administrador().politica_de(nombre)
        if politica in (None, "bloquear"):
            _escribir_bitacora(f"BLOQUEADO  herramienta externa {nombre}")
            return False, ("Esa herramienta externa está bloqueada (o no existe). "
                           "Se activa desde Ajustes > Herramientas externas.")
    elif nombre not in ACCIONES_QUE_MODIFICAN:
        return True, ""  # solo lectura: pasa sin trabas

    _acciones_del_turno.append(nombre)

    if len(_acciones_del_turno) > config.MAX_ACCIONES_POR_TURNO:
        hechas = ", ".join(_acciones_del_turno[:-1])
        _escribir_bitacora(f"CORTADO  demasiadas acciones en un turno: {hechas}")
        return False, (
            f"Freno: ya hice {len(_acciones_del_turno) - 1} acciones que modifican cosas "
            f"en este solo pedido ({hechas}). Es mas de lo normal, asi que paro por las "
            "dudas. Si de verdad querias todo eso, pedimelo de nuevo por partes."
        )

    # Si en este turno se leyo contenido externo (web/busqueda), cualquier accion que modifique algo
    # (escribir notas, archivos, abrir programas) debe confirmarse para frenar inyecciones indirectas.
    origen_contaminado = _origen_externo_leido and nombre in ACCIONES_QUE_MODIFICAN

    if (nombre in NECESITAN_CONFIRMACION or (externa and politica == "preguntar")
            or (nombre == "mirar_pantalla" and config.VISTA_PREGUNTAR)
            or origen_contaminado):
        detalle = ", ".join(f"{k}={v}" for k, v in args.items())
        motivo_extra = f" (Alerta: se leyó contenido externo en este turno {_ultimo_origen_externo})" if origen_contaminado else ""
        if _pedir_confirmacion is None:
            _escribir_bitacora(f"DENEGADO (sin confirmador)  {nombre}({detalle}){motivo_extra}")
            return False, (
                f"'{nombre}' necesita que {config.USUARIO} lo confirme{motivo_extra} y no tengo como preguntarle "
                "desde aca."
            )
        if not _pedir_confirmacion(nombre, args):
            _escribir_bitacora(f"RECHAZADO POR EL USUARIO  {nombre}({detalle}){motivo_extra}")
            return False, f"{config.USUARIO} no autorizo '{nombre}'{motivo_extra}. Acción detenida por seguridad."
        _escribir_bitacora(f"CONFIRMADO  {nombre}({detalle}){motivo_extra}")

    return True, ""


def anotar(nombre: str, args: dict, resultado: str):
    """Deja constancia de lo que se hizo, despues de hacerlo."""
    if nombre not in ACCIONES_QUE_MODIFICAN and not nombre.startswith("mcp_"):
        return
    detalle = ", ".join(f"{k}={str(v)[:60]}" for k, v in args.items())
    _escribir_bitacora(f"{nombre}({detalle}) -> {resultado[:120]}")


def leer_bitacora(lineas: int = 30) -> str:
    """Ultimas acciones registradas, para que Brian pueda auditar."""
    if not BITACORA.exists():
        return "Todavia no hice nada que modifique algo."
    try:
        todas = BITACORA.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        return f"No pude leer la bitacora: {e}"
    return "\n".join(todas[-lineas:]) or "La bitacora esta vacia."


def listar_respaldos(lineas: int = 25) -> str:
    """Copias guardadas antes de sobrescribir, por si hay que recuperar algo."""
    if not CARPETA_RESPALDOS.exists():
        return "No hay respaldos: todavia no sobrescribi ningun archivo."
    archivos = sorted(
        CARPETA_RESPALDOS.iterdir(), key=lambda p: -p.stat().st_mtime
    )[:lineas]
    if not archivos:
        return "No hay respaldos."
    filas = [f"En {CARPETA_RESPALDOS}:\n"]
    for p in archivos:
        fecha = datetime.fromtimestamp(p.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
        filas.append(f"  {p.name}  ({fecha})")
    return "\n".join(filas)
