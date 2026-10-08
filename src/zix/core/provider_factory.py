"""Fábrica del proveedor de IA de ZIX.

Lee `AI_PROVIDER` de la configuración y devuelve el proveedor
correspondiente (`groq` por defecto, `xkiro` como alternativa).
El Agent nunca elige proveedor: recibe un AIProvider ya construido.
"""
from __future__ import annotations

from ..config import Config
from .ai_provider import AIProvider
from .groq_provider import GroqProvider
from .xkiro_provider import XkiroProvider


def build_provider(config: Config) -> AIProvider:
    """Construye el AIProvider según `config.ai_provider`."""
    name = (config.ai_provider or "groq").strip().lower()
    if name == "xkiro":
        return XkiroProvider(config)
    if name == "groq":
        return GroqProvider(config)
    raise ValueError(
        f"AI_PROVIDER={config.ai_provider!r} no válido. Usa 'groq' o 'xkiro'."
    )
