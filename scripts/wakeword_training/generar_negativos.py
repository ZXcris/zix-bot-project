"""Genera los clips NEGATIVOS que openWakeWord espera y que nunca se crearon.

Por que hace falta:
    train.py hace
        negative_clips_train = [str(i) for i in Path(negative_train).glob("*.wav")][...]
        negative_clips_train_generator = augment_clips(negative_clips_train, ...)
    Como /content/zix_model/zix/negative_train estaba VACIO, la lista sale
    vacia, augment_clips no puede producir nada y utils.py:575 revienta con
        StopIteration
    Eso es el fallo que SESSION_STATE.md llamaba "augment OK" y no lo era.

Que son negativos duros:
    No basta con frases cualesquiera. Un negativo util es audio que se
    parece a "Hey ZIX" o tiene la misma forma acustica: se mezcla con ruido
    de fondo real (ESC-50) a relaciones senal/ruido variadas, igual que hace
    openWakeWord por su cuenta.
"""
import os
import random
import sys
import traceback

sys.path.insert(0, "/content/openwakeword")

import numpy as np
import scipy.io.wavfile
from scipy.signal import resample_poly

OUT_DIR = "/content/zix_model/zix/negative_train"
BG_DIR = "/content/background"
MODELS = "/content/piper-sample-generator/models"
VOICES = ["libritts_r", "hfc_female", "ryan", "lessac"]
SR = 16000

# Frases objetivo de todos los checkpoints (ver my_model.yaml: target_phrase).
# Si alguna coincide, se sintetizaria como NEGATIVO y el modelo aprenderia a
# ignorar la frase que debe despertar.
FRASES_OBJETIVO = ("hey zix",)


def normalizar(frase):
    """Minusculas, sin puntuacion final y con espacios colapsados.

    Comparar solo por igualdad cruda no basta: "HEY ZIX", "hey  zix" y
    "hey zix." son la MISMA frase y tambien envenenan el set.
    """
    import re as _re
    f = (frase or "").strip().lower()
    f = _re.sub(r"[.!?,;:]+$", "", f)
    f = _re.sub(r"\s+", " ", f)
    return f.strip()


def filtrar_frase_objetivo(textos, objetivo="hey zix"):
    """Quita la frase objetivo de una lista de NEGATIVOS.

    Se aplica a la lista FINAL que se sintetiza, no solo a la funcion
    parcheada de openWakeWord: generar_negativos.py anadia variantes a mano
    DESPUES del parche, y ahi se colaba la frase exacta.
    """
    objetivo_n = normalizar(objetivo)
    return [t for t in textos if normalizar(t) != objetivo_n]


def cargar_texto():
    """Frases negativas: las confusables del parche + casi-aciertos.

    El filtro final es OBLIGATORIO y se aplica aqui, sobre la lista completa,
    porque las frases anadidas a mano tambien pueden colar la frase objetivo.
    """
    try:
        from openwakeword.data import generate_adversarial_texts

        conf = generate_adversarial_texts("hey zix", N=400)
    except Exception:
        print("aviso: no pude usar generate_adversarial_texts", flush=True)
        conf = []
    # Anadidos a mano: lo que mas se confunde con "hey zix" en el mundo real.
    # NOTA: "hey zix" NO debe aparecer aqui. Si aparece, se filtra abajo igual,
    # pero dejarlo seria una bomba de relojería.
    conf += [
        "hey zics", "hey zip", "hey zisk", "hey zicks", "hey six",
        "hey zis", "hey zih", "hey zixx", "hey zizza", "hey zips", "hey zix en",
        "zix", "hey", "hey z", "hey zi", "ok zix", "oye zix", "hola zix",
        "hey jix", "hey zixx por favor", "hey zics ahora", "hey six computer",
        "hey assistant", "hey computer", "oye", "hola", "buenos dias",
        "hey jarvis", "hey siri", "hey google", "alexa", "ok google",
    ]
    vistos, out = set(), []
    for c in conf:
        c = (c or "").strip().lower()
        if c and c not in vistos:
            vistos.add(c)
            out.append(c)
    # Filtro final sobre TODAS las frases objetivo conocidas.
    for objetivo in FRASES_OBJETIVO:
        out = filtrar_frase_objetivo(out, objetivo)
    assert all(
        normalizar(t) != normalizar("hey zix") for t in out
    ), "la frase objetivo sigue entre los negativos"
    return out


def cargar_fondo():
    fondos = []
    if os.path.isdir(BG_DIR):
        for f in sorted(os.listdir(BG_DIR)):
            if f.endswith(".wav"):
                fondos.append(os.path.join(BG_DIR, f))
    return fondos


# Referencia al defecto original (documentado, no se ejecuta):
#
#     conf += [
#         "hey zix",   <-- BUG: la frase objetivo entre los NEGATIVOS,
#                          anadida DESPUES del parche que ya la filtraba.
#         "hey zics", "hey zip", ...
#     ]
#     return out    <-- sin filtro final
#
# La version vigente de cargar_texto() aplica filtrar_frase_objetivo()
# sobre la lista completa antes de devolverla.


def main():
    from piper import PiperVoice
    from piper.config import SynthesisConfig

    os.makedirs(OUT_DIR, exist_ok=True)
    for viejo in os.listdir(OUT_DIR):
        if viejo.endswith(".wav"):
            os.remove(os.path.join(OUT_DIR, viejo))

    textos = cargar_texto()
    fondos = cargar_fondo()
    print(f"textos negativos: {len(textos)}", flush=True)
    print(f"fondos ESC-50: {len(fondos)}", flush=True)
    if not textos:
        raise SystemExit("ERROR: no hay frases negativas")

    voces = []
    for v in VOICES:
        p = f"{MODELS}/en_US-{v}-medium.onnx"
        if os.path.exists(p):
            try:
                voces.append((v, PiperVoice.load(p)))
                print(f"  voz cargada: {v}", flush=True)
            except Exception as e:
                print(f"  voz {v} fallo: {type(e).__name__}", flush=True)
    if not voces:
        raise SystemExit("ERROR: ninguna voz piper disponible")

    rng = random.Random(11)
    escalas = [0.85, 0.95, 1.0, 1.05, 1.15]
    clips_palabra = 3  # cada frase se dice con varias voces y ritmos
    total, fallos = 0, 0

    for texto in textos:
        for _ in range(clips_palabra):
            nombre_v, voice = rng.choice(voces)
            fn = f"{OUT_DIR}/neg_{abs(hash(texto)) % 10**8}_{total:05d}.wav"
            try:
                esc = rng.choice(escalas)
                trozos = []
                for chunk in voice.synthesize(
                    texto, syn_config=SynthesisConfig(length_scale=esc)
                ):
                    trozos.append(
                        np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16).astype(np.float32)
                    )
                if not trozos:
                    continue
                d = np.concatenate(trozos)
                if len(d) > SR * 2:  # recorta frases absurdamente largas
                    d = d[: SR * 2]
                if len(d) < SR * 0.3:
                    continue
                # la mayoria de las voces ya son 22050 o 44100
                if abs(len(d)) > 0:
                    d = resample_poly(d, SR, 44100 if len(d) / 2 > SR else 22050).astype(np.int16)
                # mezclar con fondo: esto es lo que hace el negativo "duro"
                if fondos and rng.random() < 0.85:
                    try:
                        sr_f, bg = scipy.io.wavfile.read(rng.choice(fondos))
                        bg = bg.astype(np.float32)
                        if bg.ndim > 1:
                            bg = bg.mean(axis=1)
                        if sr_f != SR:
                            bg = resample_poly(bg, SR, sr_f).astype(np.float32)
                        if len(bg) < len(d):
                            bg = np.tile(bg, int(np.ceil(len(d) / max(1, len(bg)))))
                        ini = rng.randint(0, max(1, len(bg) - len(d)))
                        trozo = bg[ini : ini + len(d)]
                        # SNR entre 0 y 12 dB: a veces apenas se oye la frase
                        snr = rng.uniform(0, 12)
                        rms_f = np.sqrt(np.mean(trozo**2)) + 1e-9
                        rms_d = np.sqrt(np.mean(d**2)) + 1e-9
                        trozo = trozo * (rms_d / rms_f) * (10 ** (-snr / 20.0))
                        d = d + trozo
                    except Exception:
                        pass  # sin fondo tambien es un negativo valido
                pico = np.max(np.abs(d))
                if pico > 32000:
                    d = d * (32000.0 / pico)
                scipy.io.wavfile.write(fn, SR, d.astype(np.int16))
                total += 1
                if total % 250 == 0:
                    print(f"  {total} negativos...", flush=True)
            except Exception as e:
                fallos += 1
                if fallos <= 3:
                    print(f"  skip {texto!r}: {type(e).__name__}: {e}", flush=True)

    print(f"NEGATIVOS OK: {total} clips, {fallos} fallos", flush=True)
    print(f"total en disco: {len([f for f in os.listdir(OUT_DIR) if f.endswith('.wav')])}", flush=True)
    if total < 100:
        print("AVISO: muy pocos negativos, el entrenamiento sera fragil", flush=True)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        sys.exit(1)