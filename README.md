# ZIX-PC

Asistente personal de IA por voz para Windows (inspirado en JARVIS). **Fase v0.2: asistente por voz funcionando.**

> ZIX es un asistente de voz: `Micrófono → Wake Word → STT → Agent → Tools → TTS → Altavoz`.
> La CLI de texto (`python -m zix.main`) sigue disponible como adaptador de pruebas.

## Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│                     ZIX (v0.2)                          │
│   Micrófono → Wake Word → STT → Agent → Tool Router    │
│        │                                 │              │
│        └── VAD ─────────────── TTS ◄─────┘              │
│        Altavoz ◄─────────── (Piper local)               │
└─────────────────────────────────────────────────────────┘

v0.2 (actual):  Voz → ConversationManager → Agent → Groq API → Piper → Altavoz
                + modo conversación temporal (10 s) + reactivación por wake word
```

- `AIProvider` — interfaz del proveedor de IA. El núcleo **nunca importa `groq`**; `GroqProvider` es la única clase que lo usa. Permitirá cambiar a Ollama/otros sin reescribir.
- `Agent` — bucle de agente: decide si necesita herramientas, las ejecuta, devuelve el resultado al modelo y repite hasta completar la tarea (máx. `MAX_AGENT_ITERATIONS`). Es **agnóstico de I/O**: recibe texto, devuelve texto; conserva el historial de conversación entre turnos.
- `ToolRegistry` — registro central de herramientas (nombre, descripción, esquema JSON, función, metadatos).
- `ToolExecutor` — valida argumentos y ejecuta de forma uniforme. Los errores de herramientas **no se ocultan**: vuelven al modelo como mensajes `tool` para que decida una alternativa o explique al usuario.
- Voz (v0.2) — todo bajo `src/zix/voice/`, intercambiable vía interfaces:
  - `WakeWordProvider` / `OpenWakeWordProvider` — wake word propio `zix.onnx` (openWakeWord, 100% local, entrenado en Colab y verificado 0.7457 > 0.5). Respaldo: `hey_jarvis`.
  - `STTProvider` / `GroqSTTProvider` — Whisper de Groq (`whisper-large-v3-turbo`, español).
   - `TTSProvider` / `PiperTTSProvider` — Piper local (`es_MX-claude-high`), sin red, ~3 s por frase.
  - `VAD` — detección de habla por RMS; descarta falsos positivos (< 0.3 s).
  - `ConversationManager` — máquina de estados (IDLE/LISTENING/THINKING/SPEAKING/CONVERSATION). Tras responder, ZIX sigue escuchando **10 s**; una orden válida reinicia la ventana. El wake word reactiva ZIX en cualquier momento. Una "orden válida" es cualquier transcripción con intención comunicativa dirigida a ZIX (≥ 2 caracteres, con palabras); silencio, ruido, STT vacío o frases ininteligibles **no** reinician la ventana. No exige `tool_call`.
- Preparado para MCP: cuando se integre, un adaptador envolverá cada herramienta MCP como un `Tool` y se registrará en el mismo `ToolRegistry`.

## Requisitos

- Windows 10/11
- Python 3.12+ (probado con 3.14; 3.12 es el mínimo real de las dependencias fijadas)
- Micrófono y altavoz (solo para `python -m zix.voice_main`)
- **Una** de estas dos para el cerebro de ZIX:
  - **Ollama local** (recomendado en este equipo): sin cuota, sin tokens y
    sin que salga nada de internet. Instala Ollama, `ollama pull
    openbmb/minicpm-v4.6` y pon `AI_PROVIDER=ollama` en `.env`.
  - **API key gratuita de Groq**: <https://console.groq.com> (sin tarjeta)

### Motor local con Ollama

```powershell
ollama pull openbmb/minicpm-v4.6   # el único de los tres locales que
                                    # emite tool calls de verdad
```

El agente de ZIX vive de las tools, así que el modelo tiene que saber
llamarlas. De los modelos instalados en este equipo, **solo
`openbmb/minicpm-v4.6` las usa**: `phi4-mini` las ignora y `qwen2.5-coder`
devuelve el JSON como texto. Con esos dos, ZIX contesta pero no puede hacer
nada.

En CPU va lento (~7 palabras/s) y el primer turno tarda más, porque el modelo
pesa 1,5 GB y hay que cargarlo en RAM.

## Instalación

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
python scripts/setup_voice_models.py   # descarga respaldo hey_jarvis + voz Piper + espeak-ng; verifica zix.onnx propio (viaja con el repo)
```

## Configuración

```powershell
Copy-Item .env.example .env
# Elige cerebro:
#   AI_PROVIDER=ollama   -> motor local, sin clave y sin cuota
#   AI_PROVIDER=groq     -> nube, necesitas GROQ_API_KEY
```

La clave se lee **solo** desde `.env` (ignorado por git). Nunca se escribe en el código.

Todas las opciones de voz tienen valores por defecto sensatos en `.env.example` (volumen del VAD, tiempos de silencio, duración máxima de frase, ventana de conversación, modelos, etc.).

## Ejecutar

### Asistente por voz (v0.2)

```powershell
python -m zix.voice_main
```

Di **"Hey ZIX"** para activarme. Ejemplo:

```
Tú (voz): Hey ZIX, calcula 25 por 48
ZIX (voz): El resultado es 1200.
Tú (voz, sin wake word): ¿y cómo se hace?
ZIX (voz): [responde dentro de la ventana de 10 s]
```

### CLI temporal de pruebas (v0.1)

```powershell
python -m zix.main
```

```
Tú: Calcula 25 por 48.
ZIX: El resultado es 1200.
Tú: Abre Chrome.
ZIX: Abierta: chrome.
```

## Grabar tu voz para el wake word (Hey ZIX)

El wake word es lo único que **no se puede descargar**: hay que grabarlo.
El grabador te guía: te dice qué condición falta, pulsas Enter, dices «Hey ZIX»
y **valida el clip solo** (duración, nivel, saturación y que haya voz
detectada con el VAD de Silero). Lo que grabes mal te lo pide otra vez.

```powershell
python scripts/wakeword_training/grabar_clips.py --persona <tu-etiqueta>
```

| Opción | Para qué |
|---|---|
| `--persona` | Tu etiqueta en el nombre del fichero (`heyzix_<persona>_...`). Usa la que quieras: identifica al hablante, no se publica |
| `--destino` | Dónde se guardan (por defecto `data/wakeword_real/`) |
| `--segundos` | Duración de cada clip (por defecto 3 s) |
| `--objetivo` | Clips por condición (por defecto 3) |
| `--dispositivo` | Si hay varios micros,substring del nombre |

**La matriz que cubre** (3 sitios × 3 distancias × 3 fondos): cuarto
silencioso, cocina con eco y ventana con tráfico de calle; y de cerca
(~0,5 m), medio (1-2 m) y lejos (3-5 m). Con `--objetivo 3` son unos 27
clips. **La variedad importa más que la cantidad**: 30 clips bien repartidos
valen más que 100 en el mismo sitio.

**Privacidad:** la voz es un dato biométrico. Los clips se quedan en tu
equipo (`data/wakeword_real/` está en `.gitignore` y nunca se versionan).
Solo se subirían a Colab para entrenar, y solo si tú lo decides.

## Tests

```powershell
pip install -e ".[dev]"
python -m pytest
```

Prueba de integración real (opt-in, no la toca pytest; requiere `.env` con clave y modelos descargados):

```powershell
python scripts/integration_test_voice.py   # Piper → WAV → STT → texto + wake word
python scripts/integration_test_agent.py   # tool calling real del Agent
```

## Modelos de Groq usados (proveedor por defecto)

| Rol | Modelo | Free tier | Tool calling |
|---|---|---|---|
| Principal | `qwen/qwen3.6-27b` | ✔ | ✔ |
| Respaldo (rate limit) | `openai/gpt-oss-20b` | ✔ | ✔ |
| STT (voz) | `whisper-large-v3-turbo` | ✔ | — |

## Proveedor alternativo: xKiro (v0.3)

ZIX puede usar [xKiro](https://xkiro.com) (gateway OpenAI-compatible con
40+ modelos gratis, sin tarjeta) en vez de Groq. El núcleo no cambia:
`XkiroProvider` implementa la misma interfaz `AIProvider` (solo `urllib`,
sin SDK) y se elige con `AI_PROVIDER` en `.env`:

```
AI_PROVIDER=xkiro
XKIRO_API_KEY=<tu clave de xkiro.com → Console → API Keys>
XKIRO_MODEL=qwen/qwen3.8-max:free
XKIRO_FALLBACK_MODEL=minimax/minimax-m3:free
```

Gratis con tool calling (verificado en `GET api.xkiro.com/v1/models`):
`qwen/qwen3.8-max:free`, `mistralai/mistral-small-2603`,
`minimax/minimax-m3:free`, `qwen/qwen3-coder-plus:free`,
`mistralai/devstral-medium`.
El STT de voz sigue en Groq Whisper. `opencode.json` también trae xKiro
como proveedor custom (modelos gratis de código); tras reiniciar opencode,
pon tu key con `/connect` o `XKIRO_API_KEY` y elige modelo con `/models`.

*Verificados vía API el 19/08/2026 con `models.list()` de la cuenta: los modelos `llama-3.3-70b-versatile`/`llama-3.1-8b-instant` ya no están disponibles y devuelven `404 model_not_found`.*

## Resultado de la prueba de integración (voz, real)

Ejecución manual (opt-in): `python scripts/integration_test_voice.py`

```
[OK] 1. Modelos presentes (voz, config y espeak-ng-data).
[OK] 2. Piper sintetizó 'Esto es una prueba de voz de ZIX.' (22050 Hz, 68352 muestras).
[OK] 3. STT transcribió el audio sintetizado: 'Esto es una prueba de voz de Zetaidikis.'
[OK] 4. Wake word hey_jarvis cargado y procesa silencio sin dispararse.
PRUEBA DE INTEGRACIÓN DE VOZ SUPERADA.
```

**Nota (Windows, bug conocido):** el espeak-ng incluido en el wheel de piper-tts **no puede leer sus datos desde rutas con caracteres no-ASCII** (p. ej. `Imágenes` en la ruta de este proyecto). `setup_voice_models.py` copia los datos a `%LOCALAPPDATA%\zix\espeak-ng-data` (siempre ASCII) y `PiperTTSProvider` los pasa explícitamente. Si mueves el proyecto a una ruta ASCII, puedes volver a apuntar `PIPER_ESPEAK_DATA_DIR` al paquete.

## Resultado de la prueba de integración (tool calling real)

Ejecución manual con la API real (opt-in, separada de `pytest`): `python scripts/integration_test_agent.py`

Tarea: *"Calcula 25 por 48"* — flujo verificado:

```
Groq recibió las herramientas          → [get_current_time, calculator, echo, open_app]
Groq generó tool_call                 → calculator("25 * 48")
ToolExecutor ejecutó                  → calculator → "1200"
Resultado devuelto al Agent           → mensaje 'tool' con "1200"
Respuesta final de ZIX                → "El resultado es 1200."
Ninguna herramienta no solicitada     → ✔
```

**Resultado: PRUEBA DE INTEGRACIÓN SUPERADA (19/08/2026).**

## Herramientas v0.1 (solo seguras)

`get_current_time`, `calculator` (evaluación segura por AST, sin `eval()`), `echo`, `open_app` (lista blanca; rechaza cualquier aplicación no permitida y nunca ejecuta comandos arbitrarios).

## Roadmap (pendiente de aprobación)

Fases posteriores: MCP, Playwright, control de Windows, memoria, permisos, integración con ZXIA Android. El wake word propio `zix.onnx` ya está entrenado, verificado e integrado.

## Pruebas

```powershell
python -m pytest tests/   # 158 pruebas: agente, audio, conversación, VAD, registry, calculator + UI
```

## Estructura

- `src/zix/` — `main.py` (CLI), `voice_main.py` (voz), `core/` (agente+tools), `voice/` (audio, conversación, providers), `tools/`, `config.py`
- `scripts/` — `setup_voice_models.py`, `integration_test_*.py` (manuales), `wakeword_training/`
- `tests/` — suite pytest · `models/` `runtime/` `.venv/` — locales, ignorados por git
- `docs/` — `SESSION_STATE.md`, informes técnicos (PDF), `TEAM_WORKFLOW.md`
- `apps/zix-ui/` — pantallas de la app migradas desde el proyecto `zix app` de Open Design (fuente visual oficial):
  `zix-login.html`, `zix-config.html`, `zix-home-tarjeta.html`.
  Flujo `LOGIN → DESCARGA → CONFIGURACIÓN → HOME → CHAT`; Chat (`zix-main.html`) está pendiente.
  `index.html` es una maqueta antigua de Stitch y **no** es fuente de verdad.
  La UI es visual: sin backend, sin captura real de voz y sin datos inventados (los estados vacíos son honestos).

## Documentación

- `docs/TEAM_WORKFLOW.md` — flujo Git/GitHub y trabajo en equipo.
- `docs/SESSION_STATE.md` — instantánea operativa del proyecto.
- Wiki Obsidian (vault externo `ZIXVault`) y grafo `graphify-out/` como base de conocimiento.

## Flujo de trabajo Git

`main` es la rama estable: no se desarrolla directamente sobre ella. Una rama por tarea (`cristian/...`), commits pequeños, `push`, Pull Request con revisión y merge. Detalle completo en `docs/TEAM_WORKFLOW.md`.
