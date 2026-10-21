# Arquitectura de Nox

Este documento explica **cómo está pensado Nox y por qué**. Para instalarlo, ver
[`INSTALACION.md`](INSTALACION.md); para usarlo y sus límites de seguridad, el
[`README.md`](README.md); para lo que sigue, [`HOJA_DE_RUTA.md`](HOJA_DE_RUTA.md).

## Qué es

Un asistente de escritorio que **corre en el propio equipo**: conversa por texto o voz,
consulta una bóveda de notas, recuerda cosas entre sesiones, y controla el equipo (abrir
programas, volumen, archivos) dentro de límites estrictos. Funciona en Linux y en Windows.

Los modelos son de código abierto y corren localmente con Ollama: **Qwen3 8B** para conversar
y **nomic-embed-text** para buscar por significado. Para preguntas profundas que no tocan
nada personal puede usar opcionalmente un modelo grande en la nube (OpenRouter).

## Cómo viaja un mensaje

```
 voz (micrófono)                         texto (teclado)
      │  Whisper transcribe                    │
      └─────────────────┬──────────────────────┘
                        ▼
              ┌───────────────────┐
              │ enrutador.py      │  ¿acción, charla, normal o profundo?
              │                   │  ¿es personal? ¿puede salir de la PC?
              └────────┬──────────┘
          personal /   │   \ pregunta general y profunda
          acciones     │    ▼
                       │   nube.py ──► OpenRouter (solo 3 herramientas públicas,
                       │               sin memoria ni bóveda en el prompt)
                       ▼
              ┌───────────────────┐
              │ nucleo.py         │  ciclo: el modelo local (Ollama) pide
              │ Conversacion      │  herramientas → se ejecutan → vuelve el resultado
              └────────┬──────────┘
                       ▼
              ┌───────────────────┐      ┌────────────────────────────┐
              │ guardian.py       │ ───► │ herramientas.py (30)       │
              │ confirma, limita, │      │  sistema.py   programas,   │
              │ respalda, anota   │      │               archivos, web│
              └───────────────────┘      │  boveda.py    notas        │
                       ▲                 │  memoria.py   recuerdos    │
                       │                 │  documentos.py .docx / PDF │
              ┌────────┴──────────┐      │  juegos.py    horas Steam  │
              │ seguridad.py      │ ◄─── └────────────────────────────┘
              │ TODA la validación│
              └───────────────────┘
                       ▼
                 respuesta → pantalla y, si se habló, voz.py (Piper)
```

## Los módulos, por capas

| Capa | Archivos | Qué hacen |
|---|---|---|
| **Interfaces** | `gui.py`, `asistente.py` | Ventana (CustomTkinter) y versión de terminal. Las dos usan el mismo motor. |
| **Motor** | `nucleo.py`, `enrutador.py`, `nube.py` | Conversación, elección de esfuerzo y de ruta (local o nube), prompts. |
| **Herramientas** | `herramientas.py` | Cada una tiene un esquema que ve el modelo y una función real. |
| **Conocimiento** | `boveda.py`, `memoria.py`, `vocabulario.py` | Búsqueda en la bóveda (semántica + BM25), memoria persistente, vocabulario para la voz. |
| **Control del equipo** | `sistema.py`, `documentos.py`, `juegos.py`, `escanear_programas.py` | Lo que Nox hace sobre el equipo. |
| **Por sistema operativo** | `plataforma.py`, `so_linux.py`, `so_windows.py` | Lo único que cambia entre Linux y Windows. |
| **Voz** | `voz.py`, `vad.py` | Escuchar (faster-whisper), saber qué es voz (Silero VAD), hablar (Piper), palabra de activación. |
| **Seguridad** | `seguridad.py`, `guardian.py` | Qué se puede o no, y confirmaciones, límites y respaldos. |
| **Configuración** | `config.py`, `ajustes.py`, `config_local.json` | Parámetros del proyecto, **perfiles de equipo**, y los ajustes de cada persona (que se validan y guardan desde la interfaz). |
| **Interfaz de ajustes** | `ajustes_ui.py`, `bienvenida_ui.py`, `ui_comun.py`, `modelos.py`, `estilo.py` | Ventana de Ajustes, asistente de la primera vez, descarga de modelos, tono y trato. |
| **Herramientas externas** | `mcp_cliente.py` | Cliente MCP con lista blanca por herramienta. |
| **Iniciativa y percepción** | `recordatorios.py`, `vista.py` | Avisos y saludo (sin que lo llames); mirar la pantalla (con permiso). |
| **Memoria** | `memoria.py` | Recuerdos con uso, duplicados, olvido propuesto y resúmenes. |
| **Medición** | `evaluar_modelo.py`, `resultados_modelos/` | Mide modelos con las herramientas reales antes de adoptarlos. |

## Decisiones de diseño (y por qué)

### 1. Lista blanca, no lista negra
Una lista de cosas prohibidas siempre tiene agujeros: basta una forma de escribir el comando
que nadie previó. Nox al revés: solo puede abrir lo que está en `programas.json`, escribir en
carpetas permitidas y con extensiones permitidas, y ejecutar consultas de un conjunto cerrado.
Todo lo demás se rechaza. Y toda esa lógica vive en **un solo archivo** (`seguridad.py`) para
poder auditarlo de una lectura.

### 2. Las capacidades peligrosas no existen
No hay una herramienta para borrar archivos. No es que el modelo "se niegue": no puede, porque
la capacidad no está. `test_barreras.py` lo comprueba analizando el código (el árbol
sintáctico), no pidiéndole cosas al modelo.

### 3. La privacidad se garantiza por estructura
Lo personal nunca sale, y no porque el modelo se porte bien. Por el canal de la nube **no
existen** las herramientas de bóveda, memoria ni archivos; su prompt no lleva el perfil ni la
memoria; y hay un historial paralelo "limpio" con solo los turnos que nunca tocaron nada
personal. El detector de "esto es personal" está deliberadamente exagerado: un falso positivo
cuesta segundos; un falso negativo cuesta privacidad. `test_privacidad.py` lo verifica.

### 4. Esfuerzo proporcional
En un equipo modesto un modelo de 8B genera pocos tokens por segundo, así que la diferencia
entre un asistente agradable y uno insoportable es que **no divague**. `enrutador.py`
clasifica cada mensaje (`accion`, `charla`, `normal`, `profundo`) y ajusta cuánto razonar y
cuánto escribir. Se midió que un modelo más grande (14B) iba 3 veces más lento por
desbordarse a la RAM, así que se ajusta el esfuerzo del mismo modelo en vez de cambiarlo.

### 5. Dos sistemas operativos, una interfaz
`so_linux.py` y `so_windows.py` exponen **las mismas funciones** (abrir, listar y cerrar
ventanas, detectar un juego en curso, volumen, consultas). `sistema.py` elige uno al arrancar
y el resto del código no pregunta nunca qué sistema es. `test_plataforma.py` comprueba que
ambas interfaces sean idénticas y simula Windows para probar su lógica.

### 6. Cada persona, su Nox
Nada personal está escrito en el código. El nombre, la regla de trato, el perfil y la bóveda
salen de `config_local.json`. El perfil solo se le dice al modelo local, nunca a la nube. El
prompt se arma distinto según haya bóveda o no.

### 7. Los modelos se eligen midiendo, no por moda
Los modelos cambian cada pocos meses y uno "más nuevo" puede ser peor para lo que Nox necesita
(en la medición, `qwen3.5:9b` inventó la hora en vez de consultar la herramienta y acertó
solo 18 de 30 acciones). `evaluar_modelo.py` mide cada candidato con los pedidos reales de Nox y
aplica una regla fija: debe caber entero en la GPU, no caer en trampas de seguridad, y gana el
de más aciertos. Los **perfiles de equipo** (`config.PERFILES_EQUIPO`) agrupan el resultado por
hardware; uno solo se marca "medido" si se midió en ese equipo.

### 8. Cerrar no es borrar, y escribir se respalda
Antes de pisar un archivo, `guardian.py` guarda una copia y anota la acción en una bitácora.
Las acciones irreversibles piden confirmación a la persona. Hay un tope de acciones que
modifican cosas por turno, para cortar cadenas causadas por un modelo confundido o engañado
por una página web.

### 9. Se configura desde la interfaz, no editando archivos
Cambiar el perfil, el nombre o el tono no debería exigir abrir un editor. `ajustes.py` es la
única puerta para guardar: valida cada valor (un valor malo no guarda **nada**), escribe el
archivo de forma atómica (un corte de luz no lo deja a medias), conserva lo que no conoce, y le
avisa a `config.recargar()` para que se aplique al instante y sin borrar la conversación. La
ventana y el asistente de bienvenida solo *llaman* a ese módulo, así que se prueban sin
interfaz. Lo personal del perfil solo llega al modelo local.

### 10. Lo externo (MCP) es lista blanca, no confianza
Un servidor MCP es código de terceros. `mcp_cliente.py` lo trata como a todo lo demás en Nox: **nada
corre sin permiso explícito, por herramienta**. Nace apagado, cada herramienta nace bloqueada, las
de alto riesgo nunca quedan en «permitir», el modelo no ve lo bloqueado ni puede invocarlo por su
nombre, el resultado se marca como dato de un tercero, y el servidor no hereda tus claves. Pasa por
el mismo `guardian.py` que las herramientas propias (límite por turno, confirmación, bitácora). Y
una regla aprendida midiendo: **un resultado de herramienta tiene que ser honesto sobre lo que no
entrega** (`abrir_web` ahora avisa que no devolvió el contenido), porque un modelo chico rellena
los vacíos inventando.

### 11. Lo que actúa por su cuenta o ve tu pantalla viene APAGADO
Tres capacidades cambian la relación con Nox: que te hable sin llamarlo (saludo de la mañana), que mire
tu pantalla, y que guarde resúmenes de tus conversaciones. Las tres vienen **apagadas** y se activan una a una
en Ajustes: Nox no se vuelve más intrusivo hasta que lo decides. Las que miran o guardan cosas tuyas pasan
además por el guardián (permiso, límite por turno, bitácora) y nunca por la nube. Lo que sí está encendido por
defecto es lo que pediste tú explícitamente: los recordatorios que programas.

### 12. Medir antes de "mejorar" (y aceptar cuando no hace falta)
Cuatro de las fases planeadas se cerraron con una medición. Una de ellas (la búsqueda en tus notas) terminó con
«no cambies nada»: los modelos de embeddings más nuevos y el re-ranking no mejoraron una tubería que ya
combina semántica y palabras, y costaban de 3 a 6 veces más. Que una mejora *plausible* no valga la pena también
es un resultado, y está documentado (`HOJA_DE_RUTA.md`, 7.5).

### 13. Todo gratuito y local por defecto
Sin claves de API ni cuotas para lo esencial: el único techo es el hardware. La nube es un
extra opcional.

## Dónde mirar según lo que quieras cambiar

| Quiero... | Voy a... |
|---|---|
| Agregar una herramienta | `herramientas.py`: función + esquema en `ESQUEMAS` + registro en `DESPACHADOR`. Si toca el equipo, validar en `seguridad.py`. |
| Cambiar la personalidad | `construir_system_prompt()` en `nucleo.py`. |
| Cambiar de modelo | `config_local.json` (`modelo_chat`) o `MODELO_CHAT` en `config.py`. |
| Soportar otro sistema operativo | Un `so_<sistema>.py` con la misma interfaz que los otros dos. |
| Cambiar qué puede escribir | `CARPETAS_ESCRITURA` y `EXTENSIONES_ESCRITURA` en `config.py`, y correr los tests. |

## Cómo se verifica

`python probar_todo.py` corre cinco grupos de pruebas, sin necesitar Ollama ni internet:
seguridad, barreras que no se saltean, privacidad, compatibilidad Linux/Windows y nombre de
usuario. Regla del proyecto: **después de tocar permisos, correrlas.**
