"""Implementación de WakeWordProvider con openWakeWord (Apache-2.0).

Modelo provisional: 'hey_jarvis' (descarga automática de los releases
oficiales de openWakeWord). Para usar un modelo propio en el futuro basta
apuntar WAKE_WORD_MODEL a la ruta del .onnx (p. ej. models/wakeword/zix.onnx):
OpenWakeWordProvider acepta tanto nombres preentrenados como rutas de archivo.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from .wake_word_provider import WakeWordError, WakeWordProvider


class OpenWakeWordProvider(WakeWordProvider):
    def __init__(
        self,
        model: str = "hey_jarvis",
        threshold: float = 0.5,
        models_dir: Optional[Path | str] = None,
        speex_noise_suppression: bool = False,
    ) -> None:
        if not model or not str(model).strip():
            raise WakeWordError("El nombre del modelo de wake word está vacío")
        if not 0.0 < threshold <= 1.0:
            raise WakeWordError("El umbral del wake word debe estar en (0, 1]")
        self._model_name = str(model).strip()
        self._threshold = float(threshold)
        spec, key = self._resolve_spec(self._model_name, models_dir)
        self._key = key
        # Solo diagnóstico: último score observado (no altera el flujo).
        self.last_score: float | None = None

        from openwakeword.model import Model

        try:
            if speex_noise_suppression:
                try:
                    import speexdsp_ns  # noqa: F401 - comprueba que existe
                except ImportError as exc:
                    raise WakeWordError(
                        "WAKE_WORD_SPEEX_NS=1 requiere el paquete 'speexdsp-ns', "
                        "que solo existe para Linux (no para Windows)"
                    ) from exc
            self._model = Model(
                wakeword_models=[spec],
                inference_framework="onnx",
                enable_speex_noise_suppression=speex_noise_suppression,
            )
        except WakeWordError:
            raise
        except Exception as exc:  # noqa: BLE001 - error claro al usuario
            raise WakeWordError(
                f"No se pudo cargar el modelo de wake word '{self._model_name}'. "
                f"Ejecuta 'python scripts/setup_voice_models.py'. Detalle: {exc}"
            ) from exc

        loaded = list(self._model.models.keys())
        if self._key not in loaded:
            if loaded:
                self._key = loaded[0]
            else:
                raise WakeWordError(
                    f"El modelo '{self._model_name}' no cargó ningún modelo interno"
                )

    @property
    def name(self) -> str:
        return self._model_name

    @staticmethod
    def _resolve_spec(
        model: str, models_dir: Optional[Path | str]
    ) -> tuple[str, str]:
        """Devuelve (especificación para openwakeword, clave del resultado).

        - Ruta de archivo .onnx -> (ruta, nombre sin extensión).
        - Nombre preentrenado (alexa, hey_jarvis...) -> (nombre, nombre).
        - Otro nombre con models_dir -> (ruta models_dir/<nombre>.onnx, ...).
        """
        path = Path(model)
        if path.suffix == ".onnx" or path.exists():
            return str(path), path.stem
        try:
            from openwakeword import MODELS
        except ImportError:
            MODELS = {}
        if model in MODELS:
            return model, model
        if models_dir:
            candidate = Path(models_dir) / f"{model}.onnx"
            if candidate.exists():
                return str(candidate), candidate.stem
        return model, model

    def process(self, samples: np.ndarray) -> bool:
        arr = np.asarray(samples)
        if arr.size == 0:
            return False
        if arr.dtype != np.int16:
            arr = np.clip(arr.astype(np.float32) * 32767.0, -32768.0, 32767.0)
            arr = arr.astype(np.int16)
        try:
            prediction = self._model.predict(arr)
        except Exception as exc:  # noqa: BLE001 - nunca romper el loop de audio
            raise WakeWordError(f"Fallo procesando audio: {exc}") from exc
        score = prediction.get(self._key)
        if score is None:
            score = max(prediction.values()) if prediction else 0.0
        self.last_score = float(score)
        return float(score) >= self._threshold

    def reset(self) -> None:
        self._model.reset()