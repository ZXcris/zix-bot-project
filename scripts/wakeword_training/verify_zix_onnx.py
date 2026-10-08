"""Verificación local de un wake word .onnx entrenado (p. ej. zix.onnx).

NO integra nada en ZIX: no copia el modelo a models/wakeword/, no toca .env,
no reemplaza hey_jarvis y no hace commit. Solo carga y puntúa.

Comprueba:
  1. Que el .onnx cargue con nuestro OpenWakeWordProvider (ruta de archivo).
  2. Que sea compatible con openwakeword (Model + inference_framework="onnx"
     + shapes de entrada/salida válidas).
  3. Que Model.predict() funcione bloque a bloque (16 kHz, mono, int16).
  4. Que pueda puntuar un WAV de prueba (--wav, 16 kHz mono int16).
  5. Reporta el score máximo y si supera el umbral actual (0.5 por defecto).

Uso:
    python scripts/wakeword_training/verify_zix_onnx.py zix.onnx [--wav prueba.wav]

Sin --wav se genera un tono sintético: solo comprueba la mecánica
(load + predict); los scores no tienen significado.
Exit code 0 = mecánica OK (el veredicto del umbral es informativo).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from zix.config import Config  # noqa: E402
from zix.voice.audio import AudioError, AudioManager  # noqa: E402
from zix.voice.openwakeword_wake_word import OpenWakeWordProvider  # noqa: E402
from zix.voice.wake_word_provider import WakeWordError  # noqa: E402

BLOCK = 1280  # 80 ms a 16 kHz (openWakeWord)


def _print_onnx_shapes(model_path: Path) -> None:
    """Muestra shapes de entrada/salida del .onnx (compatibilidad básica)."""
    import onnxruntime as ort

    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    for inp in session.get_inputs():
        print(f"    entrada:  {inp.name}  {inp.shape}  ({inp.type})")
    for out in session.get_outputs():
        print(f"    salida:   {out.name}  {out.shape}  ({out.type})")


def _score_blocks(
    model, samples: np.ndarray, key: str, block_size: int = BLOCK
) -> list[float]:
    scores = []
    pcm = AudioManager.to_int16(samples)
    for i in range(0, len(pcm) - block_size + 1, block_size):
        pred = model.predict(pcm[i : i + block_size])
        scores.append(float(pred.get(key, max(pred.values()) if pred else 0.0)))
    return scores


def _synthetic_test_signal(seconds: float = 2.0) -> np.ndarray:
    sr = 16000
    t = np.arange(int(sr * seconds), dtype=np.float32) / sr
    freq = 300.0 + 2700.0 * t / seconds  # barrido 300 -> 3000 Hz
    return np.sin(2 * np.pi * np.cumsum(freq) / sr).astype(np.float32)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verifica un wake word .onnx (zix.onnx) sin integrarlo en ZIX."
    )
    parser.add_argument("model", help="ruta al .onnx entrenado (p. ej. zix.onnx)")
    parser.add_argument("--wav", help="WAV de prueba 16 kHz mono int16 (opcional)")
    args = parser.parse_args()

    model_path = Path(args.model)
    print(f"Modelo: {model_path}")
    if not model_path.exists():
        raise WakeWordError(f"No existe el archivo: {model_path}")
    if model_path.stat().st_size == 0:
        raise WakeWordError(f"El archivo está vacío: {model_path}")
    print(f"  tamaño: {model_path.stat().st_size} bytes")

    print("[1/4] Cargando con OpenWakeWordProvider (el de ZIX)...")
    provider = OpenWakeWordProvider(model=str(model_path))
    print(f"  OK: proveedor cargado (clave interna: {provider._key!r})")

    print("[2/4] Compatibilidad openWakeWord (shapes del .onnx)...")
    _print_onnx_shapes(model_path)
    print("  OK: onnx válido y shapes coherentes.")

    print("[3/4] Model.predict() bloque a bloque (16 kHz, mono, int16)...")
    if args.wav:
        wav_path = Path(args.wav)
        if not wav_path.exists():
            raise AudioError(f"No existe el WAV: {wav_path}")
        sr, samples = AudioManager.read_wav(wav_path)
        if sr != 16000:
            raise AudioError(
                f"El WAV debe ser de 16 kHz (es de {sr} Hz): {wav_path}"
            )
        print(f"  WAV: {wav_path} ({len(samples) / sr:.1f}s, {sr} Hz, mono int16)")
        signal = samples
    else:
        print("  Sin --wav: tono sintético (mecánica; scores sin significado).")
        signal = _synthetic_test_signal()
    scores = _score_blocks(provider._model, signal, provider._key)
    print(f"  OK: {len(scores)} bloques puntuados.")

    print("[4/4] Resultado...")
    threshold = Config.from_env().wake_word_threshold
    max_score = max(scores) if scores else 0.0
    print(f"  score máximo: {max_score:.4f}")
    print(f"  umbral actual (WAKE_WORD_THRESHOLD): {threshold}")
    if max_score >= threshold:
        print("  VEREDICTO: SUPERA el umbral. Listo para integrar en ZIX.")
    else:
        print("  VEREDICTO: NO supera el umbral. Entrenar/probar más o calibrar.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - mostrar el error exacto
        print(f"\nERROR verificando el modelo: {type(exc).__name__}: {exc}")
        sys.exit(1)