"""Pipeline de voz de ZIX (v0.2).

Módulos:
    states: máquina de estados del asistente (IDLE, LISTENING, ...).
    vad: detección de voz por energía (RMS).
    audio: captura/reproducción de audio (sounddevice) + WAV (stdlib).
    wake_word_provider: interfaz WakeWordProvider (intercambiable).
    openwakeword_wake_word: wake word con openWakeWord (hey_jarvis hoy,
                            zix.onnx en el futuro).
    stt_provider: interfaz STTProvider (intercambiable).
    groq_stt: STT con Whisper de Groq (whisper-large-v3-turbo).
    tts_provider: interfaz TTSProvider (intercambiable).
    piper_tts: TTS local con Piper (es_MX-ald-medium).
    conversation: ConversationManager, máquina de estados + temporizador.

El núcleo del agente (zix.core) NO depende de nada de aquí; el pipeline se
conecta a él mediante el método Agent.run(text) -> texto.
"""