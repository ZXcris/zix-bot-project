# Entrenamiento del wake word "Hey ZIX" (openWakeWord)

Objetivo: entrenar un modelo de wake word propio para **"Hey ZIX"** con el
pipeline **oficial de openWakeWord**, y obtener **`zix.onnx`** para ZIX.

> `hey_jarvis_v0.1.onnx` **no se reemplaza**: queda como respaldo mientras tanto.

## Estado real del modelo actual (medido 2026-10-14, no estimado)

`models/wakeword/zix.onnx` **no sirve**. Medido con el `OpenWakeWordProvider` real
sobre los 27 clips propios y 48 grabaciones de `runtime/`:

| Conjunto | n | score máx | media |
|---|---|---|---|
| Retenidos (nunca vistos por el modelo) | 4 | **0.0017** | 0.0012 |
| Entrenamiento (sí vistos) | 23 | 0.2075 | 0.0222 |
| Negativos (`runtime/`) | 48 | 0.0133 | 0.0018 |

El retenido es indistinguible de los negativos, así que **ningún umbral separa
la frase del ruido**: no es un problema de calibración, hay que reentrenar.
El 0.2075 puntual es una instancia memorizada, no reconocimiento.

No es un modelo degenerado: la red responde con rango completo (logits de −6 a
+3) y los pesos se movieron del inicializador. Aprendió, pero aprendió a
**rechazar la voz humana**: lo que el modelo sí aprendió bien fue la voz sintética de Piper.

Por eso la corrida **debe pasar las compuertas** de este documento. Antes,
`train_model` terminaba con código 0 y el modelo se daba por bueno.

## Procedimiento (Colab)

1. Abre <https://colab.research.google.com> y sube el notebook
   `scripts/wakeword_training/train_hey_zix.ipynb`
   (Archivo → Subir notebook).
2. **Runtime → Cambiar tipo de entorno → GPU T4** (el entrenamiento es mucho
   más rápido; sin GPU, multiplica los tiempos).
3. Ejecuta las celdas **en orden** (Runtime → Ejecutar todo o celda a celda):

   | Celda | Qué hace | Tiempo aprox. |
   |---|---|---|
   | 1. Instalación del entorno | Clona piper-sample-generator + openWakeWord e instala dependencias | ~10 min |
   | 2. Descarga de datos | RIRs MIT, AudioSet (1 tar) + FMA (1 h), features negativos (~2 GB) | ~20-30 min |
   | 3. Configuración | Escribe `my_model.yaml` con frase **"hey zix"** y `model_name: zix` | instantáneo |
   | 4. Generar clips | Sintetiza ~5000 muestras de "Hey ZIX" + adversariales con Piper TTS | ~30-45 min |
   | 4b. Audios reales (opcional) | Mezcla tus WAV 16k mono en `zix_model/zix/positive_train/` (**con guion bajo y subcarpeta del modelo**: es la única ruta que lee `train.py`; ver `data/wakeword_real/README.md` + `prepare_real_clips.py`) | ~5 min |
   | 5. Aumentar clips | Mezcla con ruido/reverberación | ~10 min |
   | 6. Entrenar | Entrena la DNN y exporta `zix.onnx` (+ `zix.tflite`) | ~30-60 min |
   | 7. Verificar | Carga `zix.onnx` y compara scores positivos vs. negativos | instantáneo |
   | 8. Descargar | `files.download("zix_model/zix.onnx")` → lo guardas en tu PC | instantáneo |

4. Si algo falla a mitad de la generación, **vuelve a ejecutar esa celda**:
   `train.py` continúa donde quedó (no se regenera lo ya hecho).
5. Si la instalación de dependencias fallara en el Colab actual (pins de
   2023), prueba otro runtime de Python (3.10) o el notebook comunitario
   `alfiedennen/openwakeword-colab-2026` (versiones compatibles con 2026),
   que produce el mismo `.onnx`.

## Archivos que se generan

| Archivo (en Colab) | ¿Se necesita en ZIX? | Dónde va |
|---|---|---|
| `zix_model/zix.onnx` | **Sí — es el único necesario** | `models/wakeword/zix.onnx` |
| `zix_model/zix.tflite` | No (ZIX usa ONNX) | — |
| `zix_model/positive/`, `negative/`, features, checkpoints, logs | No (subproductos del entrenamiento) | — |

### ¿Necesita archivos auxiliares junto al `.onnx`? **No.**

openWakeWord usa dos *feature models* compartidos para TODOS los wake words:
`melspectrogram.onnx` (1.1 MB) y `embedding_model.onnx` (1.3 MB, Apache-2.0).
**Ya están instalados en tu PC** con el paquete `openwakeword`
(`.venv\Lib\site-packages\openwakeword\resources\models\`). No hay metadatos
por modelo: el `.onnx` es autocontenido (entrada = embeddings de 96 dims,
salida = score).

## Compatibilidad con `OpenWakeWordProvider` — confirmada

- Acepta **rutas de archivo `.onnx`** (`_resolve_spec`): con
  `WAKE_WORD_MODEL=zix` buscará `models/wakeword/zix.onnx` y la clave del
  resultado será `zix` (el stem del archivo).
- `Model(wakeword_models=[ruta], inference_framework="onnx")` es exactamente
  lo que el provider ya usa con `hey_jarvis` — misma API.
- Audio: 16 kHz mono int16 (nuestro `AudioManager` ya entrega eso).
- Umbral configurable: `WAKE_WORD_THRESHOLD` (default 0.5); tras probar con
  micrófono real se puede calibrar.

## Herramientas locales (nuevas, 2026-10-03)

El ciclo de reentrenamiento se hacia a mano y la verificación era engañosa.
Estas dos herramientas lo automatizan:

### 1. Grabar clips reales — `grabar_clips.py`

```
.venv\Scripts\python.exe scripts\wakeword_training\grabar_clips.py
```

Modo guiado: te dice qué condición falta (`lugar / distancia / fondo`), pulsas
Enter, dices "Hey ZIX" y el clip se guarda ya normalizado a 16 kHz mono 16-bit
con el nombre del protocolo (`heyzix_<persona>_<lugar>-<dist>-<fondo>_<nn>.wav`).

Rechaza el toma en el momento, sin guardar nada, si la duración está fuera de
rango, el nivel es bajo o saturante, hay clipping, o **Silero no detecta habla**
(`openwakeword` ya trae el VAD; el script lo usa). `q` para salir.

Matriz por defecto: 9 condiciones × 3 tomas = 27 clips, priorizando variedad
(3 lugares, 3 distancias, 3 fondos) sobre cantidad.

### 2. Verificar sobre clips retenidos — `verify_heldout.py`

```
.venv\Scripts\python.exe scripts\wakeword_training\verify_heldout.py data\wakeword_real_16k ^
    --negativos runtime\wakeword_wasapi.wav --negativos runtime\wakeword_test.wav
```

Puntúa el modelo con el mismo `OpenWakeWordProvider` que usa producción y da:

- score máximo por clip, y cuántos disparan sobre el umbral;
- falsos positivos sobre los negativos;
- **umbral recomendado**: el punto medio entre el positivo más bajo y el
  negativo más alto, que es el corte con más margen;
- veredicto `NO LISTO` si el modelo no separa tus clips de los negativos.

**Se niega a correr si la carpeta parece de entrenamiento**
(`zix_model`, `positive/train`). La celda 7 del notebook puntuaba
`positive/train/*.wav` y por eso el 0.8834 no significaba nada: era
memorización. Este script existe para que eso no vuelva a pasar.

## Antes de subir a Colab

```
.venv\Scripts\python.exe scripts\wakeword_training\prepare_real_clips.py data\wakeword_real --out data\wakeword_real_16k
.venv\Scripts\python.exe scripts\wakeword_training\verify_heldout.py data\wakeword_real_16k --negativos <tuivos>
```

## Integración en ZIX (solo tras tu aprobación)

1. Copia `zix.onnx` a `models/wakeword/zix.onnx`.
2. En `.env`:
   ```
   WAKE_WORD_MODEL=zix
   # WAKE_WORD_THRESHOLD=0.5   (calibrar tras pruebas reales)
   ```
3. Verifica con `python scripts/integration_test_voice.py` (cargará `zix` y
   procesará silencio) y luego con micrófono real
   (`python -m zix.voice_main`) diciendo **"Hey ZIX"**.
4. Para volver al respaldo: `WAKE_WORD_MODEL=hey_jarvis`.

## Resultado esperado

```
"Hey ZIX" → wake word detectado → ZIX escucha → procesa el comando
          → responde por voz → vuelve a esperar "Hey ZIX"
```

## Pipeline de una sola pasada (`entrenar_colab.sh`, 2026-10-10)

El flujo por celdas de arriba falló tres veces seguidas. Este script lo
sustituye: es **idempotente** (se puede relanzar sin romper nada) y escribe un
log en `/content/zix_run.log`.

### Cómo se usa

Sube `heyzix_clips.zip` (tus 27 clips) al panel **Archivos** de Colab y ejecuta:

```
!chmod +x /content/entrenar_colab.sh
!(setsid nohup bash /content/entrenar_colab.sh > /content/run.log 2>&1 < /dev/null &)
```

Va de 1 a 20: dependencias → parches → datos → clips → negativos → reales →
augment → entrenamiento. Cada paso comprueba si ya está hecho y se salta.

### Los tres fallos que había (y por qué importan)

| Error | Causa real | Arreglo |
|---|---|---|
| `UnpicklingError: invalid load key, b'<'` | DeepPhonemizer descarga un **HTML de error** en vez del modelo de espeak: el primer byte `<` no es un pickle | `patch_adversarial.py` sustituye `generate_adversarial_texts()` por confusables generadas a mano |
| `StopIteration` en `utils.py:575` | `negative_train/` estaba **vacío**, así que `negative_clips_train = []` y `augment_clips([])` no puede dar nada | `generar_negativos.py` crea 1268 negativos duros |
| `FileNotFoundError: negative_test` | Faltaba la cuarta carpeta que openWakeWord espera | `generar_negativos.py` deja las cuatro |

> El `StopIteration` **nunca fue por ficheros viejos de una corrida anterior**,
> que era la hipótesis más obvia y la falsa. `SESSION_STATE.md` decía
> "augment OK" desde hacía meses y nunca lo estuvo.

### Ficheros

| Fichero | Para qué |
|---|---|
| `entrenar_colab.sh` | El pipeline entero, 20 pasos + compuertas |
| `validar_preflight.py` | **Comprobaciones antes y después de entrenar** (rutas, frases objetivo, clips, fuga, peso de la voz real, recall del modelo) |
| `generar_negativos.py` | Negativos duros: confusables × 4 voces × 5 ritmos, mezclados con ESC-50 a SNR 0-12 dB |
| `patch_adversarial.py` | Parchea `data.py` para no depender de DeepPhonemizer |
| `inyectar_clips_reales.py` | Mete tus 27 clips con sobremuestreo ×100 en `positive_train` y aparta el 15% como retenido. **Devuelve 1 si algo falta** |
| `check_adversarial.py` | Comprueba que el parche no dejó la frase exacta entre las negativas |

### Compuertas: por qué la corrida puede parar

Un entrenamiento en Colab cuesta 40-90 min de GPU. Descubrir al final que el
modelo no sirve significa ese tiempo perdido. Hay dos compuertas:

| Compuerta | Cuándo | Qué corta la corrida |
|---|---|---|
| `gate_pre.py` (paso 17b) | **antes** de augment y de entrenar | La frase objetivo aparece como negativa; 0 clips reales en `positive_train`; la voz real es <5% de los positivos; retenidos vacíos; fuga retenido↔entrenamiento |
| `gate_post.py` (paso 19b) | **después** de entrenar, antes de empaquetar | `recall@0.5 < 50%` sobre los retenidos, o `FAR@0.5 > 2%` sobre los negativos |

`gate_post` **no borra el artefacto**: lo empaqueta igualmente (no se pierde
el trabajo) pero deja claro en el log que no debe instalarse en ZIX.

Equivalente local: `validar_preflight.py` (paso previo) y el mismo script en
modo post contra el `.onnx` exportado:

```
.venv\Scripts\python.exe scripts\wakeword_training\validar_preflight.py --raiz . ^
    --modelo models\wakeword\zix.onnx --modo post
```

Códigos: `0` correcto · `1` crítico, no entrenar / no instalar · `2` avisos.

### Por qué ×100 y no solo "añadirlos"

En septiembre la celda 4b metía los clips reales en una carpeta con ~14 000
sintéticos: **27/14 027 = 0,19 %** de voz real. Con sobremuestreo ×100 la voz
real sube al **28 %** del set positivo, que es donde la DNN empieza a girar
hacia el hablante.

El 15% retenido va a `/content/zix_real_heldout/` y **no lo ve el modelo**. Es
lo único que dirá la verdad después: bájalo y pásalo por `verify_heldout.py`.

### Tiempo real medido (T4)

| Paso | Tiempo |
|---|---|
| Dependencias y parches | ~12 min |
| Descargar RIRs + ESC-50 + features | ~8 min |
| Generar 5000 clips sintéticos | ~35 min |
| Multivoces (1200) | ~12 min |
| Negativos (1268) | ~4 min |
| **augment** | ~9 min |
| **entrenar** (30 000 pasos × 3 secuencias) | **~21 min** |

## Referencias

- Pipeline oficial: `dscripka/openWakeWord` → `notebooks/automatic_model_training.ipynb`
- Config de ejemplo: `dscripka/openWakeWord` → `examples/custom_model.yml`
- Features compartidos: `davidscripka/openwakeword_features` (HuggingFace)
- Comunidad (fallback 2026): `alfiedennen/openwakeword-colab-2026`