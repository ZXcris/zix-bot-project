# Celda 4b (version OSS): mezclar audios reales con SOBREMUESTREO
#
# Por que no basta con anadirlos una vez: la celda original mete los clips
# reales en una carpeta con ~14.000 clips sinteticos de LibriTTS. 27/(14000+27)
# = 0,19 % de voz real, una fraccion que no cambia lo que aprende el modelo.
# Con sobremuestreo el peso sube de verdad.
#
# Cuantas mas copias, mas se acerca el modelo a tu voz, pero se pierde
# variedad sintetica. ~100 deja la voz real en ~16% del set positivo, que es
# el punto en el que la DNN empieza a girar hacia el hablante real.
#
# SUBE antes los 27 clips al panel de Archivos de Colab y descomprimelos:
#     !unzip -q -o heyzix_clips.zip -d ./
#
# Es la UNICA implementacion de este paso. Anteslogicacrunsalimportar este
# modulo (no habia main() ni guard __main__), asi que:
#   * importarlo desde un test escribia en positive_train sin avisar,
#   * si faltaba ./hey_zix_real/ imprimia ERROR y salia con codigo 0, asi que
#     la corrida de Colab continuaba entrenando con CERO voz real y solo
#     declaraba exito al final.
# Ahora main() devuelve 1 si algo falta y el pipeline puede detenerse.
"""Inyecta los clips reales en positive_train con sobremuestreo y retenidos.

Ejecucion unica (Colab, con la raiz en /content):
    ZIX_RAIZ=/content python inyectar_clips_reales.py

Codigo de salida:
    0 = los clips reales quedaron en positive_train y los retenidos separados
    1 = falta ./hey_zix_real/, estaba vacia, o ningun clip llego al destino
"""
import os
import random
import shutil
import sys
from pathlib import Path

import numpy as np
import scipy.io.wavfile

COPIAS = int(os.environ.get("ZIX_REAL_COPIAS", "100"))  # factor de sobremuestreo
RAIZ = Path(os.environ.get("ZIX_RAIZ", "."))             # /content en Colab
MODEL_NAME = os.environ.get("ZIX_MODEL_NAME", "zix")     # model_name del yaml
SRC = RAIZ / "hey_zix_real"
# ---------------------------------------------------------------------------
# RUTAS REALES que lee openWakeWord (train.py):
#     output_dir/model_name/positive_train
#     output_dir/model_name/negative_train
# ANTES: ./zix_model/positive/train  (con barra y SIN subcarpeta de modelo)
#        -> nada lo leia: los 27 clips reales se perdian en silencio.
# ---------------------------------------------------------------------------
MODEL_DIR = RAIZ / "zix_model" / MODEL_NAME
POS_TRAIN = MODEL_DIR / "positive_train"     # <- lo que lee train.py
NEG_TRAIN = MODEL_DIR / "negative_train"     # <- lo que lee train.py
HELDOUT = RAIZ / "zix_real_heldout"          # retenidos: el modelo NO los vera
STAGE = MODEL_DIR / "extra_real"             # copia intermedia, trazable


def _leer(ruta):
    sr, data = scipy.io.wavfile.read(str(ruta))
    if data.ndim > 1:
        data = data.mean(axis=1).astype(np.dtype("int16"))
    if sr != 16000:
        from scipy import signal
        n = int(len(data) * 16000 / sr)
        data = signal.resample(data.astype(np.float32), n)
        data = (np.clip(data, -1, 1) * 32767).astype(np.int16)
    return data


def seleccionar_retenidos(wavs):
    """Aparta un 15% para verificar DESPUES con verify_heldout.py.

    Si el modelo memoriza estos, el verificador lo detecta. Es el mismo error
    que produjo el falso 0.88 en 2026-09.
    """
    random.seed(7)
    n_val = max(1, int(len(wavs) * 0.15))
    return set(random.sample(wavs, n_val))


def main() -> int:
    if not SRC.is_dir():
        print("ERROR: no existe ./hey_zix_real/")
        print("Sube heyzix_clips.zip al panel Archivos y ejecuta antes:")
        print("    !unzip -q -o heyzix_clips.zip -d ./")
        return 1

    wavs = sorted(SRC.glob("*.wav"))
    if not wavs:
        print(f"ERROR: {SRC} esta vacio: sin clips reales no hay nada que inyectar.")
        return 1

    retenidos = seleccionar_retenidos(wavs)

    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True, exist_ok=True)
    HELDOUT.mkdir(parents=True, exist_ok=True)
    for viejo in HELDOUT.glob("*.wav"):
        viejo.unlink()
    # idempotencia: fuera copias de una ejecucion anterior
    for viejo in POS_TRAIN.glob("real_*_c*.wav"):
        viejo.unlink()

    n_train = n_val = saltados = 0
    for w in wavs:
        try:
            data = _leer(w)
            dur = len(data) / 16000
            if not (0.5 <= dur <= 5.0):
                print(f"  SKIP {w.name}: duracion {dur:.2f}s")
                saltados += 1
                continue
            if w in retenidos:
                scipy.io.wavfile.write(str(HELDOUT / w.name), 16000, data)
                n_val += 1
                continue
            for c in range(COPIAS):
                # leve variacion para que no sean copias identicas
                jitter = 1.0 + random.uniform(-0.03, 0.03)
                ganancia = random.uniform(0.85, 1.10)
                d = np.clip(data.astype(np.float32) * jitter * ganancia, -32768, 32767)
                scipy.io.wavfile.write(str(STAGE / f"real_{w.stem}_c{c:03d}.wav"), 16000,
                                       d.astype(np.int16))
            n_train += 1
        except Exception as e:
            print(f"  SKIP {w.name}: {type(e).__name__}: {e}")
            saltados += 1

    # 2) mover los sobremuestreados dentro de positive_train, que es donde
    #    train.py los recoge de verdad (output_dir/model_name/positive_train).
    POS_TRAIN.mkdir(parents=True, exist_ok=True)
    for f in STAGE.glob("*.wav"):
        shutil.copy2(f, POS_TRAIN / f.name)

    reales = len(list(POS_TRAIN.glob("real_*_c*.wav"))) if POS_TRAIN.is_dir() else 0
    total_pos = len(list(POS_TRAIN.glob("*.wav"))) if POS_TRAIN.is_dir() else 0
    neg = len(list(NEG_TRAIN.glob("*.wav"))) if NEG_TRAIN.is_dir() else 0

    print("")
    print(f"  Clips reales usados en entrenamiento : {n_train}")
    print(f"  Copias por clip (COPIAS={COPIAS})        : {COPIAS}")
    print(f"  Ficheros reales en {POS_TRAIN} : {reales}")
    print(f"  Retenidos para verificar (NUNCA se ven): {n_val}  -> {HELDOUT}")
    print(f"  Saltados                            : {saltados}")
    total = total_pos + neg
    if total:
        print(f"  Peso de la voz real en los positivos : {100*reales/total:.1f} %")
    print("")
    print("  SIGUIENTE: ejecuta augment_clips y luego train_model.")
    print(f"  Los retenidos en {HELDOUT} son tu prueba honesta:")
    print("  bajalos y verificalos con verify_heldout.py.")

    # Si el objetivo del paso es meter la voz real en el set positivo y no lo
    # consigue, seguir adelante solo produce otro modelo que ignora al usuario.
    if reales == 0:
        print("")
        print("ERROR: 0 clips reales en positive_train. El modelo no oiria tu voz.")
        print("       Revisa COPIAS, los nombres de los ficheros y los permisos.")
        return 1
    if n_val == 0:
        print("")
        print("ERROR: 0 clips retenidos: sin ellos no hay verificacion honesta posible.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())