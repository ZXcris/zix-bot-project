"""Prepara audios reales de "Hey ZIX" para Colab (opt-in, no lo toca pytest).

Valida y normaliza WAV a 16 kHz / mono / 16-bit, 1-3 s, con habla detectable.
Uso:
    python scripts/wakeword_training/prepare_real_clips.py data/wakeword_real --out data/wakeword_real_16k

Solo copia al --out los clips válidos. Los inválidos se listan con el motivo.
Nunca toca models/ ni .env.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import numpy as np


def _load_wav(path: Path) -> tuple[int, np.ndarray]:
    import wave

    with wave.open(str(path), "rb") as w:
        sr, ch, sw, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if sw == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128.0
    elif sw == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    else:
        raise ValueError(f"{path.name}: sample width {sw * 8}-bit no soportado (usa 16-bit)")
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return sr, data


def _resample(data: np.ndarray, sr: int, target: int = 16000) -> np.ndarray:
    if sr == target:
        return data
    from scipy import signal

    n = int(len(data) * target / sr)
    return signal.resample(data, n).astype(np.float32)


def _save_wav(path: Path, data: np.ndarray, sr: int = 16000) -> None:
    import wave

    pcm = np.clip(data, -1.0, 1.0)
    pcm = (pcm * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def main() -> int:
    ap = argparse.ArgumentParser(description="Valida/normaliza clips reales Hey ZIX a 16k mono.")
    ap.add_argument("input_dir", help="Carpeta con WAV grabados")
    ap.add_argument("--out", required=True, help="Carpeta destino con clips válidos normalizados")
    ap.add_argument("--min_seconds", type=float, default=0.7)
    ap.add_argument("--max_seconds", type=float, default=4.0)
    ap.add_argument("--min_rms", type=float, default=0.01)
    args = ap.parse_args()

    src = Path(args.input_dir)
    dst = Path(args.out)
    if not src.is_dir():
        print(f"ERROR: no existe {src}")
        return 1
    wavs = sorted([p for p in src.glob("*.wav") if p.name != ".gitkeep"])
    if not wavs:
        print(f"Sin WAV en {src}. Graba según data/wakeword_real/README.md y reintenta.")
        return 1
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)

    ok, bad = 0, 0
    for wav in wavs:
        try:
            sr, data = _load_wav(wav)
            data = _resample(data, sr)
            dur = len(data) / 16000
            rms = float(np.sqrt(np.mean(data**2))) if len(data) else 0.0
            peak = float(np.max(np.abs(data))) if len(data) else 0.0
            if not (args.min_seconds <= dur <= args.max_seconds):
                print(f"[X] {wav.name}: duración {dur:.2f}s fuera de rango")
                bad += 1
                continue
            if rms < args.min_rms or peak < 0.05:
                print(f"[X] {wav.name}: silencio/muy bajo (rms={rms:.4f} peak={peak:.3f})")
                bad += 1
                continue
            if peak > 0.99:
                print(f"[!] {wav.name}: posible clipping (peak={peak:.3f}), se acepta")
            _save_wav(dst / wav.name, data)
            print(f"[OK] {wav.name} ({dur:.2f}s rms={rms:.3f})")
            ok += 1
        except Exception as exc:  # noqa: BLE001 - reporte por archivo, no corte total
            print(f"[X] {wav.name}: {type(exc).__name__}: {exc}")
            bad += 1
    print(f"\nVálidos: {ok}, inválidos: {bad} -> {dst} (sube esto a Colab, celda 4b).")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
