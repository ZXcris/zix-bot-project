"""Prueba de integración MANUAL del pipeline de voz (v0.2).

NO forma parte de la suite de pytest (no toca micrófono ni altavoz).
Ejecutar a mano:

    python scripts/integration_test_voice.py

Requiere .env con GROQ_API_KEY válida y modelos descargados
(scripts/setup_voice_models.py). Nunca imprime la API key.

Verifica:
1. Los modelos están en su sitio (wake word, voz Piper, espeak-ng-data).
2. Piper sintetiza un WAV real desde texto (sin micrófono).
3. Groq STT transcribe ese WAV (prueba real del flujo audio->texto).
4. El wake word (openWakeWord) carga y procesa silencio sin errores.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

from zix.config import Config, project_path  # noqa: E402
from zix.voice.audio import AudioManager  # noqa: E402
from zix.voice.groq_stt import GroqSTTProvider  # noqa: E402
from zix.voice.openwakeword_wake_word import OpenWakeWordProvider  # noqa: E402
from zix.voice.piper_tts import PiperTTSProvider  # noqa: E402

TEXT = "Esto es una prueba de voz de ZIX."


def main() -> int:
    config = Config.from_env()
    if not config.groq_api_key:
        print("ERROR: GROQ_API_KEY no está definida en .env. No se puede ejecutar la prueba real.")
        return 1

    # 1. Modelos presentes
    piper_onnx = project_path(config.piper_models_dir) / f"{config.piper_voice}.onnx"
    piper_json = project_path(config.piper_models_dir) / f"{config.piper_voice}.onnx.json"
    espeak = Path(config.piper_espeak_data_dir)
    for label, path in (
        ("voz Piper", piper_onnx),
        ("config Piper", piper_json),
        ("espeak-ng-data", espeak / "phontab"),
    ):
        assert path.exists(), f"Falta {label}: {path}"
    print(f"[OK] 1. Modelos presentes (voz, config y espeak-ng-data).")

    # 2. Piper sintetiza WAV real
    tts = PiperTTSProvider(config)
    out = Path(__file__).resolve().parents[1] / "runtime" / "integration_test.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    tts.synthesize(TEXT, out)
    sr, samples = AudioManager.read_wav(out)
    assert sr == 22050, f"Sample rate inesperado: {sr} (esperado 22050)"
    assert samples.size > 1000, "El WAV sintetizado está vacío."
    assert float(np.max(np.abs(samples))) > 0.01, "El WAV sintetizado es silencio."
    print(f"[OK] 2. Piper sintetizó {TEXT!r} -> {out.name} ({sr} Hz, {samples.size} muestras).")

    # 3. Groq STT transcribe el WAV sintetizado
    stt = GroqSTTProvider(config)
    text = stt.transcribe(out)
    assert text.strip(), f"La transcripción llegó vacía: {text!r}"
    print(f"[OK] 3. STT transcribió el audio sintetizado: {text!r}")

    # 4. Wake word carga y procesa silencio
    wake = OpenWakeWordProvider(
        model=config.wake_word_model,
        threshold=config.wake_word_threshold,
        models_dir=project_path(config.wake_models_dir),
    )
    assert wake.name == config.wake_word_model, f"Wake word inesperado: {wake.name}"
    silence = np.zeros(1280, dtype=np.int16)
    scores = wake.process(silence)
    assert not scores, f"El silencio activó el wake word: {scores}"
    wake.reset()
    print(f"[OK] 4. Wake word {wake.name} cargado y procesa silencio sin dispararse.")

    print()
    print("PRUEBA DE INTEGRACIÓN DE VOZ SUPERADA.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - mostrar el error exacto, no ocultarlo
        print(f"\nPRUEBA DE INTEGRACIÓN DE VOZ FALLIDA: {type(exc).__name__}: {exc}")
        sys.exit(1)