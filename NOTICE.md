# Atribuciones de terceros

ZIX está bajo **GPL-3.0-or-later** (ver `LICENSE`). Esa licencia no es una
decisión estética: está **forzada** por las dependencias. Ver la sección
"Por qué GPL" más abajo.

## Por qué GPL y no MIT/Apache

| Dependencia | Licencia | Efecto |
|---|---|---|
| **piper-tts** 1.7.0 | **GPL-3.0-or-later** | **Obliga a GPL.** `src/zix/voice/piper_tts.py:50` hace `from piper import PiperVoice` en tiempo de ejecución. |
| openwakeword 0.6.0 | Apache-2.0 | Compatible con GPL-3. |
| onnxruntime 1.29.0 | MIT | Compatible. |
| numpy / scipy / scikit-learn | BSD | Compatible. |
| python-dotenv | BSD-3-Clause | Compatible. |
| groq | Apache-2.0 | Compatible. |
| protobuf | BSD-3-Clause | Compatible. |
| requests / flatbuffers | Apache-2.0 | Compatible. |
| tqdm | MPL-2.0 AND MIT | Compatible (MPL es copyleft débil, file-level). |

Piper es el único copyleft fuerte, y es obligatorio: es el motor de síntesis de
voz. Si en el futuro se quiere publicar bajo MIT o Apache-2.0, **hay que
sustituir Piper** por un TTS con licencia permisiva (por ejemplo Coqui TTS,
CPML, o un modelo ONNX propio entrenado con datos libres). No hay otra vía.

## Datos usados para entrenar el wake word

El modelo `zix.onnx` **no se distribuye con este repositorio**. Cuando se
reentrene, estos son los conjuntos con los que se mezcló y sus licencias:

| Conjunto | Licencia | Nota |
|---|---|---|
| RIRs (MIT) | MIT | Reverb rooms, freely usable. |
| AudioSet | CC-BY 4.0 | Requiere atribución. |
| FMA | **CC-BY-NC** | **No comercial.** Cualquier modelo entrenado con él herrea esa restricción. |
| ACAV | research | Uso de investigación. |

> **Esto es una restricción seria.** Un modelo reentrenado con FMA o ACAV no
> debería publicarse como open source. Para un modelo publicable hay que
> quedarse solo con RIRs + AudioSet, o con voz humana propia más audio libre de
> licencia comercial.

## Recursos de terceros usados en tiempo de ejecución

- **Feature models de openWakeWord** (Apache-2.0, de
  `davidscripka/openwakeword_features`): `melspectrogram.onnx` y
  `embedding_model.onnx`. Los usa el runtime de openwakeword, no ZIX
  directamente. Se descargan con el paquete.
- **Silero VAD** (MIT), incluido dentro de openwakeword.
- **Modelos de voz de Piper** (`es_MX-claude-high`, `es_MX-ald-medium`).
  La licencia concreta de cada voz está en su `.onnx.json`; revísala antes de
  redistribuirlos. No se distribuyen con el repo.

## Verificación de terceros

- Inventario de CVEs consultado contra la API de OSV el 2026-10-03:
  **0 vulnerabilidades conocidas** en las 18 dependencias directas.
- `sounddevice 0.5.6` no pudo consultarse ese día (corte de conexión); repetir
  antes de una publicación.

## Aviso sobre "Hey Jarvis"

`hey_jarvis_v0.1.onnx` es un modelo preentrenado de openWakeWord (Apache-2.0) y
está en `.env` como `WAKE_WORD_MODEL` de reserva. **Escucha "Hey Jarvis", no
"Hey ZIX"**, y no se distribuye con el repo: lo baja openWakeWord a la caché
local.
