"""
Capa de acceso a la boveda de Obsidian.

Reutiliza el indice vectorial que ya mantiene la boveda (RAG/index.db, generado
por RAG/index_vault.py) en vez de construir uno propio: una sola base, una sola
verdad. Si se reindexa la boveda, el asistente ve los cambios sin tocar nada aca.

La matriz de embeddings se carga una sola vez por sesion y queda cacheada, para
que la segunda busqueda en adelante no vuelva a leer los 900+ fragmentos.
"""
import re
import sqlite3
import sys

import numpy as np
import requests

import config
import seguridad

# pythonw.exe (sin consola) deja sys.stdout en None, asi que hay que chequear.
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

# Cache de sesion: (filepaths, headings, contents, matriz_normalizada)
_cache = None
# Cache del indice BM25: (frecuencias, largos, largo_medio, idf)
_bm25 = None
# Indices de fragmentos que son solo listas de enlaces
_navegacion = None


def _embed(texto: str) -> np.ndarray:
    """Convierte texto a vector con el mismo modelo que uso el indexador."""
    resp = requests.post(
        config.EMBED_URL,
        json={"model": config.MODELO_EMBED, "prompt": texto},
        timeout=60,
    )
    resp.raise_for_status()
    return np.array(resp.json()["embedding"], dtype=np.float32)


def _cargar_indice():
    """Lee todos los fragmentos del indice y prenormaliza los vectores."""
    global _cache
    if _cache is not None:
        return _cache

    if not config.INDICE_DB.exists():
        raise FileNotFoundError(
            f"No existe el indice {config.INDICE_DB}. "
            "Corre primero: python RAG/index_vault.py"
        )

    conn = sqlite3.connect(config.INDICE_DB)
    filas = conn.execute(
        "SELECT filepath, heading, content, embedding FROM chunks"
    ).fetchall()
    conn.close()

    if not filas:
        raise ValueError("El indice esta vacio. Corre RAG/index_vault.py")

    filepaths, headings, contents, vectores = [], [], [], []
    for filepath, heading, content, blob in filas:
        filepaths.append(filepath)
        headings.append(heading or "")
        contents.append(content)
        vectores.append(np.frombuffer(blob, dtype=np.float32))

    matriz = np.vstack(vectores)
    # Prenormalizar aca evita repetir el calculo en cada busqueda.
    matriz = matriz / (np.linalg.norm(matriz, axis=1, keepdims=True) + 1e-8)

    _cache = (filepaths, headings, contents, matriz)
    return _cache


def _tokenizar(texto: str) -> list[str]:
    """Palabras normalizadas (sin tildes, sin puntuacion) para la busqueda por palabras."""
    return re.findall(r"[a-z0-9]+", seguridad.normalizar(texto))


def _cargar_bm25():
    """
    Indice BM25 sobre los mismos fragmentos, para busqueda por palabras exactas.

    La busqueda semantica sola falla con nombres propios, siglas y terminos raros
    ("DTE", "Thymeleaf", "gfx1102"): el embedding los diluye. BM25 los encuentra
    justamente porque compara palabras. Se combinan las dos mas abajo.
    """
    global _bm25
    if _bm25 is not None:
        return _bm25

    _, _, contents, _ = _cargar_indice()
    docs = [_tokenizar(c) for c in contents]

    frecuencias = []      # {palabra: veces} por documento
    doc_freq = {}         # en cuantos documentos aparece cada palabra
    for tokens in docs:
        cuenta = {}
        for t in tokens:
            cuenta[t] = cuenta.get(t, 0) + 1
        frecuencias.append(cuenta)
        for t in cuenta:
            doc_freq[t] = doc_freq.get(t, 0) + 1

    largos = np.array([len(d) for d in docs], dtype=np.float32)
    largo_medio = float(largos.mean()) if len(largos) else 1.0
    n = len(docs)

    # IDF de BM25 (variante suavizada, siempre positiva)
    idf = {
        palabra: np.log(1 + (n - df + 0.5) / (df + 0.5))
        for palabra, df in doc_freq.items()
    }

    _bm25 = (frecuencias, largos, largo_medio, idf)
    return _bm25


def _puntajes_bm25(consulta: str) -> np.ndarray:
    frecuencias, largos, largo_medio, idf = _cargar_bm25()
    k1, b = 1.5, 0.75

    scores = np.zeros(len(frecuencias), dtype=np.float32)
    for palabra in _tokenizar(consulta):
        if palabra not in idf:
            continue
        peso = idf[palabra]
        for i, cuenta in enumerate(frecuencias):
            tf = cuenta.get(palabra, 0)
            if tf:
                norm = 1 - b + b * (largos[i] / largo_medio)
                scores[i] += peso * (tf * (k1 + 1)) / (tf + k1 * norm)
    return scores


# Palabras vacias del español. Si la consulta esta llena de estas, es una pregunta
# hablada, no una busqueda por termino.
VACIAS = frozenset("""
a al algo alguna algunas alguno algunos ante antes como con contra cual cuales cuando
cuanto de del desde donde dos el ella ellas ellos en entre era eran es esa esas ese eso
esos esta estaba estaban estan estar estas este esto estos fue fueron ha hace hacer han
hasta hay la las le les lo los mas me mi mis mucho muy ni no nos nosotros o otra otras
otro otros para pero poco por porque que quien quienes se sea si sin sobre son su sus
tambien tanto te tener tiene tienen todo todos tu tus un una uno unos y ya yo
""".split())


def _peso_lexico(consulta: str) -> float:
    """
    Cuanto debe pesar la busqueda por palabras frente a la semantica.

    Primera version usaba el IDF maximo como "rareza", y salio al reves: en "que le
    gusta a Brian de los videojuegos", la palabra mas rara resulto ser "gusta" (un
    verbo de relleno), y en "DTE" el termino exacto tenia IDF bajo justamente porque
    hay toda una seccion de la boveda sobre eso. Terminaba dandole todo el peso a las
    preguntas habladas y nada a las busquedas por termino.

    Lo que hay que distinguir no es rareza sino FORMA de la consulta:
      - identificador tecnico (camelCase, th:fragment, snake_case) -> BM25 manda
      - pocas palabras y ninguna vacia -> busqueda por termino -> BM25 pesa
      - muchas palabras vacias -> pregunta hablada -> que mande lo semantico
    """
    tokens = _tokenizar(consulta)
    if not tokens:
        return 0.3

    # camelCase, th:fragment, snake_case, nombres con numeros: identificadores.
    if re.search(r"[a-z][A-Z]|\w[:._]\w|\w\d|\d\w", consulta):
        return 1.2

    proporcion_vacias = sum(1 for t in tokens if t in VACIAS) / len(tokens)

    if len(tokens) <= 3 and proporcion_vacias == 0:
        return 1.0   # "DTE", "Codice Farulum": busqueda por nombre
    if proporcion_vacias > 0.4:
        return 0.25  # "que le gusta a Brian de los videojuegos": pregunta hablada
    return 0.6       # termino medio


def _chunks_de_navegacion() -> set[int]:
    """
    Indices de los fragmentos que son solo listas de enlaces (secciones
    "Relacionado", indices, mapas de seccion). Tienen poco valor como respuesta.
    """
    global _navegacion
    if _navegacion is not None:
        return _navegacion

    _, headings, contents, _ = _cargar_indice()
    _navegacion = set()
    for i, (heading, contenido) in enumerate(zip(headings, contents)):
        if heading.strip().lower() in ("relacionado", "indice", "índice"):
            _navegacion.add(i)
            continue
        # O si mas de la mitad del texto son wikilinks.
        enlaces = sum(len(m) for m in re.findall(r"\[\[([^\]]*)\]\]", contenido))
        if contenido and enlaces / len(contenido) > 0.5:
            _navegacion.add(i)
    return _navegacion


def buscar(consulta: str, top_k: int = None, modo: str = "hibrido") -> list[dict]:
    """
    Busca en la boveda. Por defecto combina dos busquedas distintas:

    - semantica (embeddings): entiende el significado, encuentra cosas parafraseadas
    - por palabras (BM25): encuentra terminos exactos, siglas y nombres propios

    Se fusionan con Reciprocal Rank Fusion: cada resultado suma 1/(60+puesto) de cada
    ranking. Lo que aparece bien posicionado en ambos sube; lo que solo aparece en uno
    igual entra. Es mas robusto que promediar los scores, porque no hay que normalizar
    dos escalas que no son comparables.
    """
    top_k = top_k or config.TOP_K_DEFECTO
    filepaths, headings, contents, matriz = _cargar_indice()

    vec = _embed(consulta)
    vec = vec / (np.linalg.norm(vec) + 1e-8)
    sem = matriz @ vec

    if modo == "semantico":
        orden = np.argsort(-sem)[:top_k]
        puntajes = {int(i): float(sem[i]) for i in orden}
    else:
        lex = _puntajes_bm25(consulta)
        peso_lex = _peso_lexico(consulta)
        navegacion = _chunks_de_navegacion()

        # Se fusiona por SCORE normalizado, no por puesto (RRF).
        #
        # Con RRF los puestos 1 y 3 valen 1/61 y 1/63: 3% de diferencia. Eso descarta
        # que la semantica considere al primero mucho mejor que al tercero (0.73 vs
        # 0.60), y cualquier empujoncito de BM25 daba vuelta el orden. Normalizando los
        # scores de cada lista a [0,1] se conserva esa distancia, que es justamente la
        # informacion que hace falta para decidir.
        tope = max(top_k * 4, 20)
        candidatos = set(np.argsort(-sem)[:tope].tolist())
        candidatos |= {int(i) for i in np.argsort(-lex)[:tope] if lex[i] > 0}

        def normalizar(valores: dict) -> dict:
            if not valores:
                return {}
            lo, hi = min(valores.values()), max(valores.values())
            if hi - lo < 1e-9:
                return {k: 1.0 for k in valores}
            return {k: (v - lo) / (hi - lo) for k, v in valores.items()}

        sem_n = normalizar({i: float(sem[i]) for i in candidatos})
        lex_n = normalizar({i: float(lex[i]) for i in candidatos})

        fusion = {
            i: sem_n[i] + peso_lex * lex_n.get(i, 0.0)
            for i in candidatos
        }

        # Las secciones "Relacionado" son listas de wikilinks: repiten mucho el termino
        # buscado en poco texto, asi que BM25 las adora, pero no dicen nada. Se hunden.
        for idx in navegacion & candidatos:
            fusion[idx] *= 0.3

        # Fuentes/ es material crudo sin procesar (paginas web pegadas, transcripciones).
        # Wiki/ es la version curada de esa misma informacion. Cuando las dos coinciden,
        # gana la curada. Un solo volcado crudo puede ocupar 40 fragmentos del indice y
        # tapar la nota buena; esto lo compensa sin sacarlo del indice.
        for idx in candidatos:
            if filepaths[idx].startswith("Fuentes"):
                fusion[idx] *= config.PESO_FUENTES

        orden = sorted(fusion, key=lambda i: -fusion[i])[:top_k]
        puntajes = {i: fusion[i] for i in orden}

    resultados = []
    for idx in orden:
        idx = int(idx)
        texto = contents[idx].strip()
        if len(texto) > config.MAX_CHARS_FRAGMENTO:
            texto = texto[: config.MAX_CHARS_FRAGMENTO] + "..."
        resultados.append(
            {
                "archivo": filepaths[idx],
                "seccion": headings[idx],
                "score": round(float(puntajes[idx]), 4),
                "similitud": round(float(sem[idx]), 3),
                "contenido": texto,
            }
        )
    return resultados


def leer_nota(ruta_relativa: str) -> str:
    """Lee una nota completa de la boveda a partir de su ruta relativa."""
    destino = (config.BOVEDA / ruta_relativa).resolve()

    # Comparar rutas como rutas, no como texto (ver seguridad.py).
    if not seguridad.dentro_de(destino, [config.BOVEDA]):
        raise ValueError("Ruta fuera de la boveda")
    if not destino.exists():
        raise FileNotFoundError(f"No existe la nota: {ruta_relativa}")

    texto = destino.read_text(encoding="utf-8", errors="ignore")
    if len(texto) > config.MAX_CHARS_NOTA:
        texto = texto[: config.MAX_CHARS_NOTA] + "\n\n[...nota recortada...]"
    return texto


def _validar_destino(ruta_relativa: str) -> "Path":
    """
    Valida que una ruta sea escribible: dentro de la boveda, .md, y en Wiki/.
    Fuentes/ es inmutable por regla de la boveda: ahi solo entran documentos crudos
    que pone Brian, no cosas generadas.
    """
    from pathlib import Path

    if not ruta_relativa.endswith(".md"):
        raise ValueError("Solo se pueden escribir archivos .md")

    destino = (config.BOVEDA / ruta_relativa).resolve()
    if not seguridad.dentro_de(destino, [config.BOVEDA]):
        raise ValueError("Ruta fuera de la boveda")
    if destino.is_symlink():
        raise ValueError("El destino es un enlace simbolico. No escribo ahi.")

    partes = Path(ruta_relativa).parts
    if not partes or partes[0] != "Wiki":
        raise ValueError(
            "Solo se puede escribir dentro de Wiki/. Fuentes/ es inmutable y la raiz "
            "esta reservada para index.md, log.md y CLAUDE.md."
        )
    return destino


def crear_nota(ruta_relativa: str, contenido: str, sobrescribir: bool = False) -> str:
    """Crea una nota nueva en Wiki/. Por defecto no pisa una existente."""
    destino = _validar_destino(ruta_relativa)

    if destino.exists() and not sobrescribir:
        raise FileExistsError(
            f"Ya existe {ruta_relativa}. Usa agregar_a_nota para ampliarla, "
            "o sobrescribir=True si de verdad queres reemplazarla."
        )

    if not contenido.lstrip().startswith("#"):
        raise ValueError("La nota debe empezar con un titulo H1 (# Titulo)")

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido.rstrip() + "\n", encoding="utf-8")
    return f"Nota creada: {ruta_relativa} ({len(contenido)} caracteres)"


def agregar_a_nota(ruta_relativa: str, contenido: str) -> str:
    """Agrega contenido al final de una nota existente."""
    destino = _validar_destino(ruta_relativa)
    if not destino.exists():
        raise FileNotFoundError(f"No existe {ruta_relativa}. Usa crear_nota primero.")

    actual = destino.read_text(encoding="utf-8").rstrip()
    destino.write_text(actual + "\n\n" + contenido.strip() + "\n", encoding="utf-8")
    return f"Contenido agregado a {ruta_relativa}"


def registrar_en_log(descripcion: str, tipo: str = "ingest") -> str:
    """
    Agrega una linea al log.md de la boveda, arriba de todo como pide su formato:
    `AAAA-MM-DD - tipo - descripcion`, mas reciente primero.
    """
    from datetime import date

    log = config.BOVEDA / "log.md"
    if not log.exists():
        raise FileNotFoundError("No existe log.md en la boveda")

    texto = log.read_text(encoding="utf-8")
    entrada = f"- {date.today().isoformat()} — {tipo} — {descripcion.strip()}\n"

    # Insertar antes de la primera entrada existente (la primera linea que empieza con "- ")
    lineas = texto.splitlines(keepends=True)
    for i, linea in enumerate(lineas):
        if linea.startswith("- "):
            lineas.insert(i, entrada)
            break
    else:
        lineas.append("\n" + entrada)

    log.write_text("".join(lineas), encoding="utf-8")
    return f"Registrado en log.md: {descripcion[:80]}"


def reindexar() -> str:
    """
    Corre el indexador de la boveda para que lo recien escrito quede buscable.
    Tambien limpia el cache en memoria para que la proxima busqueda lo vea.
    """
    global _cache, _bm25, _navegacion
    import subprocess

    script = config.BOVEDA / "RAG" / "index_vault.py"
    if not script.exists():
        raise FileNotFoundError(f"No encuentro {script}")

    r = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, timeout=600, cwd=str(config.BOVEDA),
        encoding="utf-8", errors="ignore",
    )
    _cache = None       # forzar recarga del indice actualizado
    _bm25 = None        # el indice de palabras tambien queda viejo
    _navegacion = None

    salida = (r.stdout or "").strip().splitlines()
    return salida[-1] if salida else "Reindexado (sin salida)"


def listar_notas(filtro: str = "") -> list[str]:
    """Lista las rutas de las notas de la boveda, opcionalmente filtradas."""
    rutas = []
    for carpeta in ("Wiki", "Fuentes"):
        base = config.BOVEDA / carpeta
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.md")):
            rel = str(p.relative_to(config.BOVEDA))
            if not filtro or filtro.lower() in rel.lower():
                rutas.append(rel)
    return rutas
