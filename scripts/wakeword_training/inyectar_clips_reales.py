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
import glob, os, random, shutil
from pathlib import Path
import numpy as np
import scipy.io.wavfile

COPIAS = int(os.environ.get("ZIX_REAL_COPIAS", "100"))  # factor de sobremuestreo
SRC = Path("./hey_zix_real")
DEST = Path("./zix_model/positive/extra_real")          # carpeta propia: trazable
VALIDATION = Path("./zix_model/real_heldout")            # clips que el modelo NO vera

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

if not SRC.is_dir():
    print("ERROR: no existe ./hey_zix_real/")
    print("Sube heyzix_clips.zip al panel Archivos y ejecuta antes:")
    print("    !unzip -q -o heyzix_clips.zip -d ./")
else:
    wavs = sorted(SRC.glob("*.wav"))
    if not wavs:
        print("ERROR: ./hey_zix_real/ esta vacio.")
    else:
        # 1) un 15% se aparta como retenido. Sirve para verificar DESPUES con
        #    verify_heldout.py: si el modelo memoriza estos, el verificador lo
        #    detecta. Es el mismo error que produjo el falso 0.88 en 2026-09.
        random.seed(7)
        n_val = max(1, int(len(wavs) * 0.15))
        retenidos = set(random.sample(wavs, n_val))

        if DEST.exists():
            shutil.rmtree(DEST)
        DEST.mkdir(parents=True, exist_ok=True)
        VALIDATION.mkdir(parents=True, exist_ok=True)
        for viejo in VALIDATION.glob("*.wav"):
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
                    scipy.io.wavfile.write(str(VALIDATION / w.name), 16000, data)
                    n_val += 1
                    continue
                for c in range(COPIAS):
                    # leve variacion para que no sean copias identicas
                    jitter = 1.0 + random.uniform(-0.03, 0.03)
                    ganancia = random.uniform(0.85, 1.10)
                    d = np.clip(data.astype(np.float32) * jitter * ganancia, -32768, 32767)
                    scipy.io.wavfile.write(str(DEST / f"{w.stem}_c{c:03d}.wav"), 16000,
                                            d.astype(np.int16))
                n_train += 1
            except Exception as e:
                print(f"  SKIP {w.name}: {type(e).__name__}: {e}")
                saltados += 1

        # 2) mover los sobremuestreados dentro de positive/train, que es donde
        #    train.py los recoge.
        total_train = 0
        for f in DEST.glob("*.wav"):
            shutil.copy2(f, Path("./zix_model/positive/train") / f.name)

        pos_train = Path("./zix_model/positive/train")
        pos_val = Path("./zix_model/positive/validation")
        for d in (pos_train, pos_val):
            if d.is_dir():
                total_train += len(list(d.glob("*.wav")))

        reales = len(list(pos_train.glob("*_c*.wav"))) if pos_train.is_dir() else 0
        print("")
        print(f"  Clips reales usados en entrenamiento : {n_train}")
        print(f"  Copias por clip (COPIAS={COPIAS})        : {COPIAS}")
        print(f"  Ficheros reales en positive/train   : {reales}")
        print(f"  Retenidos para verificar (NUNCA se ven): {n_val}  -> {VALIDATION}")
        print(f"  Saltados                            : {saltados}")
        if pos_train.is_dir():
            neg = len(list(Path('./zix_model/negative/train').glob('*.wav'))) \
                  if Path('./zix_model/negative/train').is_dir() else 0
            total = len(list(pos_train.glob('*.wav'))) + neg
            if total:
                print(f"  Peso de la voz real en los positivos : {100*len(list(pos_train.glob('*.wav')))/total:.1f} %")
        print("")
        print("  SIGUIENTE: ejecuta augment_clips y luego train_model.")
        print("  Los retenidos en real_heldout/ son tu prueba honesta: despues")
        print("  bajalos y verificalos con verify_heldout.py.")
