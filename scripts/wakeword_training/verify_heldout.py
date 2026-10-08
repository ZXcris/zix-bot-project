"""Verifica el wake word sobre clips REALES retenidos (opt-in, no lo toca pytest).

El objetivo es que nunca mas se publique un numero medido sobre los datos de
entrenamiento. La celda 7 de train_hey_zix.ipynb hacia `glob("positive/train")`
y eso es lo que produjo el falso 0.8834: puntuaba lo que el modelo memorizo.

Este script puntua clips que el modelo NO vio, y propone umbral.

Uso:
    python scripts/wakeword_training/verify_heldout.py data\\wakeword_real_16k
    python scripts/wakeword_training/verify_heldout.py data\\wakeword_real_16k \\
        --negativos runtime\\wakeword_test.wav --negativos runtime\\wakeword_wasapi.wav

Nunca toca models/ ni .env: solo lee.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _audio_utils import load_wav, medir, resample, to_int16  # noqa: E402

BLOQUE = 1280  # 80 ms a 16 kHz: lo que entrega AudioManager al pipeline
PROHIBIDO = ("positive/train", "positive\\train", "zix_model", "train/")


def barrer(int16: np.ndarray, proceso) -> float:
    """Score maximo recorriendo el audio en bloques de 80 ms, como en produccion."""
    if len(int16) < BLOQUE:
        return 0.0
    return max(
        float(proceso(int16[i: i + BLOQUE]) or 0.0)
        for i in range(0, len(int16) - BLOQUE + 1, BLOQUE)
    )


def mejor_umbral(positivos: list[float], negativos: list[float]) -> tuple[float | None, str]:
    """Umbral recomendado, o None si no hay separacion posible.

    Si hay separacion limpia se propone el punto medio entre el positivo mas
    bajo y el negativo mas alto: es el corte con mas margen, no el mas bajo que
    "funciona", que dejaria al modelo a un pelo de los falsos positivos.
    """
    if not positivos:
        return None, "sin positivos"
    if not negativos:
        return 0.5, "sin negativos: umbral por defecto 0.5"

    min_pos, max_neg = min(positivos), max(negativos)
    if min_pos > max_neg:
        corte = (min_pos + max_neg) / 2.0
        corte = min(max(corte, 0.01), 0.99)
        acierta = sum(1 for s in positivos if s >= corte) / len(positivos)
        falsos = sum(1 for s in negativos if s >= corte) / len(negativos)
        return corte, (
            f"corte con margen entre {max_neg:.3f} y {min_pos:.3f}; "
            f"acierta {acierta*100:.0f}%, falsos {falsos*100:.0f}%"
        )

    # Solapados: se busca el umbral con mas acierto que aun no meta falsos.
    for t in [round(x, 2) for x in np.arange(0.05, 1.0, 0.05)]:
        acierta = sum(1 for s in positivos if s >= t) / len(positivos)
        falsos = sum(1 for s in negativos if s >= t) / len(negativos)
        if falsos == 0 and acierta >= 0.8:
            return t, f"{acierta*100:.0f}% de positivos y 0 falsos positivos (sin margen)"
    mejor = max(
        (sum(1 for s in positivos if s >= t) / len(positivos)
         - sum(1 for s in negativos if s >= t) / len(negativos)
         for t in [round(x, 2) for x in np.arange(0.05, 1.0, 0.05)]),
        default=0.0,
    )
    return None, (
        f"no hay umbral que separe bien (solapamiento; mejor balance {mejor:.2f}). "
        "El modelo no distingue tus clips de los negativos: hay que reentrenar."
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Verifica el wake word sobre clips retenidos.")
    ap.add_argument("clips", help="carpeta con WAV positivos reales (NO los de entrenamiento)")
    ap.add_argument("--negativos", action="append", default=[],
                    help="WAV o carpeta con negativos reales (repetible)")
    ap.add_argument("--modelo", default="zix", help="nombre o ruta del modelo (default zix)")
    ap.add_argument("--modelos_dir", default=str(RAIZ / "models" / "wakeword"),
                    help="donde buscar el .onnx si pasas un nombre suelto")
    ap.add_argument("--umbral", type=float, default=0.5)
    args = ap.parse_args()

    if any(p in args.clips.lower() for p in PROHIBIDO):
        print("!" * 72)
        print("  ESO PARECE UNA CARPETA DE ENTRENAMIENTO.")
        print("  Ver aqui da un numero falso: el modelo memorizo esos clips.")
        print("  Usa clips reales aparte (p. ej. los que grabaste tu hoy).")
        print("!" * 72)
        return 1

    from zix.voice.openwakeword_wake_word import OpenWakeWordProvider

    try:
        prov = OpenWakeWordProvider(
            model=args.modelo,
            threshold=args.umbral,
            models_dir=args.modelos_dir,
        )
    except Exception as exc:  # noqa: BLE001 - mensaje claro al usuario
        print(f"ERROR: no se pudo cargar el modelo '{args.modelo}': {exc}")
        return 1

    positivos = sorted(Path(args.clips).glob("*.wav"))
    if not positivos:
        print(f"ERROR: no hay WAV en {args.clips}")
        return 1

    neg_paths: list[Path] = []
    for item in args.negativos:
        p = Path(item)
        if p.is_dir():
            neg_paths += sorted(p.glob("*.wav"))
        elif p.is_file():
            neg_paths.append(p)
        else:
            print(f"[!] negativo ignorado, no existe: {item}")

    def puntuar(ruta: Path) -> tuple[float, str]:
        sr, data = load_wav(ruta)
        data = resample(data, sr)
        dur, rms, _ = medir(data)
        return barrer(to_int16(data), prov.process), f"{dur:.2f}s rms={rms:.3f}"

    print("=" * 76)
    print(f"  POSITIVOS ({len(positivos)} clips de voz real que el modelo no vio)")
    print("=" * 76)
    sp, info_p = [], []
    for p in positivos:
        s, i = puntuar(p)
        sp.append(s)
        info_p.append(i)
        marca = "OK " if s >= args.umbral else "-- "
        print(f"  {marca}{s:.4f}  {p.name:<46} {i}")
    tasa = sum(1 for s in sp if s >= args.umbral) / len(sp)
    print(f"\n  disparan sobre el umbral {args.umbral}: "
          f"{sum(1 for s in sp if s >= args.umbral)}/{len(sp)}  ({tasa*100:.0f}%)")
    print(f"  media: {np.mean(sp):.4f}   maximo: {max(sp):.4f}")

    sn: list[float] = []
    if neg_paths:
        print()
        print("=" * 76)
        print(f"  NEGATIVOS ({len(neg_paths)} clips, no deberian disparar)")
        print("=" * 76)
        for p in neg_paths:
            s, i = puntuar(p)
            sn.append(s)
            marca = "FP!" if s >= args.umbral else "ok "
            print(f"  {marca}{s:.4f}  {p.name:<46} {i}")
        fps = sum(1 for s in sn if s >= args.umbral)
        print(f"\n  falsos positivos: {fps}/{len(sn)}")

    print()
    umbral, razon = mejor_umbral(sp, sn)
    print("=" * 76)
    if umbral is None:
        print("  VEREDICTO: NO LISTO")
        print(f"  {razon}")
        print("  El modelo no distingue tus clips del ruido. Hay que reentrenar")
        print("  con voz humana (ver data/wakeword_real/README.md).")
        rc = 1
    else:
        print(f"  UMBRAL RECOMENDADO: {umbral:.2f}   ({razon})")
        print(f"  Ponlo en .env:  WAKE_WORD_THRESHOLD={umbral:.2f}")
        print("  PRUEBA FINAL obligatoria: dilo en voz alta una vez y comprueba")
        print("  que dispara. Ningun archivo sustituye a eso.")
        rc = 0
    print("=" * 76)
    return rc


if __name__ == "__main__":
    sys.exit(main())
