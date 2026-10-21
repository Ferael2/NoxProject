"""
Memoria persistente del asistente.

Guarda cosas que Brian le cuenta en el chat y que deberian sobrevivir a cerrar el
programa. Es distinta de la boveda: la boveda es conocimiento curado (notas que Brian
escribe y revisa), esto es lo que el asistente aprende sobre la marcha conversando.

Cada recuerdo se guarda con su embedding, asi que se puede buscar por significado y no
solo por palabras exactas.
"""
import json
import math
import sqlite3
import sys
from datetime import datetime, timedelta

import numpy as np
import requests

import config

# pythonw.exe (sin consola) deja sys.stdout en None, asi que hay que chequear.
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

# "sesion" son los resumenes de conversaciones (ver resumir_sesion): ocupan poco y se pueden
# limpiar cuando dejan de usarse. Las demas son cosas que la persona le dijo a Nox.
CATEGORIAS = ("preferencia", "dato", "proyecto", "correccion", "sesion")

# Cuanto pesa cada tipo al elegir lo que Nox ya sabe al empezar. Las correcciones primero: si le
# dijiste "eso no es asi", que no lo vuelva a decir.
PESO_CATEGORIA = {"correccion": 3.0, "preferencia": 2.0, "proyecto": 1.5, "dato": 1.0, "sesion": 0.6}

UMBRAL_DUPLICADO_AL_GUARDAR = 0.95   # tan parecido que ni se guarda
UMBRAL_DUPLICADO_REVISION = 0.88     # tan parecido que se propone fusionarlos
DIAS_SIN_USO = 90                    # un dato que no se uso en este tiempo se propone para olvidar
CATEGORIAS_OLVIDABLES = ("dato", "sesion")   # lo que la persona dijo como preferencia o correccion no caduca solo


def _conectar() -> sqlite3.Connection:
    conn = sqlite3.connect(config.MEMORIA_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recuerdos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contenido TEXT NOT NULL,
            categoria TEXT NOT NULL,
            fecha TEXT NOT NULL,
            embedding BLOB NOT NULL
        )
    """)
    conn.execute("CREATE TABLE IF NOT EXISTS meta (clave TEXT PRIMARY KEY, valor TEXT NOT NULL)")
    # Migracion: las bases de antes no tienen estas columnas. Se agregan sin tocar lo que hay.
    columnas = {f[1] for f in conn.execute("PRAGMA table_info(recuerdos)")}
    if "usos" not in columnas:
        conn.execute("ALTER TABLE recuerdos ADD COLUMN usos INTEGER NOT NULL DEFAULT 0")
    if "ultimo_uso" not in columnas:
        conn.execute("ALTER TABLE recuerdos ADD COLUMN ultimo_uso TEXT")
    if "origen" not in columnas:
        conn.execute("ALTER TABLE recuerdos ADD COLUMN origen TEXT NOT NULL DEFAULT 'usuario'")
    conn.commit()
    return conn


import hashlib
import re


def _vector_local(texto: str, dim: int = 512) -> np.ndarray:
    """Vectorizador local determinista por palabras y trigramas: funciona sin red y sin Ollama."""
    vec = np.zeros(dim, dtype=np.float32)
    tokens = re.findall(r"\w+", texto.lower())
    for t in tokens:
        h = int(hashlib.md5(t.encode("utf-8")).hexdigest(), 16) % dim
        vec[h] += 1.0
        for i in range(len(t) - 2):
            ng = t[i:i+3]
            h_ng = int(hashlib.md5(ng.encode("utf-8")).hexdigest(), 16) % dim
            vec[h_ng] += 0.5
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


def _embed(texto: str) -> np.ndarray:
    if getattr(config, "USAR_OLLAMA_EMBED", False):
        try:
            resp = requests.post(
                config.EMBED_URL,
                json={"model": config.MODELO_EMBED, "prompt": texto},
                timeout=5,
            )
            resp.raise_for_status()
            return np.array(resp.json()["embedding"], dtype=np.float32)
        except Exception:
            pass
    return _vector_local(texto)


def asegurar_modelo() -> int:
    """
    Si cambio el modelo de embeddings, los vectores guardados ya no se
    pueden comparar con los nuevos: se recalculan todos (son pocos).
    Funciona tanto con Ollama como con el vectorizador local independiente.
    """
    conn = _conectar()
    modelo_actual = config.MODELO_EMBED if getattr(config, "USAR_OLLAMA_EMBED", False) else "local_vector_512"
    guardado = conn.execute("SELECT valor FROM meta WHERE clave = 'modelo_emb'").fetchone()
    filas = conn.execute("SELECT id, contenido FROM recuerdos").fetchall()
    if guardado and guardado[0] == modelo_actual:
        conn.close()
        return 0
    if not filas:
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('modelo_emb', ?)", (modelo_actual,))
        conn.commit()
        conn.close()
        return 0
    try:
        nuevos = [(_embed(c).tobytes(), i) for i, c in filas]
    except Exception:
        conn.close()
        return 0
    conn.executemany("UPDATE recuerdos SET embedding = ? WHERE id = ?", nuevos)
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('modelo_emb', ?)", (modelo_actual,))
    conn.commit()
    conn.close()
    return len(nuevos)


def guardar(contenido: str, categoria: str = "dato", origen: str = "usuario") -> str:
    """Guarda un recuerdo nuevo. Evita duplicados casi identicos."""
    if categoria not in CATEGORIAS:
        categoria = "dato"

    asegurar_modelo()
    vec = _embed(contenido)
    conn = _conectar()

    # Si ya hay algo practicamente igual, no duplicar.
    existentes = conn.execute("SELECT id, contenido, embedding FROM recuerdos").fetchall()
    if existentes:
        matriz = np.vstack([np.frombuffer(e[2], dtype=np.float32) for e in existentes])
        matriz = matriz / (np.linalg.norm(matriz, axis=1, keepdims=True) + 1e-8)
        sims = matriz @ (vec / (np.linalg.norm(vec) + 1e-8))
        if sims.max() > UMBRAL_DUPLICADO_AL_GUARDAR:
            idx = int(np.argmax(sims))
            conn.close()
            return f"Ya recordaba algo casi igual (#{existentes[idx][0]}): {existentes[idx][1]}"

    cur = conn.execute(
        "INSERT INTO recuerdos (contenido, categoria, fecha, embedding, origen) VALUES (?, ?, ?, ?, ?)",
        (contenido, categoria, datetime.now().isoformat(timespec="seconds"), vec.tobytes(), origen),
    )
    conn.commit()
    nuevo_id = cur.lastrowid
    conn.close()
    return f"Recordado (#{nuevo_id}, {categoria}): {contenido}"


def buscar(consulta: str, top_k: int = 5) -> list[dict]:
    """Busca recuerdos por significado."""
    asegurar_modelo()
    conn = _conectar()
    filas = conn.execute(
        "SELECT id, contenido, categoria, fecha, embedding FROM recuerdos"
    ).fetchall()
    conn.close()

    if not filas:
        return []

    matriz = np.vstack([np.frombuffer(f[4], dtype=np.float32) for f in filas])
    matriz = matriz / (np.linalg.norm(matriz, axis=1, keepdims=True) + 1e-8)

    vec = _embed(consulta)
    vec = vec / (np.linalg.norm(vec) + 1e-8)
    scores = matriz @ vec

    resultados = []
    umbral = config.UMBRAL_MEMORIA if getattr(config, "USAR_OLLAMA_EMBED", False) else 0.15
    for idx in np.argsort(-scores)[:top_k]:
        if scores[idx] < umbral:
            continue
        resultados.append({
            "id": filas[idx][0],
            "contenido": filas[idx][1],
            "categoria": filas[idx][2],
            "fecha": filas[idx][3],
            "score": round(float(scores[idx]), 3),
        })
    _anotar_uso([r["id"] for r in resultados])
    return resultados


def _anotar_uso(ids: list[int]):
    """Cuenta que estos recuerdos SE USARON: es lo que los distingue de los que sobran."""
    if not ids:
        return
    conn = _conectar()
    ahora = datetime.now().isoformat(timespec="seconds")
    conn.executemany("UPDATE recuerdos SET usos = usos + 1, ultimo_uso = ? WHERE id = ?", [(ahora, i) for i in ids])
    conn.commit()
    conn.close()


def listar(categoria: str = "") -> list[dict]:
    """Lista todos los recuerdos, opcionalmente de una categoria."""
    conn = _conectar()
    consulta = "SELECT id, contenido, categoria, fecha, usos, ultimo_uso, origen FROM recuerdos"
    if categoria:
        filas = conn.execute(consulta + " WHERE categoria = ? ORDER BY id", (categoria,)).fetchall()
    else:
        filas = conn.execute(consulta + " ORDER BY id").fetchall()
    conn.close()
    return [
        {"id": f[0], "contenido": f[1], "categoria": f[2], "fecha": f[3],
         "usos": f[4], "ultimo_uso": f[5], "origen": f[6]} for f in filas
    ]


def olvidar(id_recuerdo: int) -> str:
    conn = _conectar()
    fila = conn.execute(
        "SELECT contenido FROM recuerdos WHERE id = ?", (id_recuerdo,)
    ).fetchone()
    if not fila:
        conn.close()
        return f"No existe el recuerdo #{id_recuerdo}."
    conn.execute("DELETE FROM recuerdos WHERE id = ?", (id_recuerdo,))
    conn.commit()
    conn.close()
    return f"Olvidado #{id_recuerdo}: {fila[0]}"


def _importancia(r: dict, ahora: datetime) -> float:
    """
    Cuanto merece un recuerdo estar entre lo que Nox ya sabe al empezar: pesa su tipo, cuantas
    veces se uso (con rendimientos decrecientes) y que tan reciente es lo ultimo que lo toco.
    """
    base = PESO_CATEGORIA.get(r["categoria"], 1.0)
    uso = math.log1p(r.get("usos", 0))
    ultimo = r.get("ultimo_uso") or r["fecha"]
    try:
        dias = max((ahora - datetime.fromisoformat(ultimo)).days, 0)
    except ValueError:
        dias = 0
    frescura = 1.0 / (1.0 + dias / 60.0)       # a los 60 dias vale la mitad
    return base * (1.0 + uso) * (0.5 + 0.5 * frescura)


def contexto_inicial(limite: int = 15, max_chars: int = 1800) -> str:
    """
    Los recuerdos mas importantes, para inyectar al system prompt al arrancar una conversacion.
    Se elige por importancia (tipo, uso y frescura), no solo por categoria, y se acota por largo:
    asi la memoria no se come el contexto del modelo a medida que crece.
    """
    recuerdos = listar()
    if not recuerdos:
        return ""

    ahora = datetime.now()
    recuerdos.sort(key=lambda r: -_importancia(r, ahora))

    lineas, usados = [], 0
    for r in recuerdos[:limite]:
        linea = f"- ({r['categoria']}) {r['contenido']}"
        if usados + len(linea) > max_chars:
            break
        lineas.append(linea)
        usados += len(linea) + 1
    return f"LO QUE YA SABES DE {config.USUARIO.upper()} (memoria de conversaciones anteriores):\n" + "\n".join(lineas)


# --- Mantenimiento: duplicados y olvido ---
# Nada de esto se aplica solo: Nox PROPONE y la persona decide (Ajustes > Memoria). Borrar es
# irreversible, y una memoria que se borra sola en silencio es una que no puedes auditar.

def candidatos_duplicados(umbral: float = UMBRAL_DUPLICADO_REVISION) -> list[dict]:
    """
    Pares de recuerdos muy parecidos entre si, del mas parecido al menos. Cada recuerdo aparece
    en un solo par (el de mayor parecido), para no proponer fusionar tres cosas contra una.
    Devuelve [{a, b, similitud}] donde a y b son los recuerdos completos.
    """
    asegurar_modelo()
    conn = _conectar()
    filas = conn.execute("SELECT id, embedding FROM recuerdos ORDER BY id").fetchall()
    conn.close()
    recuerdos = {r["id"]: r for r in listar()}
    if len(filas) < 2:
        return []

    ids = [f[0] for f in filas]
    matriz = np.vstack([np.frombuffer(f[1], dtype=np.float32) for f in filas])
    matriz = matriz / (np.linalg.norm(matriz, axis=1, keepdims=True) + 1e-8)
    sims = matriz @ matriz.T
    pares = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if sims[i, j] >= umbral:
                pares.append((float(sims[i, j]), ids[i], ids[j]))
    pares.sort(reverse=True)

    usados, resultado = set(), []
    for sim, a, b in pares:
        if a in usados or b in usados:
            continue
        usados |= {a, b}
        resultado.append({"a": recuerdos[a], "b": recuerdos[b], "similitud": round(sim, 3)})
    return resultado


def fusionar(id_conservar: int, id_borrar: int) -> str:
    """
    Deja un solo recuerdo de dos casi iguales: se conserva uno y el otro se borra, sumando sus usos
    para no perder lo que ya se aprendio de cuanto sirve.
    """
    if id_conservar == id_borrar:
        return "Son el mismo recuerdo."
    conn = _conectar()
    filas = {f[0]: f for f in conn.execute(
        "SELECT id, contenido, usos FROM recuerdos WHERE id IN (?, ?)", (id_conservar, id_borrar))}
    if len(filas) < 2:
        conn.close()
        return "Uno de los dos recuerdos ya no existe."
    conn.execute("UPDATE recuerdos SET usos = usos + ? WHERE id = ?", (filas[id_borrar][2], id_conservar))
    conn.execute("DELETE FROM recuerdos WHERE id = ?", (id_borrar,))
    conn.commit()
    conn.close()
    return f"Fusionados: se conserva #{id_conservar} y se olvida #{id_borrar}."


def candidatos_olvido(dias: int = DIAS_SIN_USO, ahora: datetime | None = None) -> list[dict]:
    """
    Recuerdos que probablemente ya no hacen falta: datos sueltos (y resumenes de sesion) con mas de
    'dias' dias, que NUNCA se han usado. Las preferencias, correcciones y proyectos no caducan solos.
    """
    ahora = ahora or datetime.now()
    limite = ahora - timedelta(days=dias)
    candidatos = []
    for r in listar():
        if r["categoria"] not in CATEGORIAS_OLVIDABLES or r["usos"] > 0:
            continue
        try:
            if datetime.fromisoformat(r["fecha"]) <= limite:
                candidatos.append(r)
        except ValueError:
            continue
    return candidatos


def estadisticas() -> dict:
    rs = listar()
    por_categoria = {}
    for r in rs:
        por_categoria[r["categoria"]] = por_categoria.get(r["categoria"], 0) + 1
    return {"total": len(rs), "por_categoria": por_categoria, "sin_uso": sum(1 for r in rs if r["usos"] == 0),
            "duplicados": len(candidatos_duplicados()) if len(rs) > 1 else 0, "para_olvidar": len(candidatos_olvido())}


# --- Resumen de una conversacion ---

def resumir_sesion(mensajes: list[dict], preguntar=None) -> list[str]:
    """
    Resume una conversacion en hasta 3 frases cortas que valga la pena recordar (lo que la persona
    CONTO o DECIDIO; no lo que Nox respondio). Se guardan como categoria "sesion". Solo con el
    modelo LOCAL: la conversacion no sale de la PC. 'preguntar' permite sustituir al modelo en las
    pruebas. Devuelve [] si no hay nada que valga la pena.
    """
    dichos = [m["content"].split("\n\n[")[0].strip() for m in mensajes if m.get("role") == "user" and m.get("content")]
    if len(dichos) < 3:
        return []
    transcripcion = "\n".join(f"- {d[:300]}" for d in dichos[-14:])
    pedido = (
        "Esto es lo que una persona le dijo a su asistente en una conversacion. Extrae como MAXIMO 3 "
        "hechos, decisiones o planes concretos que valga la pena recordar para otro dia (no saludos, "
        "no preguntas sueltas, no cosas del momento). Cada uno en una frase corta en tercera persona. "
        "Responde SOLO con una lista JSON de textos, por ejemplo [\"Quiere aprender Rust este mes\"]. "
        "Si no hay nada que valga la pena, responde [].\n\n" + transcripcion)
    if preguntar is None:
        def preguntar(texto):
            r = requests.post(config.CHAT_URL, json={
                "model": config.MODELO_CHAT, "stream": False, "think": False,
                "messages": [{"role": "user", "content": texto}],
                "options": {"temperature": 0.2, "num_ctx": 4096}, "keep_alive": config.KEEP_ALIVE_NORMAL}, timeout=180)
            r.raise_for_status()
            return r.json()["message"]["content"]
    try:
        crudo = preguntar(pedido)
        inicio, fin = crudo.index("["), crudo.rindex("]") + 1
        frases = json.loads(crudo[inicio:fin])
    except (ValueError, requests.RequestException, KeyError):
        return []
    return [" ".join(str(f).split())[:200] for f in frases if isinstance(f, str) and len(str(f).strip()) >= 8][:3]


def guardar_resumen_de_sesion(mensajes: list[dict], preguntar=None) -> int:
    """Resume la conversacion y guarda lo que valga la pena. Devuelve cuantos recuerdos nuevos quedaron."""
    nuevos = 0
    for frase in resumir_sesion(mensajes, preguntar):
        if guardar(frase, "sesion", origen="resumen").startswith("Recordado"):
            nuevos += 1
    return nuevos
