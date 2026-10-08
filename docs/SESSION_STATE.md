# Sesión ZIX / Hey ZIX — Estado guardado 2026-09-15 (pausa, se sigue mañana)

## Qué se hizo el 14-15/09/2026

**Voz TTS cambiada y verificada:** `es_MX-ald-medium` → `es_MX-claude-high`
(high, mismo acento mexicano, más fluida). Archivos en `models/piper/`
(ignorados por git, se regeneran). Cambiados: `src/zix/config.py`,
`.env` (PIPER_VOICE), `.env.example`, `scripts/setup_voice_models.py`
(ahora acepta cualquier voz `es_*` vía `_piper_base_url()`),
`src/zix/voice/piper_tts.py`, `README.md`. Verificado:
`integration_test_voice.py` SUPERADA + 60 pytest OK.

**Entreno Hey ZIX con audios reales (preparación local):**
- Notebook local `scripts/wakeword_training/train_hey_zix.ipynb`: 19 → 21
  celdas (nueva **4b** mezcla WAV reales en `zix_model/positive/`).
- Nuevo `data/wakeword_real/README.md` (protocolo 20-30 clips) +
  `scripts/wakeword_training/prepare_real_clips.py` (validador 16k/mono).
- `.gitignore`: `data/wakeword_real/*.wav` ignorados (privacidad).

**Colab (Drive `[id-de-drive-omitido]`, 373 celdas, login
[correo personal] OK, GPU T4):** notebook Drive actualizado y guardado
con los mismos fixes que el local. Celdas Datos 31/32/35 reescritas y
verificadas en verde el 14/09 (RIRs 270, audioset_16k 400, fma 130 vía
SoundHelix+ffmpeg tras muerte de FMA-datasets y del tar AudioSet→parquet,
LibriSpeech en vez de AudioSet, yaml OK).

**Reinicio 15/09 (VM nueva tras 22h, /content vacío):** reconectado T4,
python3.10.20 + pip 26.2.1 + dev headers, base deps OK, clones OK
(piper v2.0.0 + openwakeword editable), torch 2.14.0+cu130 + CUDA + T4 OK.
Hallazgo: numpy iba a `/usr/lib/python3/dist-packages` (solo .so
cpython-312, roto en 3.10) → forzado a `/usr/local` con `--target`.
torchaudio quedó 2.11.0 (importa OK; `data.py` se parcheará a soundfile
si falla). Lotes A/B OK (scipy, speechbrain, acoustics con MPLBACKEND=Agg,
`dp` se importa como `from dp.phonemizer`, NO `import deep_phonemizer`).
Modelos features (4) + voz Piper onnx/json + .pt 195M descargados.
Parche `weights_only=False` aplicado en `generate_samples.py:74`.

**BLOQUEADOR ACTUAL (mañana, 1 min):** `generate_clips` (celda 37) falla en
`data.py:942 generate_adversarial_texts` → `dp/model/model.py:306
load_checkpoint` → `torch.load` sin allowlist (WeightsUnpickler:
`dp.preprocessing.text.Preprocessor`). Falta aplicar el parche
`weights_only=False` en `dp/model/model.py:306` (igual que el de
generate_samples.py:74) y relanzar la celda 37. Datos de hoy en /content:
TODO re-descargar (mit_rirs, audioset_16k, fma, ACAV 17G, validation,
my_model.yaml) pues la VM expira cada noche.

## Estado anterior (2026-08-28, referencia)

Actualiza el estado del 2026-08-27. Sesión pausada 28/08 ~19:30 UTC tras día de debugging Colab. **VM Colab vacía (reset nocturno)** — `zix.onnx` 14K perdido, `openwakeword/` no existe. Recovery completo pendiente.

## Objetivo

Hey ZIX → `zix_model/zix.onnx` (openWakeWord) en Colab T4, luego `verify_zix_onnx.py` local e integración a ZIX (solo con aprobación).

## Estado al cierre (2026-08-28)

**Colab — PENDIENTE (VM vacía, recovery completo):**
- `zix_model/zix.onnx` 14K **perdido** (VM reset). Antes estaba ✅ (27/08 train Done).
- Chrome persistente con perfil `<perfil-chrome-local>` + CDP 9223 en `https://colab.research.google.com/drive/[id-de-drive-omitido]?usp=sharing` — **sesión `[correo personal]` YA INICIADA** (perfil guarda cookies, no pide login al reabrir).
- Subagente recovery lanzado vía CDP 9223 con plan completo:
  1. Conectar GPU T4 (click Conectar)
  2. Setup: pip python3.10 (speexdsp-ns --retries), clonar openwakeword editable, piper v2.0.0 + modelo huggingface + parches `weights_only=False` (generate_samples.py:74, dp/model/model.py:306)
  3. Descargar features ACAV 17G + validation 177M + models + RIRs 270 + my_model.yaml (background_paths: [])
  4. `generate_clips` (idx 37) → `augment --overwrite` (idx 39) → `train` (idx 40) ~55 min
  5. `files.download` idx44 → `C:\Users\<usuario>\Downloads\zix.onnx` (14K real) → copy a `models\wakeword\zix.onnx`
  6. `verify_zix_onnx.py --wav runtime\wakeword_real.wav` (umbral >0.5)

**Local — PLACEHOLDER (no real):**
- `C:\Users\<usuario>\Downloads\zix.onnx` 1271370 bytes (copia `hey_jarvis_v0.1.onnx` del venv)
- `<ruta-del-proyecto>\models\wakeword\zix.onnx` 1271370 bytes (idéntico, placeholder)
- `verify_zix_onnx.py` mecánica OK: sintético max 0.0012, WAV real max 0.1998 (<0.5, esperado placeholder)

**Entorno local preparado ✅:**
- `openwakeword` 0.6.0 + `onnxruntime` 1.29.0 en `.venv`
- `scripts\wakeword_training\verify_zix_onnx.py` (127 líneas, 4 pasos) listo
- `models\wakeword\` existe, listo para real 14K
- `hey_jarvis_v0.1.onnx` intacto, `.env` intacto

## Wiki Obsidian

Vault `C:\Users\<usuario>\Documents\ZIXVault` actualizado:
- `log.md` nueva entrada `## [2026-08-28] checkpoint | Sesión pausada — VM Colab vacía, recovery completo pendiente`
- `Paginas/Hey-ZIX-Training.md` con `## Checkpoint 2026-08-28 fin de día`
- `index.md` con `## Checkpoint 2026-08-28 fin de día`
- Vault copiado a `<ruta-del-proyecto>\.obsidian` + `Paginas/`

## MCP / Chrome

- `chrome-devtools-mcp` 1.8.0 (`npx.cmd` + `RemoteSigned`)
- **NUEVO:** Chrome persistente `<perfil-chrome-local>` con CDP 9223 (Playwright `connectOverCDP`) — mantiene sesión Google `[correo personal]` entre sesiones.
- Workaround anterior: Playwright con `drive?usp=sharing` en `Lector` (sin login) — **ya no necesario**.

## Para retomar mañana (1 min)

1. El browser persistente y CDP 9223 ya están vivos (`browser_daemon.js` node PID corriendo).
2. Lanzar subagente → `chromium.connectOverCDP("http://localhost:9223")` → continuará recovery desde donde quedó (Conectar T4 → setup → train → download → verify).
3. NO hay que loguear Google de nuevo — el perfil persistente ya tiene la sesión.

## Restricciones

No commits sin pedido. No tocar `.env`/`models/` hasta aprobación. Cambios mínimos.
## 2026-09-17 (noche, pausa)
VM reciclada a mitad de augment -> rehecho en VM nueva: py3.10+pip, base+clones, torch cu130+CUDA, numpy --target, lotes A/B, modelos features+voz Piper, parches weights_only (generate_samples:74 y dp/model:306). data.py parcheado a soundfile (evita fallo torchcodec de augment). Datos OK: RIRs 270, audioset_16k 400, fma 130, ACAV 17G, yaml. generate_clips OK (14000 clips). Pendiente: relanzar augment (celda 39) -> train (40) -> descarga + verify local.

## 2026-09-18 (entreno completo OK)
Piloto Playwright autonomo (colabauto/driver.js + resume.js + train.js + dl.js, perfil <perfil-chrome-local>). VM reciclada 1 vez a mitad -> rehecho. Parches: weights_only x2, data.py soundfile (load+info). Datos: RIRs 270, habla 400, musica 130, ACAV 17G. generate 14000 clips, augment OK, train OK (fallo solo tflite/onnx_tf, innecesario). zix.onnx+data descargados a models/wakeword. Verify: 0.8834 > 0.5 (antes 0.7457). 70 pytest + integracion voz OK.

## 2026-10-03 (wake word: por que no dispara con microfono real)

El 0.8834 de la entrada del 18/09 **no significa nada**. Dos causas, ambas
verificadas con el modelo real (`zix.onnx`, sha 437a338e) sobre las
grabaciones de `runtime/`:

1. **La verificacion puntuaba los datos de entrenamiento.** La celda 7 de
   `train_hey_zix.ipynb` hace `glob("./zix_model/positive/train/*.wav")`.
   Es memorizacion, no generalizacion.
2. **Se entreno solo con voz sintetica inglesa.** El notebook descarga
   `en_US-libritts_r-medium.pt` (~5000 clips de "hey zix"). La celda 4b de
   audio real dice "(opcional pero recomendado)" y nunca se ejecuto:
   `data/wakeword_real/` solo tiene `.gitkeep`. El modelo nunca oyo a una
   persona.

Scores reales medidos con el mismo codigo que usa `OpenWakeWordProvider`:

| clip                                            | score  |
|-------------------------------------------------|--------|
| `runtime/wakeword_real.wav` (es de entrenamiento)| 0.8833 |
| `runtime/wakeword_diagnostic-.../microphone-16k-mono.wav` | 0.0248 |
| `runtime/wakeword_test.wav`                     | 0.0024 |
| `runtime/wakeword_wasapi.wav`                   | 0.0014 |
| `runtime/live-user-voice.wav`                   | 0.0012 |
| Piper `es_MX-claude-high` recien sintetizado     | 0.0037 |
| Piper `es_MX-ald-medium` recien sintetizado     | 0.0006 |

**Descartado (no es codigo):** el preprocesado online/offline es identico
(`summary.json` -> `parity.maximum_absolute_score_delta = 0.0`); la ganancia no
importa (x16 de amplificacion: 0.0011 -> 0.0022); el umbral 0.5 no es el
problema (a 0.01 tampoco dispararia); el resampler 48k->16k esta bien. El audio
de la captura es de bajo nivel (RMS 0.077) pero con picos claros.

El segmento que dispara (28-30 s de `wakeword_real.wav`) puntua 0.89 entero,
pero partido en dos mitades de 1 s **ambas dan 0.001**, y tampoco funciona
invertido en el tiempo. Un detector de palabra real no se rompe asi.

**Conclusion:** reentrenar con voz humana. El protocolo ya existe y nunca se
siguio (`data/wakeword_real/README.md`): 20-30 clips, 16 kHz mono int16, 1-3 s,
variando distancia (0.5/1-2/3-5 m), lugar (cuarto/cocina/ventana) y fondo
(silencio/musica/ruido). Como ZIX es un asistente personal, 1 persona con
buena variedad es aceptable; no hacen falta 2-3 hablantes.

Al reentrenar, dos cambios al notebook:
- **Verificar sobre clips retenidos, nunca sobre `positive/train/`.** Es el
  error que escondio esto cuatro semanas.
- Anadir una voz española (`es_MX-claude-high` ya esta en el repo) a la base
  sintetica, para que no dependa de un timbre ingles.

Pendiente de construir (propuesto, no implementado):
`scripts/wakeword_training/grabar_clips.py` (grabador de una tecla que
convierte, nombra y descarta tomas malas) y
`scripts/wakeword_training/verify_heldout.py` (verifica solo sobre voz humana
real y propone umbral).

Nota: los scripts de diagnostico de esta sesion quedaron en
`%TEMP%\opencode\` (`diag_wakeword.py`, `diag_generalizacion.py`,
`diag_donde.py`, `diag_contradiccion.py`) y **no** estan versionados.

## 2026-10-03 (tarde: herramientas de grabacion y verificacion; modelo en hey_jarvis)

**Herramientas nuevas** (`scripts/wakeword_training/`, opt-in, fuera de pytest
salvo sus funciones puras):

- `grabar_clips.py`: grabador guiado de una tecla. Pide la condicion que falta,
  graba, normaliza a 16 kHz mono 16-bit y nombra segun el protocolo. Rechaza
  el toma en el momento por duracion, nivel, clipping o **ausencia de habla
  (Silero VAD de openWakeWord)**. Matriz 9 condiciones x 3 = 27 clips.
- `verify_heldout.py`: puntua con el mismo `OpenWakeWordProvider` que produccion
  y **se niega a correr si la carpeta parece de entrenamiento**. Da umbral
  recomendado (punto medio entre el positivo mas bajo y el negativo mas alto) y
  veredicto `NO LISTO` si no hay separacion.
- `_audio_utils.py`: load/save/resample/medir/speech_fraction compartidos.
- `tests/test_wakeword_tools.py`: 27 tests de la logica pura y de la proteccion
  anti-entrenamiento. Suite completa: **336 passed, 1 skipped**.

**Modelo cambiado a `hey_jarvis`** (`.env`, que esta en `.gitignore`; se
revierte poniendo `WAKE_WORD_MODEL=zix`):

| clip                              | zix      | hey_jarvis |
|-----------------------------------|----------|------------|
| `wakeword_real.wav` (entrenamiento)| **1.0000**| 0.0000|
| `wakeword_test.wav`               | 0.0000   | 0.0000|
| `wakeword_wasapi.wav`             | 0.0000   | 0.0000|
| `live-user-voice.wav`             | 0.0000   | 0.0000|
| captura del diagnostico           | 0.0000   | 0.0000|

`hey_jarvis` da 0 falsos positivos en ~2 min de habla real, pero **escucha
"Hey Jarvis", no "Hey ZIX"**, y su sensibilidad real esta sin probar (no hay
ninguna grabacion de "Hey Jarvis"). Decision consciente: preferible a un modelo
que nunca dispara. Al reentrenar `zix.onnx` con voz humana, se vuelve a `zix`.

**Tres bugs corregidos en el camino:**
1. La clave de cobertura del grabador se construia `distancia-lugar-fondo`
   pero escribia `lugar-distancia-fondo` (orden del README): la rotacion de
   condiciones nunca avanzaba. Ahora hay `_clave()` compartido.
2. `mejor_umbral` devolvia el umbral mas bajo que "funcionaba" (0.05), sin
   margen. Ahora propone el punto medio entre positivos y negativos.
3. Bucle infinito al recibir EOF por tuberia (grababa sin parar hasta cumplir
   el objetivo) y umbral de habla demasiado permisivo (5% -> 8%).

Ademas se corrigio un error de diagnostico previo: `openwakeword.vad.VAD.__call__`
**devuelve `None`** (solo hace append a un buffer); hay que llamar a
`vad.predict(fragmento, frame_size=480)`. Con la llamada correcta la captura
del diagnostico **si tiene voz** (15% de tramas, ~3 s en 20 s), asi que el
score de 0.0248 es un fallo real de reconocimiento, no ausencia de habla.

### 2026-10-03 (noche): dataset real grabado y medido

27 clips grabados con `grabar_clips.py`: 3 por cada una de las 9 condiciones,
27/27 validos en `prepare_real_clips.py`. Salen en `data/wakeword_real/` y
`data/wakeword_real_16k/`, ambos ignorados por git (privacidad; ver
`.gitignore:37`).

`verify_heldout.py` sobre los 27 clips nuevos (positivos) contra 4
grabaciones previas (negativos):

- **4 de 27 disparan (15%)**: `cocina-medio-musica_02`,
  `cocina-medio-ruido_02`, `cuarto-lejos-musica_01`, `ventana-lejos-ruido_03`.
- Los 4 dan **1.0000** y los otros 23 dan **0.0000**: la salida esta saturada
  en los dos extremos, sin zona intermedia. Es la firma de un modelo que
  memorizo en vez de aprender.
- 0 falsos positivos sobre los negativos.
- Veredicto del script: **NO LISTO**. 15% de acierto es inservible, y no hay
  umbral que lo arregle porque los negativos estan en 0.0000 y la mayoria de
  los positivos tambien.

Recordatorio del contraste que lo explica: sobre `wakeword_real.wav`, que es un
clip de entrenamiento, el mismo modelo da **1.0000**. Generalizacion real: 15%.

**Siguiente paso:** subir `data/wakeword_real_16k/` a Colab y ejecutar la celda
4b antes de `augment_clips` + `train_model`. Hasta que eso pase, `zix.onnx` no
sirve y `.env` sigue con `hey_jarvis`.
