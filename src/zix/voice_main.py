"""Punto de entrada del asistente por voz de ZIX (v0.2).

    Micrófono -> Wake Word -> STT (Groq Whisper) -> Agent -> TTS (Piper)
              -> Altavoz -> ventana de conversación de 10 s

Solo conecta componentes existentes: NO contiene lógica propia de negocio.
Ejecutar:
    python -m zix.voice_main

Requiere: modelos descargados (scripts/setup_voice_models.py), GROQ_API_KEY
en .env y un micrófono + altavoz. Ctrl+C para salir.
"""
from __future__ import annotations

import itertools
import logging
import sys
import time
from typing import Tuple

import numpy as np

from zix.config import Config, project_path
from zix.core.agent import Agent
from zix.core.provider_factory import build_provider
from zix.core.tool_executor import ToolExecutor
from zix.core.tool_registry import ToolRegistry
from zix.tools import register_builtin_tools
from zix.voice.audio import AudioManager
from zix.voice.conversation import ConversationManager
from zix.voice.groq_stt import GroqSTTProvider
from zix.voice.openwakeword_wake_word import OpenWakeWordProvider
from zix.voice.piper_tts import PiperTTSProvider

logger = logging.getLogger("zix.voice_main")


def build_pipeline(
    config: Config,
) -> Tuple[ConversationManager, AudioManager, OpenWakeWordProvider]:
    """Construye y conecta el pipeline de voz con el Agent existente."""
    registry = ToolRegistry()
    register_builtin_tools(registry)
    provider = build_provider(config)
    executor = ToolExecutor(registry)
    agent = Agent(provider=provider, executor=executor, config=config)

    audio = AudioManager(
        samplerate=config.voice_sample_rate,
        block_size=config.voice_block_size,
        device=config.audio_input_device or None,
        input_samplerate=config.audio_input_samplerate or None,
        input_channels=config.audio_input_channels or None,
    )
    wake = OpenWakeWordProvider(
        model=config.wake_word_model,
        threshold=config.wake_word_threshold,
        models_dir=project_path(config.wake_models_dir),
        speex_noise_suppression=config.wake_word_speex_ns,
    )
    stt = GroqSTTProvider(config)
    tts = PiperTTSProvider(config)

    runtime = project_path(config.voice_runtime_dir)
    runtime.mkdir(parents=True, exist_ok=True)
    counter = itertools.count(1)

    def save_utterance(samples) -> None:
        path = runtime / f"utterance_{next(counter):04d}.wav"
        AudioManager.write_wav(path, samples, config.voice_sample_rate)
        return path

    def speak(text: str) -> None:
        out = runtime / f"response_{next(counter):04d}.wav"
        tts.synthesize(text, out)
        audio.play(out)

    conversation = ConversationManager(
        config,
        on_utterance_saved=save_utterance,
        transcribe=stt.transcribe,
        run_agent=agent.run,
        speak=speak,
    )
    return conversation, audio, wake


def main() -> int:
    config = Config.from_env()
    if config.ai_provider == "xkiro" and not config.xkiro_api_key:
        print("No se encontró XKIRO_API_KEY en .env. No se puede ejecutar ZIX por voz.")
        return 1
    if config.ai_provider == "groq" and not config.groq_api_key:
        print("No se encontró GROQ_API_KEY en .env. No se puede ejecutar ZIX por voz.")
        return 1

    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    conversation, audio, wake = build_pipeline(config)

    print("ZIX v0.2 — asistente por voz")
    wake_status = "omitido" if config.voice_continuous_mode else wake.name
    print(f"Wake word: {wake_status} | STT: {config.stt_model} | TTS: {config.piper_voice}")
    print(f"Micrófono: {config.audio_input_device or 'por defecto del sistema'}")
    if config.voice_continuous_mode:
        print("Modo continuo: habla directamente. Ctrl+C para salir.")
    else:
        print("Habla el wake word para activarme. Ctrl+C para salir.")
    print("-" * 60)

    try:
        # Diagnóstico temporal (solo logging): estadísticas por bloque del array
        # exacto que se pasa a wake.process(), para comparar el "Hey ZIX" que
        # dispara vs el que no dispara dentro de la misma corrida.
        _dbg_n = 0
        _dbg_t = time.monotonic()
        _dbg_peak = 0.0
        for block in audio.iter_input_blocks():
            arr = np.asarray(block)
            detected = False
            if arr.size:
                arr_rms = float(
                    np.sqrt(np.mean(np.square(arr.astype(np.float64))))
                )
                arr_peak = float(np.max(np.abs(arr)))
                _dbg_peak = max(
                    _dbg_peak, float(np.mean(np.abs(arr)))
                )
                if not config.voice_continuous_mode:
                    detected = wake.process(block)
                logger.debug(
                    "wake_diag timestamp_unix=%.6f input_device=%s "
                    "input_sample_rate=%s input_channels=%s input_dtype=%s "
                    "input_frame_samples=%s input_overflow=%s "
                    "output_sample_rate=%d frame_samples=%d dtype=%s "
                    "rms=%.8f peak=%.8f min=%.8f max=%.8f score=%.8f",
                    time.time(),
                    audio.active_input_device,
                    audio.active_input_samplerate,
                    audio.active_input_channels,
                    audio.active_input_dtype,
                    audio.active_input_frame_size,
                    audio.last_input_overflow,
                    config.voice_sample_rate,
                    arr.size,
                    arr.dtype,
                    arr_rms,
                    arr_peak,
                    float(arr.min()),
                    float(arr.max()),
                    wake.last_score
                    if not config.voice_continuous_mode
                    and wake.last_score is not None
                    else -1.0,
                )
            _dbg_n += 1
            if time.monotonic() - _dbg_t >= 1.0:
                logger.info(
                    "audio 1s: bloques=%d pico_mean_abs=%.5f estado=%s",
                    _dbg_n,
                    _dbg_peak,
                    conversation.state.name,
                )
                _dbg_n, _dbg_t, _dbg_peak = 0, time.monotonic(), 0.0
            if detected:
                print("¡Te escucho! Di tu orden...")
                conversation.on_wake_word()
            conversation.feed_audio(block)
            conversation.tick()
    except KeyboardInterrupt:
        print("\nAdiós.")
    return 0


if __name__ == "__main__":
    sys.exit(main())