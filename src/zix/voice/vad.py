"""VAD (voice activity detection) por energía RMS.

Simple, sin dependencias de red y sin estado interno de aprendizaje:
un bloque se considera habla si su RMS >= threshold. Los bloques se esperan
en float32 mono con amplitud en [-1, 1].

La lógica de inicio/fin de frase (duración mínima, timeout de silencio) vive
en ConversationManager; esta clase solo clasifica bloques.
"""
from __future__ import annotations

import numpy as np


class VAD:
    def __init__(self, threshold: float = 0.02) -> None:
        if threshold < 0:
            raise ValueError("El umbral de VAD no puede ser negativo")
        self.threshold = float(threshold)

    @staticmethod
    def rms(samples: np.ndarray) -> float:
        """Root mean square de una señal mono en float32 [-1, 1]."""
        if samples is None or samples.size == 0:
            return 0.0
        arr = np.asarray(samples, dtype=np.float64)
        return float(np.sqrt(np.mean(np.square(arr))))

    def is_speech(self, samples: np.ndarray) -> bool:
        """True si el bloque contiene habla (RMS >= threshold)."""
        return self.rms(samples) >= self.threshold