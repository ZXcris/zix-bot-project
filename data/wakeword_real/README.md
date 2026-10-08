# Audios reales "Hey ZIX" — protocolo de grabación

Objetivo: robustecer `zix.onnx` con voz real (distancias, lugares, música, ruido).
El pipeline base es sintético (Piper TTS). Estos WAV se mezclan en `zix_model/positive/`
en Colab **antes** de `--augment_clips` + `--train_model`.

## Formato obligatorio
- WAV, **16 kHz, mono, 16-bit**. 1-3 s por clip. Solo "Hey ZIX" (una vez por archivo).
- Nombra: `heyzix_<persona>_<condicion>_<nn>.wav`
  ej: `heyzix_cristian_cocina-lejos-musica_01.wav`

## Matriz mínima (20-30 clips)
- Personas: 2-3 distintas (ideal).
- Distancias: cerca (~0.5m, 5 clips), medio 1-2m (10 clips), lejos 3-5m (10 clips).
- Lugares: cuarto silencioso, cocina/sala con eco, calle/ventana abierta (al menos 2 lugares).
- Fondo: 1/3 silencio, 1/3 música/TV baja, 1/3 ruido (ventilador, trastes, tráfico).
- No grites ni susurres siempre: tono normal, variando un poco velocidad/entonación.

## Cómo grabar en Windows
1. Grabadora de voz o `python -m zix.voice_main` no sirve (ya recorta). Usa Audacity / móvil y convierte:
   - Audacity: Pista → Frecuencia 16000 Hz → Mezclar a mono → Exportar WAV 16-bit.
2. Valida en local antes de subir:
   ```
   .venv\Scripts\python.exe scripts\wakeword_training\prepare_real_clips.py data\wakeword_real --out data\wakeword_real_16k
   ```
   Solo sube a Colab lo que pase el check.

## Cómo usar en Colab (notebook train_hey_zix.ipynb, celda 4b)
1. Ejecuta hasta `generate_clips` (celda 4 paso 1).
2. En celda **4b**: sube el ZIP o los WAV a `./hey_zix_real/` (panel Archivos o `files.upload()`).
3. La celda convierte a 16k/mono y copia a `zix_model/positive/train/` (+20% a `validation/`).
4. Sigue con `augment_clips` + `train_model` normal. El aumento mezclará tus reales con ruido/reverb igual que los sintéticos.

No se sube nada al repo: `data/wakeword_real/*.wav` está ignorado por git (privacidad).
