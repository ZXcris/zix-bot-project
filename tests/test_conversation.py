"""Tests del ConversationManager (máquina de estados + temporizador).

Sin hardware, sin red y sin proveedores reales: reloj falso + callbacks
fakes. La lógica es independiente de STT/LLM/TTS (todo es inyectado).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from zix.config import Config
from zix.voice.conversation import ConversationManager
from zix.voice.states import State

BLOCK = 1280
SILENCE = np.zeros(BLOCK, dtype=np.float32)
SPEECH = np.full(BLOCK, 0.1, dtype=np.float32)


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeTranscriber:
    def __init__(self, *texts: str) -> None:
        self.queue = list(texts)
        self.calls: list[Path] = []

    def __call__(self, path: Path) -> str:
        self.calls.append(path)
        return self.queue.pop(0) if self.queue else ""


def make_config(**overrides) -> Config:
    base = dict(
        groq_api_key="fake",
        voice_sample_rate=16000,
        voice_block_size=BLOCK,
        vad_threshold=0.02,
        vad_silence_timeout_seconds=0.5,
        vad_min_speech_seconds=0.3,
        voice_max_utterance_seconds=30.0,
        voice_conversation_timeout_seconds=10.0,
        voice_order_min_chars=2,
    )
    base.update(overrides)
    return Config(**base)


def make_manager(
    clock: FakeClock,
    transcribe=None,
    agent=None,
    speak=None,
    config=None,
):
    saved: list[np.ndarray] = []
    spoken: list[str] = []
    ran: list[str] = []

    def default_save(samples: np.ndarray) -> Path:
        saved.append(samples)
        return Path("fake_utterance.wav")

    def default_agent(text: str) -> str:
        ran.append(text)
        return "Respuesta de prueba de ZIX."

    def default_speak(text: str) -> None:
        spoken.append(text)

    manager = ConversationManager(
        config or make_config(),
        on_utterance_saved=default_save,
        transcribe=transcribe or (lambda p: "abre Chrome"),
        run_agent=agent or default_agent,
        speak=speak or default_speak,
        time_func=clock,
    )
    manager._saved = saved
    manager._spoken = spoken
    manager._ran = ran
    return manager


def feed_speech(manager, clock, blocks: int = 5) -> None:
    for _ in range(blocks):
        manager.feed_audio(SPEECH)
        clock.advance(0.08)


def feed_silence_until_timeout(manager, clock) -> None:
    for _ in range(10):
        manager.feed_audio(SILENCE)
        clock.advance(0.1)
        if manager.state is not State.LISTENING:
            return


def complete_utterance(manager, clock, blocks: int = 5) -> None:
    """Habla + silencio -> captura -> THINKING -> ... -> CONVERSATION."""
    feed_speech(manager, clock, blocks)
    feed_silence_until_timeout(manager, clock)


# ----------------------------------------------------------------------
# Wake word
# ----------------------------------------------------------------------
def test_wake_word_idle_to_listening():
    clock = FakeClock()
    m = make_manager(clock)
    assert m.state is State.IDLE
    m.on_wake_word()
    assert m.state is State.LISTENING


def test_wake_word_in_conversation_reactivates():
    clock = FakeClock()
    m = make_manager(clock)
    m.on_wake_word()
    complete_utterance(m, clock)
    assert m.state is State.CONVERSATION
    m.on_wake_word()
    assert m.state is State.LISTENING
    # la ventana anterior queda cancelada: no expira aunque pase el tiempo
    clock.advance(60)
    m.tick()
    assert m.state is State.LISTENING


def test_wake_word_ignored_while_listening():
    clock = FakeClock()
    m = make_manager(clock)
    m.on_wake_word()
    m.on_wake_word()
    assert m.state is State.LISTENING


def test_continuous_mode_starts_listening_and_never_times_out():
    clock = FakeClock()
    m = make_manager(clock, config=make_config(voice_continuous_mode=True))
    assert m.state is State.LISTENING
    complete_utterance(m, clock)
    assert m.state is State.CONVERSATION
    clock.advance(3600)
    m.tick()
    assert m.state is State.CONVERSATION


# ----------------------------------------------------------------------
# Flujo completo
# ----------------------------------------------------------------------
def test_full_flow_wake_order_response_conversation():
    clock = FakeClock()
    transcribe = FakeTranscriber("abre Chrome")
    m = make_manager(clock, transcribe=transcribe)

    m.on_wake_word()
    complete_utterance(m, clock)

    assert m.state is State.CONVERSATION
    assert transcribe.calls == [Path("fake_utterance.wav")]
    assert m._ran == ["abre Chrome"]
    assert m._spoken == ["Respuesta de prueba de ZIX."]
    assert len(m._saved) == 1
    # la frase guardada contiene habla real (no un falso positivo)
    assert float(np.max(np.abs(m._saved[0]))) > 0.01


def test_silence_does_not_trigger_capture():
    clock = FakeClock()
    transcribe = FakeTranscriber()
    m = make_manager(clock, transcribe=transcribe)
    m.on_wake_word()
    for _ in range(30):
        m.feed_audio(SILENCE)
        clock.advance(0.1)
        m.tick()
    assert m.state is State.LISTENING
    assert not transcribe.calls


def test_vad_false_positive_is_discarded():
    clock = FakeClock()
    transcribe = FakeTranscriber()
    m = make_manager(clock, transcribe=transcribe)
    m.on_wake_word()
    feed_speech(m, clock, blocks=1)  # 0.08 s < vad_min_speech_seconds (0.3)
    feed_silence_until_timeout(m, clock)
    assert m.state is State.LISTENING
    assert not transcribe.calls


def test_max_utterance_forces_capture_end():
    clock = FakeClock()
    transcribe = FakeTranscriber("abre Chrome")
    m = make_manager(
        clock, transcribe=transcribe, config=make_config(voice_max_utterance_seconds=1.0)
    )
    m.on_wake_word()
    feed_speech(m, clock, blocks=14)  # 1.04 s > max 1.0 -> fin forzado
    assert m.state is State.CONVERSATION
    assert m._spoken == ["Respuesta de prueba de ZIX."]


# ----------------------------------------------------------------------
# Ventana de conversación (10 s)
# ----------------------------------------------------------------------
def test_conversation_window_expires_to_idle():
    clock = FakeClock()
    m = make_manager(clock)
    m.on_wake_word()
    complete_utterance(m, clock)
    assert m.state is State.CONVERSATION
    clock.advance(9.0)
    m.tick()
    assert m.state is State.CONVERSATION
    clock.advance(1.5)
    m.tick()
    assert m.state is State.IDLE


def test_valid_order_resets_the_window():
    clock = FakeClock()
    transcribe = FakeTranscriber("abre Chrome", "¿y eso por qué?")
    m = make_manager(clock, transcribe=transcribe)
    m.on_wake_word()
    complete_utterance(m, clock)  # respuesta a las t=1000.96 -> deadline 1010.96
    deadline_1 = m._conversation_deadline
    assert deadline_1 is not None

    clock.advance(9.0)  # 1009.96: a 1 s de expirar
    assert m.state is State.CONVERSATION
    complete_utterance(m, clock)  # orden válida -> se reabre la ventana
    assert m.state is State.CONVERSATION
    assert m._conversation_deadline > deadline_1

    clock.advance(9.5)  # si la ventana NO se hubiera reiniciado, ya habría expirado
    m.tick()
    assert m.state is State.CONVERSATION
    clock.advance(1.0)
    m.tick()
    assert m.state is State.IDLE


def test_valid_order_without_tool_call_counts_as_interaction():
    clock = FakeClock()
    transcribe = FakeTranscriber("¿qué es un agujero negro?")
    m = make_manager(clock, transcribe=transcribe, agent=lambda t: "Buena pregunta.")
    m.on_wake_word()
    complete_utterance(m, clock)
    assert m.state is State.CONVERSATION
    assert m._spoken == ["Buena pregunta."]


# ----------------------------------------------------------------------
# Orden no válida: no reinicia el temporizador
# ----------------------------------------------------------------------
def test_invalid_order_does_not_reset_window():
    clock = FakeClock()
    transcribe = FakeTranscriber("abre Chrome", "")  # primera válida, segunda vacía
    m = make_manager(clock, transcribe=transcribe)
    m.on_wake_word()
    complete_utterance(m, clock)
    deadline_1 = m._conversation_deadline

    clock.advance(9.0)
    complete_utterance(m, clock)  # orden no válida (vacía)
    assert m.state is State.CONVERSATION
    assert m._conversation_deadline == deadline_1  # NO se reinició
    assert m._ran == ["abre Chrome"]  # el Agent solo ejecutó la primera orden

    clock.advance(1.0)  # 10 s desde la primera respuesta
    m.tick()
    assert m.state is State.IDLE


def test_noise_transcription_does_not_reset_window():
    clock = FakeClock()
    transcribe = FakeTranscriber("abre Chrome", "!!  ..  !")
    m = make_manager(clock, transcribe=transcribe)
    m.on_wake_word()
    complete_utterance(m, clock)
    deadline_1 = m._conversation_deadline

    clock.advance(9.0)
    complete_utterance(m, clock)
    assert m.state is State.CONVERSATION
    assert m._conversation_deadline == deadline_1
    assert m._ran == ["abre Chrome"]  # la segunda transcripción no ejecutó al Agent


def test_invalid_order_after_wake_word_keeps_listening():
    clock = FakeClock()
    transcribe = FakeTranscriber("   ", "abre Chrome")
    m = make_manager(clock, transcribe=transcribe)
    m.on_wake_word()
    complete_utterance(m, clock)
    assert m.state is State.LISTENING  # sigue esperando la orden real
    assert not m._ran
    complete_utterance(m, clock)
    assert m.state is State.CONVERSATION
    assert m._ran == ["abre Chrome"]


# ----------------------------------------------------------------------
# Orden válida (heurística independiente de STT/LLM)
# ----------------------------------------------------------------------
def test_is_valid_order_cases():
    m = make_manager(FakeClock())
    for valid in (
        "abre Chrome",
        "qué hora es",
        "calcula 25 por 48",
        "¿y eso por qué?",
        "¿qué acabas de decir?",
        "cuéntame algo sobre eso",
        "12345",
        "a b",  # mínimo de longitud (2) con palabras reales
    ):
        assert m.is_valid_order(valid), valid
    for invalid in (
        "",
        "   ",
        ".",
        "..",
        "!!",
        "?",
        "a",  # por debajo del mínimo de caracteres
        "¡",
        "\t\n",
    ):
        assert not m.is_valid_order(invalid), invalid


# ----------------------------------------------------------------------
# Robustez del bucle
# ----------------------------------------------------------------------
def test_transcribe_failure_does_not_crash_loop():
    clock = FakeClock()

    def broken_transcribe(path):
        raise RuntimeError("STT caído")

    m = make_manager(clock, transcribe=broken_transcribe)
    m.on_wake_word()
    complete_utterance(m, clock)
    assert m.state is State.LISTENING  # vuelve a escuchar sin romperse


def test_speak_failure_keeps_conversation_open():
    clock = FakeClock()

    def broken_speak(text):
        raise RuntimeError("altavoz caído")

    m = make_manager(clock, speak=broken_speak)
    m.on_wake_word()
    complete_utterance(m, clock)
    assert m.state is State.CONVERSATION  # se informa pero sigue en ventana
    assert m._conversation_deadline is not None


def test_tick_works_before_any_capture():
    """Regresión: tick() no debe fallar antes de la primera conversación."""
    clock = FakeClock()
    m = make_manager(clock)
    m.tick()
    m.on_wake_word()
    m.tick()  # LISTENING sin deadline
    assert m.state is State.LISTENING


def test_feed_audio_ignored_in_idle():
    clock = FakeClock()
    m = make_manager(clock)
    feed_speech(m, clock, blocks=5)
    feed_silence_until_timeout(m, clock)
    assert m.state is State.IDLE
    assert not m._saved