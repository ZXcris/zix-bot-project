"""Utilidades de WAV compartidas por los scripts de wakeword (opt-in).

Solo se usa desde `scripts/wakeword_training/`. No lo importa pytest ni el
paquete `zix`: es una dependencia del proceso de entrenamiento, no del runtime.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

SR_OBJETIVO = 16000


def load_wav(path: Path) -> tuple[int, np.ndarray]:
    """Lee WAV y devuelve (sample_rate, float32 en [-1, 1], mono)."""
    import wave

    with wave.open(str(path), "rb") as w:
        ch, an, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if an == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif an == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    else:
        raise ValueError(f"{path.name}: sample width {an * 8}-bit no soportado (usa 16-bit)")
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return sr, data.astype(np.float32)


def resample(data: np.ndarray, sr: int, target: int = SR_OBJETIVO) -> np.ndarray:
    if sr == target:
        return data
    from scipy import signal

    n = int(len(data) * target / sr)
    return signal.resample(data, n).astype(np.float32)


def save_wav(path: Path, data: np.ndarray, sr: int = SR_OBJETIVO) -> None:
    import wave

    pcm = np.clip(data, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def downsample(audio: np.ndarray) -> np.ndarray:
    """De float32 (n, canales) a float32 mono en [-1, 1]."""
    arr = np.asarray(audio, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.mean(axis=1)
    return np.clip(arr, -1.0, 1.0)


def to_int16(data: np.ndarray) -> np.ndarray:
    return np.clip(data * 32767.0, -32768.0, 32767.0).astype(np.int16)


def speech_fraction(int16: np.ndarray, frame: int = 480) -> float:
    """Proporcion de tramas que Silero VAD marca como habla.

    Devuelve 0.0 si openWakeWord no esta disponible: los scripts must seguir
    funcionando sin silero.
    """
    if len(int16) < frame:
        return 0.0
    try:
        from openwakeword.vad import VAD
    except Exception:  # noqa: BLE001 - silero es opcional
        return 0.0
    try:
        vad = VAD()
        scores = []
        for i in range(0, len(int16) - frame + 1, frame):
            scores.append(float(vad.predict(int16[i: i + frame], frame_size=frame)))
        vad.reset_states()
    except Exception:  # noqa: BLE001 - un fallo del VAD no debe parar la grabacion
        return 0.0
    if not scores:
        return 0.0
    return sum(1 for s in scores if s > 0.5) / len(scores)


def medir(data: np.ndarray) -> tuple[float, float, float]:
    """(duracion_s, rms, pico) de audio float32 mono."""
    if len(data) == 0:
        return 0.0, 0.0, 0.0
    return len(data) / SR_OBJETIVO, float(np.sqrt(np.mean(data ** 2))), float(np.max(np.abs(data)))
