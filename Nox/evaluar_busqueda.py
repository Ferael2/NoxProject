"""
Mide que tan bien encuentra Nox las respuestas en tu boveda, con distintos modelos de embeddings.

    python evaluar_busqueda.py                       # arma consultas (una vez) y compara las variantes
    python evaluar_busqueda.py --consultas 80        # cuantas consultas generar
    python evaluar_busqueda.py --rerank              # ademas prueba reordenar los resultados con un LLM

Como funciona la medicion:
  1. Toma fragmentos reales de tu boveda y le pide a un LLM local (qwen3:8b) que escriba, para cada
     uno, la pregunta que alguien haria y cuya respuesta esta ahi. Asi se sabe CUAL es la respuesta
     correcta sin que nadie tenga que etiquetar nada. Las consultas se guardan y se reutilizan,
     para que todas las variantes se midan con las MISMAS preguntas.
  2. Por cada variante (modelo de embeddings + forma de usarlo) vuelve a calcular los vectores de
     todos los fragmentos EN MEMORIA y busca con la tuberia REAL de Nox (boveda.buscar: semantica +
     palabras + penalizaciones). No toca tu RAG/index.db.
  3. Cuenta en que puesto aparece la nota correcta: recall@1, @3, @5, @10 y MRR.

Limite que hay que tener presente: las preguntas las escribe un modelo y tienden a parecerse al
texto del que salen, lo que favorece a la busqueda por palabras. Sirve muy bien para COMPARAR
variantes entre si (todas tienen la misma ventaja); no dice cuanto aciertas con las preguntas
reales de una persona.
"""
import argparse
import json
import random
import re
import sqlite3
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

import boveda
import config
import modelos as modelos_ollama

SALIDA = Path(__file__).resolve().parent / "resultados_busqueda"
CONSULTAS = SALIDA / "consultas.json"
INSTRUCCION_QWEN = "Dada una pregunta, recupera los fragmentos de notas que la responden"

# nombre -> (modelo de Ollama, prefijo de documento, prefijo de consulta). 'None' = usar el indice actual.
VARIANTES = {
    "nomic (el actual)":        ("nomic-embed-text", None, None),
    "nomic + prefijos":         ("nomic-embed-text", "search_document: ", "search_query: "),
    "qwen3-emb 0.6b":           ("qwen3-embedding:0.6b", "", ""),
    "qwen3-emb 0.6b + instr.":  ("qwen3-embedding:0.6b", "", f"Instruct: {INSTRUCCION_QWEN}\nQuery: "),
    "qwen3-emb 4b + instr.":    ("qwen3-embedding:4b", "", f"Instruct: {INSTRUCCION_QWEN}\nQuery: "),
}
# El de 4B en CPU tarda mas de una hora en indexar y, en una tarjeta de 8 GB, no cabe junto al modelo
# de conversacion: solo se mide si se pide expresamente con --variantes.
POR_DEFECTO = [v for v in VARIANTES if "4b" not in v]


# --- Los fragmentos ---

def cargar_fragmentos() -> list[dict]:
    """Todos los fragmentos del indice de la boveda, en solo lectura (no se modifica nada)."""
    conn = sqlite3.connect(f"file:{config.INDICE_DB}?mode=ro", uri=True)
    filas = conn.execute("SELECT id, filepath, heading, content, embedding FROM chunks ORDER BY id").fetchall()
    conn.close()
    return [{"id": i, "archivo": f, "seccion": h or "", "contenido": c,
             "vector": np.frombuffer(b, dtype=np.float32)} for i, f, h, c, b in filas]


def texto_de_documento(f: dict) -> str:
    """Lo mismo que embebe el indexador de la boveda: 'nombre - seccion' + contenido."""
    nombre = Path(f["archivo"]).stem
    return f"{nombre} - {f['seccion']}\n{f['contenido']}" if f["seccion"] else f"{nombre}\n{f['contenido']}"


# --- Ollama ---

CACHE = SALIDA / "cache"


def embeber(modelo: str, textos: list[str], cpu: bool = False) -> np.ndarray:
    """
    Vectores de muchos textos (por lotes). Con cpu=True se fuerza a correr sin la tarjeta de video.
    Se guardan en resultados_busqueda/cache: calcular 944 fragmentos con un modelo grande en CPU
    tarda muchos minutos, y repetir la medicion no deberia costar eso otra vez.
    """
    import hashlib
    huella = hashlib.sha1((modelo + "\0" + "\0".join(textos)).encode()).hexdigest()[:20]
    archivo_cache = CACHE / f"{modelo.replace(':', '_').replace('/', '_')}_{len(textos)}_{huella}.npy"
    if len(textos) > 8 and archivo_cache.exists():
        return np.load(archivo_cache)
    salida = []
    for i in range(0, len(textos), 32):
        cuerpo = {"model": modelo, "input": textos[i:i + 32], "keep_alive": "10m"}
        if cpu:
            cuerpo["options"] = {"num_gpu": 0}
        r = requests.post(f"{config.OLLAMA_HOST}/api/embed", json=cuerpo, timeout=600)
        r.raise_for_status()
        salida.extend(r.json()["embeddings"])
    resultado = np.array(salida, dtype=np.float32)
    if len(textos) > 8:
        CACHE.mkdir(parents=True, exist_ok=True)
        np.save(archivo_cache, resultado)
    return resultado


def preguntar(prompt: str, modelo: str = None, max_tokens: int = 80) -> str:
    r = requests.post(config.CHAT_URL, json={
        "model": modelo or config.MODELO_CHAT, "stream": False, "think": False,
        "messages": [{"role": "user", "content": prompt}],
        "options": {"temperature": 0.3, "num_predict": max_tokens, "num_ctx": 4096},
        "keep_alive": "10m"}, timeout=300)
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


# --- Las consultas de prueba ---

def candidatos(fragmentos: list[dict]) -> list[dict]:
    """Fragmentos buenos para preguntar sobre ellos: de la wiki curada, con sustancia, no listas de enlaces."""
    buenos = []
    for f in fragmentos:
        c = f["contenido"]
        enlaces = sum(len(m) for m in re.findall(r"\[\[([^\]]*)\]\]", c))
        if (f["archivo"].startswith("Wiki") and 350 <= len(c) <= 1500 and len(c) > 0
                and f["seccion"].lower() not in ("relacionado", "indice", "índice") and enlaces / len(c) < 0.3):
            buenos.append(f)
    return buenos


PROMPTS = {
    "pregunta": ("una PREGUNTA natural, como la haria una persona hablando, cuya respuesta este en el fragmento. "
                 "Usa tus propias palabras: no copies frases del fragmento."),
    "palabras": ("una BUSQUEDA corta de 2 a 5 palabras, como si la escribieras en un buscador, para encontrar "
                 "este fragmento. No copies frases enteras."),
}


def generar_consultas(fragmentos: list[dict], cuantas: int, semilla: int = 7) -> list[dict]:
    """Consultas de prueba con su respuesta correcta. Se guardan: la proxima vez se reutilizan."""
    if CONSULTAS.exists():
        guardadas = json.loads(CONSULTAS.read_text(encoding="utf-8"))
        print(f"Reutilizo {len(guardadas)} consultas de {CONSULTAS.name} (borra el archivo para regenerarlas).")
        return guardadas

    azar = random.Random(semilla)
    buenos = candidatos(fragmentos)
    # Un fragmento por nota como mucho: asi no pesa mas una nota con muchas secciones.
    por_nota = {}
    for f in buenos:
        por_nota.setdefault(f["archivo"], []).append(f)
    elegidos = [azar.choice(v) for v in por_nota.values()]
    azar.shuffle(elegidos)
    elegidos = elegidos[:cuantas]
    print(f"Generando {len(elegidos)} consultas a partir de {len(por_nota)} notas distintas…", flush=True)

    consultas = []
    for n, f in enumerate(elegidos):
        tipo = "palabras" if n % 3 == 2 else "pregunta"   # una de cada tres es de palabras clave
        texto = preguntar(
            f"Lees una nota de una wiki personal. Escribe {PROMPTS[tipo]}\n"
            "No menciones 'el fragmento', 'la nota' ni 'el texto'. Responde SOLO con la consulta, sin comillas.\n\n"
            f"Titulo de la nota: {Path(f['archivo']).stem}\nSeccion: {f['seccion']}\n\nFragmento:\n{f['contenido'][:1400]}")
        texto = texto.strip().strip('"«»').splitlines()[0].strip() if texto.strip() else ""
        if len(texto) >= 6:
            consultas.append({"id": f["id"], "archivo": f["archivo"], "seccion": f["seccion"],
                              "tipo": tipo, "consulta": texto})
        if (n + 1) % 20 == 0:
            print(f"  {n + 1}/{len(elegidos)}", flush=True)
    SALIDA.mkdir(exist_ok=True)
    CONSULTAS.write_text(json.dumps(consultas, ensure_ascii=False, indent=1), encoding="utf-8")
    return consultas


# --- Medir ---

def evaluar_variante(nombre: str, fragmentos: list[dict], consultas: list[dict], modo: str, cpu: bool = False) -> dict:
    modelo, pref_doc, pref_cons = VARIANTES[nombre]
    t = time.time()
    if pref_doc is None:   # el indice tal como esta hoy en tu boveda
        matriz = np.vstack([f["vector"] for f in fragmentos])
        tiempo_indice = 0.0
    else:
        matriz = embeber(modelo, [pref_doc + texto_de_documento(f) for f in fragmentos], cpu)
        tiempo_indice = time.time() - t
    matriz = matriz / (np.linalg.norm(matriz, axis=1, keepdims=True) + 1e-8)

    # Vectores de las consultas, de una vez (y su tiempo por consulta, de a una, para medir la latencia real).
    prefijo = pref_cons or ""
    vectores = embeber(modelo, [prefijo + c["consulta"] for c in consultas], cpu)
    por_consulta = {c["consulta"]: v for c, v in zip(consultas, vectores)}
    muestra = [consultas[i]["consulta"] for i in range(0, len(consultas), max(1, len(consultas) // 8))][:8]
    tiempos = []
    for q in muestra:
        t = time.time()
        embeber(modelo, [prefijo + q], cpu)
        tiempos.append((time.time() - t) * 1000)

    # La tuberia REAL de Nox, con esta matriz y estos vectores de consulta.
    boveda._cache = ([f["archivo"] for f in fragmentos], [f["seccion"] for f in fragmentos],
                     [f["contenido"] for f in fragmentos], matriz)
    boveda._bm25 = None
    boveda._navegacion = None
    original = boveda._embed
    boveda._embed = lambda texto: por_consulta[texto]
    try:
        rangos = []
        for c in consultas:
            res = boveda.buscar(c["consulta"], top_k=10, modo=modo)
            rango = next((i + 1 for i, r in enumerate(res) if r["archivo"] == c["archivo"]), None)
            rango_seccion = next((i + 1 for i, r in enumerate(res)
                                  if r["archivo"] == c["archivo"] and r["seccion"] == c["seccion"]), None)
            rangos.append({"tipo": c["tipo"], "rango": rango, "rango_seccion": rango_seccion})
    finally:
        boveda._embed = original
        boveda._cache = boveda._bm25 = boveda._navegacion = None

    return {"variante": nombre, "modo": modo, "cpu": cpu, "rangos": rangos,
            "ms_consulta": round(statistics.median(tiempos), 1), "s_indice": round(tiempo_indice, 1)}


def latencia_ms(modelo: str, prefijo: str, consultas: list[dict], cpu: bool, cuantas: int = 6) -> float:
    """Milisegundos que tarda UNA consulta (mediana de unas pocas), en GPU o forzando la CPU."""
    muestra = [c["consulta"] for c in consultas[:cuantas]]
    embeber(modelo, [prefijo + muestra[0]], cpu)   # calentamiento: la primera carga el modelo
    tiempos = []
    for q in muestra:
        t = time.time()
        embeber(modelo, [prefijo + q], cpu)
        tiempos.append((time.time() - t) * 1000)
    return round(statistics.median(tiempos), 1)


def metricas(rangos: list[dict], campo: str = "rango") -> dict:
    n = len(rangos)
    if not n:
        return {}
    en = lambda k: sum(1 for r in rangos if r[campo] and r[campo] <= k) / n
    return {"n": n, "r1": en(1), "r3": en(3), "r5": en(5), "r10": en(10),
            "mrr": sum(1 / r[campo] for r in rangos if r[campo]) / n}


def pct(x: float) -> str:
    return f"{100 * x:.0f} %"


# --- Re-ranking con un LLM ---

def reordenar_con_llm(consulta: str, resultados: list[dict], modelo: str, n: int = 8) -> list[dict]:
    """
    Reordena los primeros 'n' resultados preguntandole al LLM, uno por uno, si el fragmento responde
    la pregunta. Los que si, suben (sin perder el orden original entre ellos). Es lento: una llamada
    por candidato.
    """
    cabeza, cola = resultados[:n], resultados[n:]
    puntaje = []
    for i, r in enumerate(cabeza):
        respuesta = preguntar(
            "Responde SOLO 'si' o 'no'. ¿El siguiente fragmento contiene la respuesta a la pregunta?\n\n"
            f"Pregunta: {consulta}\n\nFragmento ({r['archivo']}):\n{r['contenido'][:900]}", modelo, max_tokens=3)
        puntaje.append((0 if respuesta.lower().startswith(("si", "sí")) else 1, i, r))
    return [r for _, _, r in sorted(puntaje, key=lambda t: (t[0], t[1]))] + cola


def evaluar_rerank(nombre: str, fragmentos, consultas, modelo_llm: str) -> dict:
    modelo, pref_doc, pref_cons = VARIANTES[nombre]
    matriz = (np.vstack([f["vector"] for f in fragmentos]) if pref_doc is None
              else embeber(modelo, [pref_doc + texto_de_documento(f) for f in fragmentos]))
    matriz = matriz / (np.linalg.norm(matriz, axis=1, keepdims=True) + 1e-8)
    vectores = embeber(modelo, [(pref_cons or "") + c["consulta"] for c in consultas])
    por_consulta = {c["consulta"]: v for c, v in zip(consultas, vectores)}
    boveda._cache = ([f["archivo"] for f in fragmentos], [f["seccion"] for f in fragmentos],
                     [f["contenido"] for f in fragmentos], matriz)
    boveda._bm25 = boveda._navegacion = None
    original = boveda._embed
    boveda._embed = lambda texto: por_consulta[texto]
    antes, despues, segundos = [], [], []
    try:
        for k, c in enumerate(consultas):
            res = boveda.buscar(c["consulta"], top_k=10, modo="hibrido")
            r0 = next((i + 1 for i, r in enumerate(res) if r["archivo"] == c["archivo"]), None)
            t = time.time()
            res2 = reordenar_con_llm(c["consulta"], res, modelo_llm)
            segundos.append(time.time() - t)
            r1 = next((i + 1 for i, r in enumerate(res2) if r["archivo"] == c["archivo"]), None)
            antes.append({"tipo": c["tipo"], "rango": r0})
            despues.append({"tipo": c["tipo"], "rango": r1})
            if (k + 1) % 10 == 0:
                print(f"  rerank {k + 1}/{len(consultas)}", flush=True)
    finally:
        boveda._embed = original
        boveda._cache = boveda._bm25 = boveda._navegacion = None
    return {"antes": antes, "despues": despues, "s_por_consulta": round(statistics.mean(segundos), 1)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Compara modelos de embeddings sobre tu boveda.")
    ap.add_argument("--consultas", type=int, default=70, help="cuantas consultas de prueba generar")
    ap.add_argument("--variantes", default="", help="nombres separados por ';' (por defecto, todas)")
    ap.add_argument("--rerank", action="store_true", help="probar tambien el reordenado con un LLM")
    ap.add_argument("--cpu", action="store_true", help="medir tambien la latencia con los embeddings en CPU")
    args = ap.parse_args()

    if not config.INDICE_DB.exists():
        print(f"No hay indice de boveda en {config.INDICE_DB}. Configura la boveda en Ajustes.")
        return 1
    fragmentos = cargar_fragmentos()
    print(f"{len(fragmentos)} fragmentos en {len({f['archivo'] for f in fragmentos})} notas.")

    consultas = generar_consultas(fragmentos, args.consultas)
    por_tipo = {t: sum(1 for c in consultas if c["tipo"] == t) for t in ("pregunta", "palabras")}
    print(f"{len(consultas)} consultas de prueba: {por_tipo}\n")

    nombres = [v.strip() for v in args.variantes.split(";") if v.strip()] or POR_DEFECTO
    resultados = []
    for nombre in nombres:
        modelo = VARIANTES[nombre][0]
        if modelo.split(":")[0] != "nomic-embed-text" and not any(
                m == modelo or m == f"{modelo}:latest" for m in modelos_ollama.instalados()):
            print(f"· {nombre}: falta el modelo {modelo} (ollama pull {modelo}). Se omite.")
            continue
        for modo in ("semantico", "hibrido"):
            print(f"· {nombre} [{modo}]…", flush=True)
            resultados.append(evaluar_variante(nombre, fragmentos, consultas, modo))
        if args.cpu and VARIANTES[nombre][1] is not None:
            resultados.append({"variante": nombre, "modo": "latencia", "cpu": True,
                               "ms_consulta": latencia_ms(modelo, VARIANTES[nombre][2] or "", consultas, cpu=True)})

    L = [f"# Evaluación de búsqueda — {datetime.now():%Y-%m-%d %H:%M}\n",
         f"{len(fragmentos)} fragmentos · {len(consultas)} consultas generadas por un LLM local ({por_tipo}). "
         "La nota correcta cuenta como acierto a nivel de archivo.\n",
         "## Tubería real de Nox (semántica + palabras)\n",
         "| Variante | Acierta a la 1ª | En las 3 primeras | En las 5 primeras | En las 10 primeras | MRR | ms por consulta | Indexar 944 fragmentos |",
         "|---|---|---|---|---|---|---|---|"]
    for r in resultados:
        if r["modo"] != "hibrido":
            continue
        m = metricas(r["rangos"])
        L.append(f"| {r['variante']} | {pct(m['r1'])} | {pct(m['r3'])} | {pct(m['r5'])} | {pct(m['r10'])} | "
                 f"{m['mrr']:.3f} | {r['ms_consulta']} | {r['s_indice'] or '—'} s |")
    L += ["\n## Solo semántica (sin palabras)\n", "| Variante | 1ª | 3 | 5 | 10 | MRR |", "|---|---|---|---|---|---|"]
    for r in resultados:
        if r["modo"] == "semantico":
            m = metricas(r["rangos"])
            L.append(f"| {r['variante']} | {pct(m['r1'])} | {pct(m['r3'])} | {pct(m['r5'])} | {pct(m['r10'])} | {m['mrr']:.3f} |")
    L += ["\n## Por tipo de consulta (acierta en las 3 primeras, tubería real)\n",
          "| Variante | Preguntas habladas | Búsquedas por palabras |", "|---|---|---|"]
    for r in resultados:
        if r["modo"] == "hibrido":
            p = metricas([x for x in r["rangos"] if x["tipo"] == "pregunta"])
            w = metricas([x for x in r["rangos"] if x["tipo"] == "palabras"])
            L.append(f"| {r['variante']} | {pct(p['r3'])} | {pct(w['r3']) if w else '—'} |")
    cpu = [r for r in resultados if r["modo"] == "latencia"]
    if cpu:
        L += ["\n## Latencia con los embeddings en CPU (para no quitarle la tarjeta al modelo de chat)\n",
              "| Variante | ms por consulta (CPU) |", "|---|---|"]
        L += [f"| {r['variante']} | {r['ms_consulta']} |" for r in cpu]

    if args.rerank and resultados:
        mejor = max((r for r in resultados if r["modo"] == "hibrido"),
                    key=lambda r: metricas(r["rangos"])["mrr"])
        print(f"\nRe-ranking con {config.MODELO_CHAT} sobre «{mejor['variante']}»…", flush=True)
        rr = evaluar_rerank(mejor["variante"], fragmentos, consultas, config.MODELO_CHAT)
        a, d = metricas(rr["antes"]), metricas(rr["despues"])
        L += [f"\n## Re-ranking con {config.MODELO_CHAT} (sobre «{mejor['variante']}»)\n",
              "| | 1ª | 3 | 5 | MRR | Tiempo extra por consulta |", "|---|---|---|---|---|---|",
              f"| Sin re-ranking | {pct(a['r1'])} | {pct(a['r3'])} | {pct(a['r5'])} | {a['mrr']:.3f} | — |",
              f"| Con re-ranking | {pct(d['r1'])} | {pct(d['r3'])} | {pct(d['r5'])} | {d['mrr']:.3f} | {rr['s_por_consulta']} s |"]
    informe = "\n".join(L) + "\n"
    print("\n" + informe)

    SALIDA.mkdir(exist_ok=True)
    base = SALIDA / f"{datetime.now():%Y-%m-%d_%H%M}"
    base.with_suffix(".md").write_text(informe, encoding="utf-8")
    base.with_suffix(".json").write_text(json.dumps(resultados, ensure_ascii=False), encoding="utf-8")
    print(f"Guardado en {base.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
