"""Interfaz STTProvider: contrato de cualquier transcripción de voz a texto.

El ConversationManager depende solo de esta interfaz (y de la función
Agent.run): hoy la implementa Groq Whisper; mañana puede ser otra sin
tocar el pipeline.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class STTError(Exception):
    """Error de transcripción (red, cuota, formato...)."""


class STTProvider(ABC):
    @abstractmethod
    def transcribe(self, audio_path: Path | str) -> str:
        """Transcribe un WAV mono a texto. Lanza STTError si falla."""