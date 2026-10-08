"""Interfaz WakeWordProvider: contrato de cualquier detector de wake word.

El núcleo del pipeline solo conoce esta interfaz: hoy la implementa
openWakeWord con "hey_jarvis"; en el futuro se sustituirá por un modelo
propio "zix.onnx" (OpenWakeWordProvider ya acepta una ruta al modelo).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class WakeWordError(Exception):
    """Error de carga o procesamiento del wake word."""


class WakeWordProvider(ABC):
    """Detector de wake word intercambiable.

    process() recibe bloques mono float32 [-1, 1] a 16 kHz y devuelve True
    cuando se detecta el wake word en ese bloque.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre del modelo activo (p. ej. 'hey_jarvis' o 'zix')."""

    @abstractmethod
    def process(self, samples: np.ndarray) -> bool:
        """Procesa un bloque de audio; True si detecta el wake word."""

    @abstractmethod
    def reset(self) -> None:
        """Limpia el estado interno (búferes de ventanas previas)."""