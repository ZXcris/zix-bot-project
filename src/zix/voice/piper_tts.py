"""Implementación de TTSProvider con Piper (local, 100% sin red).

Voz por defecto: es_MX-claude-high (models/piper/, descargada por
scripts/setup_voice_models.py desde HuggingFace - rhasspy/piper-voices).

Nota (Windows): el espeak-ng incluido en el wheel de piper-tts no puede
leer sus datos desde rutas con caracteres no-ASCII (p. ej. "Imágenes" en la
ruta de este proyecto). Por eso los datos de espeak-ng se copian a
%LOCALAPPDATA%\\zix\\espeak-ng-data (siempre ASCII) y se pasan explícitamente.
"""
from __future__ import annotations

import os
import wave
from pathlib import Path
from typing import Optional

from ..config import Config, project_path
from .tts_provider import TTSError, TTSProvider


class PiperTTSProvider(TTSProvider):
    def __init__(self, config: Config) -> None:
        self._config = config
        self._voice: Optional[object] = None

    def _load(self) -> None:
        config = self._config
        model_path = project_path(config.piper_models_dir) / (
            f"{config.piper_voice}.onnx"
        )
        if not model_path.exists():
            raise TTSError(
                f"No existe la voz {config.piper_voice!r} en {model_path}. "
                "Ejecuta 'python scripts/setup_voice_models.py'."
            )
        espeak_dir = Path(config.piper_espeak_data_dir).resolve()
        if not (espeak_dir / "phontab").exists():
            raise TTSError(
                f"No existen los datos de espeak-ng en {espeak_dir}. "
                "Ejecuta 'python scripts/setup_voice_models.py'."
            )
        if not espeak_dir.as_posix().isascii():
            raise TTSError(
                f"espeak-ng no puede leer rutas no-ASCII: {espeak_dir}. "
                "Configura PIPER_ESPEAK_DATA_DIR con una ruta ASCII."
            )
        os.environ["ESPEAK_DATA_PATH"] = str(espeak_dir)

        from piper import PiperVoice

        try:
            self._voice = PiperVoice.load(model_path, espeak_data_dir=espeak_dir)
        except Exception as exc:  # noqa: BLE001 - error claro al usuario
            raise TTSError(f"Fallo cargando la voz de Piper: {exc}") from exc

    def synthesize(self, text: str, output_path: Path | str) -> None:
        if not text or not text.strip():
            raise TTSError("No se puede sintetizar texto vacío")
        if self._voice is None:
            self._load()
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            with wave.open(str(out), "wb") as wav:
                self._voice.synthesize_wav(text, wav)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001 - error claro al usuario
            raise TTSError(f"Fallo sintetizando la voz: {exc}") from exc
        if not out.exists() or out.stat().st_size == 0:
            raise TTSError("La síntesis no produjo audio")