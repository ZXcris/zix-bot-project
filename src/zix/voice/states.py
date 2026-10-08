"""Estados del asistente de voz de ZIX."""
from __future__ import annotations

from enum import Enum, auto


class State(Enum):
    """Máquina de estados del asistente por voz.

    IDLE: esperando el wake word. El micrófono solo alimenta al detector.
    LISTENING: capturando la frase del usuario (VAD gated).
    THINKING: transcribiendo (STT) y procesando con el Agent.
    SPEAKING: sintetizando (TTS) y reproduciendo la respuesta.
    CONVERSATION: ventana de 10 s tras la respuesta; se puede seguir
                  hablando sin wake word.
    """

    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()
    CONVERSATION = auto()