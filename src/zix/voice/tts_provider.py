"""Interfaz TTSProvider: contrato de cualquier síntesis de voz.

El ConversationManager depende solo de esta interfaz; hoy la implementa
Piper (local, GPL-3.0). synthesize() escribe un WAV mono en output_path.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class TTSError(Exception):
    """Error de síntesis (modelo ausente, espeak-ng, escritura...)."""


class TTSProvider(ABC):
    @abstractmethod
    def synthesize(self, text: str, output_path: Path | str) -> None:
        """Sintetiza `text` a un WAV mono en `output_path`."""