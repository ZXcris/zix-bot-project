"""Implementación de STTProvider con Whisper de Groq (free tier).

Modelo por defecto: whisper-large-v3-turbo (verificado en la cuenta Groq
vía models.list()). Usa la misma GROQ_API_KEY del agente; nunca la imprime.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..config import Config
from .stt_provider import STTError, STTProvider


class GroqSTTProvider(STTProvider):
    def __init__(self, config: Config) -> None:
        if not config.groq_api_key:
            raise ValueError(
                "GROQ_API_KEY no está definida. Copia .env.example a .env "
                "y añade tu clave gratuita de https://console.groq.com"
            )
        self._config = config
        self._client: Optional[object] = None

    def _get_client(self) -> object:
        if self._client is None:
            from groq import Groq

            self._client = Groq(
                api_key=self._config.groq_api_key,
                timeout=self._config.groq_timeout_seconds,
            )
        return self._client

    def transcribe(self, audio_path: Path | str) -> str:
        path = Path(audio_path)
        if not path.exists():
            raise STTError(f"No existe el audio a transcribir: {path}")
        try:
            with open(path, "rb") as f:
                kwargs = {
                    "model": self._config.stt_model,
                    "file": (path.name, f),
                }
                if self._config.stt_language:
                    kwargs["language"] = self._config.stt_language
                result = self._get_client().audio.transcriptions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - traducir cualquier fallo
            raise STTError(
                f"Fallo de STT ({type(exc).__name__}): {exc}"
            ) from exc
        text = getattr(result, "text", "") or ""
        return text.strip()