"""
Pruebas de la memoria (memoria.py): uso, duplicados, olvido propuesto, resumenes de sesion y
cambio de modelo de embeddings.

    python test_memoria.py

No necesita Ollama: los vectores se reemplazan por unos falsos (bolsa de palabras), asi dos textos
que comparten palabras se parecen y dos que no, no. Todo en una carpeta temporal.
"""
import hashlib
import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import numpy as np
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8")

import config
import memoria

fallos = []


def check(descripcion, condicion):
    if not condicion:
        fallos.append(descripcion)
    print(f"  [{'OK ' if condicion else 'FALLA'}] {descripcion}")


def vector_falso(texto: str) -> np.ndarray:
    """Bolsa de palabras en 128 dimensiones: textos con palabras en comun tienen vectores parecidos."""
    v = np.zeros(128, dtype=np.float32)
    for palabra in texto.lower().replace(",", " ").replace(".", " ").split():
        v[int(hashlib.md5(palabra.encode()).hexdigest(), 16) % 128] += 1
    return v


tmp = tempfile.TemporaryDirectory()
db = Path(tmp.name) / "memoria.db"
parches = [mock.patch.object(config, "MEMORIA_DB", db), mock.patch.object(memoria, "_embed", vector_falso),
           mock.patch.object(config, "UMBRAL_MEMORIA", 0.3)]
for p in parches:
    p.start()


def poner_fecha(id_, dias_atras):
    conn = sqlite3.connect(db)
    conn.execute("UPDATE recuerdos SET fecha = ? WHERE id = ?",
                 ((datetime.now() - timedelta(days=dias_atras)).isoformat(timespec="seconds"), id_))
    conn.commit()
    conn.close()


print("=== Una base de datos de antes se migra sin perder nada ===")
conn = sqlite3.connect(db)
conn.execute("CREATE TABLE recuerdos (id INTEGER PRIMARY KEY AUTOINCREMENT, contenido TEXT NOT NULL, categoria TEXT NOT NULL, fecha TEXT NOT NULL, embedding BLOB NOT NULL)")
conn.execute("INSERT INTO recuerdos (contenido, categoria, fecha, embedding) VALUES (?, ?, ?, ?)",
             ("le gusta el cafe sin azucar", "preferencia", "2026-01-01T10:00:00", vector_falso("le gusta el cafe sin azucar").tobytes()))
conn.commit()
conn.close()
viejo = memoria.listar()
check("el recuerdo viejo sigue ahi", len(viejo) == 1 and viejo[0]["contenido"] == "le gusta el cafe sin azucar")
check("con las columnas nuevas en sus valores por defecto", viejo[0]["usos"] == 0 and viejo[0]["origen"] == "usuario")

print("\n=== Guardar y buscar ===")
check("guarda un recuerdo nuevo", memoria.guardar("tiene un gato llamado Miso", "dato").startswith("Recordado"))
check("no duplica lo casi identico", memoria.guardar("tiene un gato llamado Miso", "dato").startswith("Ya recordaba"))
res = memoria.buscar("gato llamado", 3)
check("encuentra por palabras en comun", res and "Miso" in res[0]["contenido"])
check("anota que ese recuerdo SE USO", next(r for r in memoria.listar() if "Miso" in r["contenido"])["usos"] == 1)
memoria.buscar("gato llamado", 3)
check("y cuenta cada vez", next(r for r in memoria.listar() if "Miso" in r["contenido"])["usos"] == 2)
check("lo que no salio en la busqueda no suma usos", next(r for r in memoria.listar() if "cafe" in r["contenido"])["usos"] == 0)
check("la busqueda de algo sin relacion no devuelve nada", memoria.buscar("astronomia cuantica", 3) == [])

print("\n=== Lo que Nox sabe al empezar (contexto) ===")
memoria.guardar("no le gusta que le digan jefe", "correccion")
memoria.guardar("va a una reunion el lunes", "dato")
ctx = memoria.contexto_inicial()
check("lleva el nombre de quien usa Nox, no uno fijo", config.USUARIO.upper() in ctx.splitlines()[0] and "BRIAN" not in ctx.splitlines()[0].replace(config.USUARIO.upper(), ""))
lineas = [l for l in ctx.splitlines()[1:]]
check("las correcciones van primero", "(correccion)" in lineas[0])
check("lo que se usa sube sobre lo que no (el gato, usado, antes que la reunion)",
      next(i for i, l in enumerate(lineas) if "Miso" in l) < next(i for i, l in enumerate(lineas) if "reunion" in l))
check("las preferencias pesan mas que los datos sueltos",
      next(i for i, l in enumerate(lineas) if "cafe" in l) < next(i for i, l in enumerate(lineas) if "reunion" in l))
for i in range(40):
    memoria.guardar(f"dato numero {i} sobre tema{i} distinto{i}", "dato")
ctx = memoria.contexto_inicial(limite=100, max_chars=500)
check(f"con muchos recuerdos, el contexto se acota por largo ({len(ctx)} caracteres)", len(ctx) < 700)
check("y sigue siendo lo mas importante primero", "(correccion)" in ctx.splitlines()[1])

print("\n=== Duplicados: se proponen, no se borran solos ===")
memoria.guardar("le encanta el cafe con leche en las mananas", "dato")
memoria.guardar("le encanta el cafe con leche por las mananas", "dato")
ds = memoria.candidatos_duplicados(0.85)
check("encuentra los casi iguales", any("cafe con leche" in d["a"]["contenido"] and "cafe con leche" in d["b"]["contenido"] for d in ds))
check("cada recuerdo aparece en un solo par", len({d["a"]["id"] for d in ds} | {d["b"]["id"] for d in ds}) == 2 * len(ds))
check("proponer no borra nada", len([r for r in memoria.listar() if "cafe con leche" in r["contenido"]]) == 2)
par = next(d for d in ds if "cafe con leche" in d["a"]["contenido"])
a, b = par["a"], par["b"]
memoria.buscar("cafe con leche mananas", 1)
mem_antes = {r["id"]: r["usos"] for r in memoria.listar()}
check("fusionar deja uno solo", memoria.fusionar(a["id"], b["id"]).startswith("Fusionados"))
check("conserva el que se pidio", [r["id"] for r in memoria.listar() if "cafe con leche" in r["contenido"]] == [a["id"]])
check("y le suma los usos del que se fue", next(r for r in memoria.listar() if r["id"] == a["id"])["usos"] == mem_antes[a["id"]] + mem_antes[b["id"]])
check("fusionar uno inexistente avisa", "ya no existe" in memoria.fusionar(a["id"], 99999))
check("fusionar consigo mismo no hace nada", "mismo" in memoria.fusionar(a["id"], a["id"]))

print("\n=== Olvido: solo propone lo viejo, sin uso, y que puede caducar ===")
todos = {r["contenido"]: r["id"] for r in memoria.listar()}
poner_fecha(todos["va a una reunion el lunes"], 200)          # dato viejo sin uso
poner_fecha(todos["le gusta el cafe sin azucar"], 400)        # preferencia vieja: no caduca
poner_fecha(todos["tiene un gato llamado Miso"], 300)         # viejo pero USADO: se queda
poner_fecha(todos["no le gusta que le digan jefe"], 500)      # correccion vieja: no caduca
cand = [r["contenido"] for r in memoria.candidatos_olvido()]
check("propone el dato viejo y sin uso", "va a una reunion el lunes" in cand)
check("NO propone una preferencia ni una correccion, por viejas que sean",
      "le gusta el cafe sin azucar" not in cand and "no le gusta que le digan jefe" not in cand)
check("NO propone lo que se ha usado", "tiene un gato llamado Miso" not in cand)
check("NO propone lo reciente", not any(f"dato numero {i}" in c for c in cand for i in range(40)))
check("proponer no borra nada", "va a una reunion el lunes" in [r["contenido"] for r in memoria.listar()])
e = memoria.estadisticas()
check("las estadisticas cuadran", e["total"] == len(memoria.listar()) and e["para_olvidar"] == len(memoria.candidatos_olvido()))

print("\n=== Resumen de una conversacion ===")
dichos = [{"role": "user", "content": t} for t in ("hola", "estoy aprendiendo rust este mes", "mañana presento mi proyecto final", "gracias")]
mensajes = [{"role": "system", "content": "..."}] + dichos + [{"role": "assistant", "content": "ok"}]
frases = memoria.resumir_sesion(mensajes, preguntar=lambda p: '["Esta aprendiendo Rust este mes", "Presenta su proyecto final mañana"]')
check("extrae lo que valia la pena", frases == ["Esta aprendiendo Rust este mes", "Presenta su proyecto final mañana"])
check("sin conversacion suficiente no resume (menos de 3 mensajes de la persona)", memoria.resumir_sesion(mensajes[:3], preguntar=lambda p: '["algo largo para guardar"]') == [])
check("tolera que el modelo hable de mas alrededor de la lista", memoria.resumir_sesion(mensajes, preguntar=lambda p: 'Claro:\n["Esta aprendiendo Rust este mes"]\nListo.') == ["Esta aprendiendo Rust este mes"])
check("tolera basura", memoria.resumir_sesion(mensajes, preguntar=lambda p: "no se que decir") == [])
check("descarta lo demasiado corto y limita a 3",
      len(memoria.resumir_sesion(mensajes, preguntar=lambda p: json.dumps(["ok", "uno largo uno", "dos largo dos", "tres largo tres", "cuatro largo 4"]))) == 3)
check("solo mira lo que dijo la persona (no lo que respondio Nox)",
      "ok" not in memoria.resumir_sesion(mensajes, preguntar=lambda p: (check("el pedido no incluye lo que dijo el asistente", "assistant" not in p and "ok" not in p.split("\n\n")[-1]) or "[]"))
      )
check("la instruccion de estilo pegada al mensaje no entra al resumen",
      "LARGO" not in str(memoria.resumir_sesion(
          [{"role": "user", "content": f"{t}\n\n[LARGO DE ESTA RESPUESTA: corto]"} for t in ("uno", "dos", "tres")],
          preguntar=lambda p: (check("el pedido no lleva la linea de estilo", "LARGO" not in p) or "[]"))))
n = memoria.guardar_resumen_de_sesion(mensajes, preguntar=lambda p: '["Esta aprendiendo Rust este mes"]')
guardado = next(r for r in memoria.listar() if "Rust" in r["contenido"])
check("se guarda como 'sesion' con origen 'resumen'", n == 1 and guardado["categoria"] == "sesion" and guardado["origen"] == "resumen")

print("\n=== Si cambia el modelo de embeddings, se recalculan ===")
conn = sqlite3.connect(db); conn.execute("DELETE FROM meta"); conn.commit(); conn.close()
cuantos = len(memoria.listar())
llamadas = []
def vector_v2(texto):
    llamadas.append(texto)
    return vector_falso(texto) * 2
with mock.patch.object(config, "MODELO_EMBED", "modelo-nuevo"), mock.patch.object(memoria, "_embed", vector_v2):
    check("recalcula todos los vectores guardados", memoria.asegurar_modelo() == cuantos and len(llamadas) == cuantos)
    llamadas.clear()
    check("y no vuelve a hacerlo si el modelo es el mismo", memoria.asegurar_modelo() == 0 and not llamadas)
with mock.patch.object(config, "MODELO_EMBED", "otro-mas"), \
        mock.patch.object(memoria, "_embed", side_effect=requests.ConnectionError("Ollama apagado")):
    check("si Ollama no responde, no rompe ni recalcula a medias", memoria.asegurar_modelo() == 0)
    check("y la memoria sigue legible", len(memoria.listar()) == cuantos)

tmp.cleanup()
for p in parches:
    p.stop()
print("\n" + "=" * 60)
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("TODAS LAS PRUEBAS DE MEMORIA PASARON")
