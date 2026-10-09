"""STT local con faster-whisper: el audio nunca sale de este equipo.

Por que existe (2026-10-09): con STT_PROVIDER=groq, cada frase que le dices a
ZIX viaja a api.groq.com. Eso incluye el audio de una activacion falsa de la
palabra de activacion: si un podcast dice la frase de disparo, ZIX graba lo que
suene despues y lo sube. Con este proveedor eso no ocurre: se transcribe aqui.

Ventajas sobre el de nube:
- Privacidad: nada sale del equipo.
- Funciona sin internet.
- Sin coste ni cuota.

Coste: mas lento en CPU (con GPU, comparable), y hay que descargar el modelo
una vez (~1,5 GB para 'small', ~460 MB para 'base').

Instalacion (no se hace sola, es una descarga grande):

    .venv\\Scripts\\python.exe -m pip install faster-whisper

Y luego en .env:

    STT_PROVIDER=local
    STT_LOCAL_MODEL=base        # tiny | base | small | medium | large-v3
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .stt_provider import STTError, STTProvider

# Modelos aceptados y su tamano aproximado de descarga, para el mensaje de error.
TAMANOS = {
    "tiny": "~75 MB",
    "base": "~145 MB",
    "small": "~460 MB",
    "medium": "~1,5 GB",
    "large-v3": "~3 GB",
}


class LocalWhisperSTTProvider(STTProvider):
    """Transcribe con faster-whisper en local. Sin red, sin cuota."""

    def __init__(
        self,
        model_name: str = "base",
        language: str = "es",
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
    ) -> None:
        if not model_name or not str(model_name).strip():
            raise STTError("El nombre del modelo STT local esta vacio")
        self._model_name = str(model_name).strip()
        self._language = (language or "es").strip() or "es"
        self._device = device or os.getenv("STT_LOCAL_DEVICE") or None
        self._compute_type = (
            compute_type or os.getenv("STT_LOCAL_COMPUTE_TYPE") or None
        )
        self._model = None
        self.last_score: float | None = None

    @property
    def name(self) -> str:
        return f"faster-whisper:{self._model_name} (local)"

    def _get_model(self):
        """Carga perezosa: importar faster-whisper cuesta si no se usa."""
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            tam = TAMANOS.get(self._model_name, "?")
            raise STTError(
                "STT local necesita 'faster-whisper', que no esta instalado. "
                f"Instálalo con: .venv\\Scripts\\python.exe -m pip install faster-whisper "
                f"(modelo '{self._model_name}' ocupa {tam} la primera vez)."
            ) from exc
        kwargs = {}
        if self._device:
            kwargs["device"] = self._device
        if self._compute_type:
            kwargs["compute_type"] = self._compute_type
        try:
            self._model = WhisperModel(self._model_name, **kwargs)
        except Exception as exc:  # noqa: BLE001 - mensaje accionable
            raise STTError(
                f"No se pudo cargar el modelo local '{self._model_name}': {exc}"
            ) from exc
        return self._model

    def transcribe(self, wav_path: Path) -> str:
        try:
            model = self._get_model()
        except STTError:
            raise
        try:
            segmentos, info = model.transcribe(
                str(wav_path),
                language=self._language,
                beam_size=1,
                vad_filter=True,
            )
            texto = "".join(s.text for s in segmentos).strip()
            self.last_score = float(getattr(info, "language_probability", 0.0) or 0.0)
            return texto
        except STTError:
            raise
        except Exception as exc:  # noqa: BLE001 - nunca romper el bucle de audio
            raise STTError(f"Fallo transcribiendo en local: {exc}") from exc

    def reset(self) -> None:
        """faster-whisper no mantiene estado entre frases."""
        return None


def disponible() -> bool:
    """True si faster-whisper esta instalado, sin importar el modelo."""
    import importlib.util

    return importlib.util.find_spec("faster_whisper") is not None


def construir_si_es_posible(
    model_name: str = "base", language: str = "es"
) -> Optional[LocalWhisperSTTProvider]:
    """Devuelve el proveedor local, o None si faster-whisper no esta instalado."""
    if not disponible():
        return None
    return LocalWhisperSTTProvider(model_name=model_name, language=language)
