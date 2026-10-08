"""Máquina de estados de la conversación por voz de ZIX.

El ConversationManager coordina: wake word -> captura (VAD) -> STT -> Agent
-> TTS -> ventana de conversación temporal. NO depende de ningún proveedor
concreto: recibe callbacks inyectados (guardar audio, transcribir, ejecutar
al agente, hablar), por lo que es 100% probable con fakes y reloj falso.

Flujo (v0.2):
    IDLE --wake word--> LISTENING --frase--> THINKING --respuesta-->
    SPEAKING --fin TTS--> CONVERSATION --10 s sin orden--> IDLE

"Orden válida" (definición aprobada): transcripción con intención
comunicativa clara dirigida a ZIX y procesable por el Agent (con o sin
tool_call). NO reinician: silencio, ruido, audio sin habla, transcripción
vacía o claramente ininteligible, falsos positivos del VAD.

El wake word reactiva ZIX en cualquier momento (IDLE o CONVERSATION),
independientemente del temporizador.
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from ..config import Config
from .states import State
from .vad import VAD

logger = logging.getLogger("zix.voice.conversation")

# Callbacks inyectados (independencia de STT/LLM/TTS):
#   on_utterance_saved(np.ndarray) -> Path   guarda la frase capturada
#   transcribe(Path) -> str                  STT
#   run_agent(str) -> str                    Agent.run (núcleo v0.1)
#   speak(str) -> None                       TTS + reproducción (bloqueante)


class ConversationManager:
    def __init__(
        self,
        config: Config,
        *,
        on_utterance_saved: Callable[[np.ndarray], Path],
        transcribe: Callable[[Path], str],
        run_agent: Callable[[str], str],
        speak: Callable[[str], None],
        time_func: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._on_utterance_saved = on_utterance_saved
        self._transcribe = transcribe
        self._run_agent = run_agent
        self._speak = speak
        self._time = time_func
        self._vad = VAD(config.vad_threshold)
        self._state = State.IDLE
        self._conversation_deadline: Optional[float] = None
        self._reset_capture()
        if config.voice_continuous_mode:
            self.on_wake_word()

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------
    @property
    def state(self) -> State:
        return self._state

    def reset(self) -> None:
        """Vuelve a IDLE y limpia todo el estado interno."""
        self._state = State.IDLE
        self._conversation_deadline: Optional[float] = None
        self._reset_capture()

    # ------------------------------------------------------------------
    # Entradas del bucle de audio
    # ------------------------------------------------------------------
    def on_wake_word(self) -> None:
        """Wake word detectado: reactiva ZIX (IDLE o CONVERSATION)."""
        if self._state in (State.IDLE, State.CONVERSATION):
            logger.info("Escucha activada -> LISTENING")
            self._conversation_deadline = None
            self._state = State.LISTENING
            self._reset_capture()
        # En LISTENING ya estamos escuchando; en THINKING/SPEAKING ocupados.

    def feed_audio(self, samples: np.ndarray) -> None:
        """Alimenta un bloque de audio mono float32 [-1, 1].

        Solo en LISTENING/CONVERSATION se captura (VAD gated). Cuando la
        frase termina (timeout de silencio) pasa a THINKING y procesa con
        los callbacks; todo el flujo es síncrono (v0.2).
        """
        if self._state not in (State.LISTENING, State.CONVERSATION):
            return
        now = self._time()
        speech = self._vad.is_speech(samples)

        if not self._capturing:
            if speech:
                origin = self._state
                self._capturing = True
                self._capture_origin = origin
                self._speech_started_at = now
                self._last_speech_at = now
                self._speech_seconds = samples.size / self._config.voice_sample_rate
                self._buffer = [np.array(samples, copy=True)]
                if origin is State.CONVERSATION:
                    # seguimos capturando; el temporizador sigue corriendo
                    self._state = State.LISTENING
                logger.debug("Habla detectada (origen: %s)", origin.name)
            return

        self._buffer.append(np.array(samples, copy=True))
        if speech:
            self._speech_seconds += samples.size / self._config.voice_sample_rate
            self._last_speech_at = now
        elif now - self._last_speech_at >= self._config.vad_silence_timeout_seconds:
            self._end_capture()
            return
        if now - self._speech_started_at >= self._config.voice_max_utterance_seconds:
            logger.info("Frase máxima alcanzada, forzando fin de captura")
            self._end_capture()

    def tick(self) -> None:
        """Comprueba la ventana de conversación (llamar cada iteración)."""
        if self._config.voice_continuous_mode:
            return
        if self._conversation_deadline is None:
            return
        if self._time() >= self._conversation_deadline:
            logger.info("Ventana de conversación expirada -> IDLE")
            self._conversation_deadline = None
            self._state = State.IDLE
            self._reset_capture()

    # ------------------------------------------------------------------
    # Orden válida
    # ------------------------------------------------------------------
    def is_valid_order(self, text: Optional[str]) -> bool:
        """Heurística de "orden válida" (aprobada por el usuario).

        Válida: texto no vacío, con longitud mínima y al menos una palabra
        con caracteres alfanuméricos (intención comunicativa reconocible).
        Inválida: vacío, casi vacío, ruido, signos sueltos, STT ininteligible.
        """
        t = (text or "").strip()
        if not t:
            return False
        if len(t) < self._config.voice_order_min_chars:
            return False
        words = [w for w in re.split(r"\s+", t) if any(ch.isalnum() for ch in w)]
        return len(words) >= 1

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _reset_capture(self) -> None:
        self._capturing = False
        self._buffer: list[np.ndarray] = []
        self._capture_origin: Optional[State] = None
        self._speech_started_at: Optional[float] = None
        self._last_speech_at: Optional[float] = None
        self._speech_seconds = 0.0

    def _end_capture(self) -> None:
        # duración del HABLA real (no incluye la cola de silencio)
        speech_seconds = self._speech_seconds
        self._capturing = False
        buffer, self._buffer = self._buffer, []
        origin = self._capture_origin
        self._capture_origin = None

        if speech_seconds < self._config.vad_min_speech_seconds:
            logger.debug(
                "Frase demasiado corta (%.2f s): falso positivo de VAD", speech_seconds
            )
            return  # descartar: seguimos en LISTENING o CONVERSATION

        samples = np.concatenate([b for b in buffer if b.size])
        if samples.size == 0:
            return
        try:
            path = self._on_utterance_saved(samples)
        except Exception:  # noqa: BLE001 - nunca romper el loop de audio
            logger.exception("Fallo guardando la frase capturada")
            return
        self._state = State.THINKING
        self._process_utterance(path, origin)

    def _process_utterance(self, path: Path, origin: Optional[State]) -> None:
        try:
            text = self._transcribe(path)
        except Exception:  # noqa: BLE001 - STTError y cualquier otro
            logger.exception("Fallo en STT")
            self._return_to(origin)
            return
        text = (text or "").strip()
        if not self.is_valid_order(text):
            logger.info("Orden no válida (%r): no se reinicia el temporizador", text)
            self._return_to(origin)
            return

        logger.info("Orden válida: %r", text)
        self._conversation_deadline = None  # la ventana se reabre tras responder
        try:
            response = self._run_agent(text)
        except Exception:  # noqa: BLE001 - el Agent real nunca lanza
            logger.exception("Fallo ejecutando el Agent")
            self._return_to(origin)
            return
        response = (response or "").strip()
        if not response:
            self._return_to(origin)
            return

        self._state = State.SPEAKING
        try:
            self._speak(response)
        except Exception:  # noqa: BLE001 - TTS/audio: se informa y se continúa
            logger.exception("Fallo en TTS/reproducción de la respuesta")
        self._state = State.CONVERSATION
        self._conversation_deadline = (
            self._time() + self._config.voice_conversation_timeout_seconds
        )
        logger.info("Respondido -> CONVERSATION (%s s)", self._config.voice_conversation_timeout_seconds)

    def _return_to(self, origin: Optional[State]) -> None:
        if origin is State.CONVERSATION:
            self._state = State.CONVERSATION  # ventana sigue activa (no reinicia)
        elif origin is State.LISTENING:
            self._state = State.LISTENING  # tras wake word: seguir esperando la orden
        else:
            self._state = State.IDLE