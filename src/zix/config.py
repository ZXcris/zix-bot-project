"""Configuración global de ZIX. Carga variables desde .env (raíz del proyecto)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


def load_env() -> None:
    load_dotenv(ENV_FILE)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    """Lee un booleano de entorno. '1', 'true', 'yes' y 'on' son True."""
    crudo = os.getenv(name)
    if crudo is None:
        return default
    return crudo.strip().lower() in ("1", "true", "yes", "on", "si", "sí")


def project_path(value: str) -> Path:
    """Resuelve una ruta de configuración; las relativas apuntan a la raíz."""
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True)
class Config:
    """Configuración de ZIX. Los valores provienen de variables de entorno (.env)."""

    # --- Proveedor de IA (v0.3) ---
    # "groq" (defecto), "xkiro" (gateway OpenAI-compatible con modelos
    # gratis) o "ollama" (modelo local, sin cuota ni internet).
    ai_provider: str = "groq"
    groq_api_key: str = ""
    # --- xKiro (v0.3, gateway OpenAI-compatible https://api.xkiro.com/v1) ---
    xkiro_api_key: str = ""
    xkiro_model: str = "qwen/qwen3.8-max:free"
    xkiro_fallback_model: str = "minimax/minimax-m3:free"
    xkiro_base_url: str = "https://api.xkiro.com/v1"
    xkiro_timeout_seconds: float = 30.0
    # --- Ollama (modelo local; endpoint OpenAI-compatible en el mismo PC) ---
    ollama_base_url: str = "http://127.0.0.1:11434/v1"
    # El modelo por defecto es el UNICO de los tres locales que emite
    # tool calls de verdad (verificado el 2026-10-20):
    #   openbmb/minicpm-v4.6 -> SI
    #   phi4-mini             -> NO, ignora las tools y responde en texto
    #   qwen2.5-coder:1.5b    -> NO, devuelve el JSON como texto
    # El agente de ZIX necesita las tools para poder hacer cosas, asi que
    # cambiar este modelo sin comprobarlo deja a ZIX hablando pero sin
    # actuar.
    ollama_model: str = "openbmb/minicpm-v4.6:latest"
    # En CPU el primer token tarda: el modelo pesa 1,5 GB y hay que
    # cargarlo en RAM. 300 s deja margen para esa primera vez.
    #
    # Este es un PLAZO TOTAL, no un timeout de socket: se comprueba el
    # reloj entre lecturas. Sin eso, un servidor lento puede retener la
    # llamada todo lo que quiera (medido: 20 s con un plazo de 2 s), y
    # como el pipeline de voz es sincrono, ZIX se queda sin microfono.
    ollama_timeout_seconds: float = 300.0
    # Permitir que OLLAMA_BASE_URL apunte fuera de este equipo. Por
    # defecto NO: la conversacion (y la transcripcion de tu voz) se
    # enviarian a un host remoto en claro.
    ollama_allow_remote: bool = False
    # Tope de la respuesta del servidor. 8 MB de sobra para un chat.
    ollama_max_response_bytes: int = 8 * 1024 * 1024
    # Tope de tool calls por respuesta: el agente las ejecuta TODAS.
    ollama_max_tool_calls: int = 32
    groq_model: str = "qwen/qwen3.6-27b"
    groq_fallback_model: str = "openai/gpt-oss-20b"
    max_agent_iterations: int = 10
    # Presupuesto de tiempo de un turno completo (todas las iteraciones).
    # El plazo de Ollama es por llamada; con 10 iteraciones, 10 plazos
    # seguidos son 50 minutos de microfono apagado. Este tope acota el
    # turno entero.
    max_turn_seconds: float = 120.0
    # Tope de mensajes que el agente conserva en el historial. Sin esto,
    # el historial crece sin limite (reset_session() no se llama nunca) y
    # se reenvia entero al modelo en cada turno.
    max_history_messages: int = 40
    groq_timeout_seconds: float = 30.0
    log_level: str = "INFO"

    # --- Audio (v0.2) ---
    voice_sample_rate: int = 16000
    voice_block_size: int = 1280  # 80 ms a 16 kHz (compatible con openWakeWord)
    vad_threshold: float = 0.02  # RMS por debajo de esto se considera silencio
    vad_silence_timeout_seconds: float = 0.8  # silencio para dar por terminada la frase
    vad_min_speech_seconds: float = 0.3  # mínimo de habla para no descartar por ruido
    voice_max_utterance_seconds: float = 30.0
    voice_conversation_timeout_seconds: float = 10.0
    voice_order_min_chars: int = 2  # mínimo de caracteres de una "orden válida"
    voice_continuous_mode: bool = False
    # Dispositivo de entrada: nombre (subcadena), índice, o vacío = por defecto.
    # Con dispositivo configurado se usa el formato nativo (p. ej. WASAPI 48 kHz/2 ch)
    # y AudioManager convierte a 16 kHz/mono para openWakeWord.
    audio_input_device: str = ""
    audio_input_samplerate: int = 0  # 0 = nativo del dispositivo
    audio_input_channels: int = 0  # 0 = máximo del dispositivo

    # --- Wake word (v0.2) ---
    wake_word_model: str = "hey_jarvis"
    wake_word_threshold: float = 0.5
    wake_models_dir: str = "models/wakeword"  # futuros modelos propios (zix.onnx)
    # Supresión de ruido Speex de openWakeWord (solo con el paquete speexdsp-ns,
    # que hoy solo existe para Linux; en Windows se ignora con aviso).
    wake_word_speex_ns: bool = False

    # --- STT (v0.2) ---
    stt_model: str = "whisper-large-v3-turbo"
    stt_language: str = "es"
    # Proveedor de STT: 'groq' (nube), 'local' (faster-whisper en este equipo)
    # o 'auto' (local si esta disponible, si no nube).
    stt_provider: str = "groq"
    # Interruptor de privacidad. Con False NO se envia audio a ningun servidor:
    # si el proveedor activo es la nube, el pipeline se niega a transcribir y lo
    # dice. Es el freno de emergencia ante un falso positivo de la palabra de
    # activacion.
    stt_allow_cloud: bool = True
    # Fraccion minima de tramas que Silero debe marcar como habla antes de
    # enviar audio. Filtra silencio y ruido en LOCAL, sin red: reduce el audio
    # que sale, aunque no lo elimina (no puede juzgar el contenido).
    stt_min_speech_ratio: float = 0.15
    # Tope de duracion de lo que se transcribe, para acotar el peor caso de una
    # activacion falsa.
    stt_max_seconds: float = 15.0
    # Si Silero no esta disponible, el freno normalmente CIERRA (no se sube
    # nada). Poner esto a True devuelve el comportamiento antiguo: subir sin
    # filtrar. Ojo: con esto, el filtro deja de existir en silencio, que es
    # justo lo que se intento evitar. Deberia hacer falta solo si has
    # comprobado que el audio que manda ZIX es tuyo.
    stt_allow_unfiltered: bool = False

    # --- TTS (v0.2) ---
    piper_voice: str = "es_MX-claude-high"
    piper_models_dir: str = "models/piper"
    # Datos de espeak-ng en ruta ASCII (espeak-ng del wheel de piper no lee
    # rutas con caracteres no-ASCII). Por defecto: %LOCALAPPDATA%\zix\espeak-ng-data
    piper_espeak_data_dir: str = ""

    # --- Ejecución de voz (v0.2) ---
    voice_runtime_dir: str = "runtime"  # grabaciones temporales de prueba

    @classmethod
    def from_env(cls) -> "Config":
        load_env()
        return cls(
            ai_provider=os.getenv("AI_PROVIDER", "groq").strip(),
            groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
            xkiro_api_key=os.getenv("XKIRO_API_KEY", "").strip(),
            xkiro_model=os.getenv(
                "XKIRO_MODEL", "qwen/qwen3.8-max:free"
            ).strip(),
            xkiro_fallback_model=os.getenv(
                "XKIRO_FALLBACK_MODEL", "minimax/minimax-m3:free"
            ).strip(),
            xkiro_base_url=os.getenv(
                "XKIRO_BASE_URL", "https://api.xkiro.com/v1"
            ).strip(),
            xkiro_timeout_seconds=_float_env("XKIRO_TIMEOUT_SECONDS", 30.0),
            ollama_base_url=os.getenv(
                "OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"
            ).strip(),
            ollama_model=os.getenv(
                "OLLAMA_MODEL", "openbmb/minicpm-v4.6:latest"
            ).strip(),
            ollama_timeout_seconds=_float_env("OLLAMA_TIMEOUT_SECONDS", 300.0),
            ollama_allow_remote=_bool_env("OLLAMA_ALLOW_REMOTE", False),
            ollama_max_response_bytes=_int_env(
                "OLLAMA_MAX_RESPONSE_BYTES", 8 * 1024 * 1024),
            ollama_max_tool_calls=_int_env("OLLAMA_MAX_TOOL_CALLS", 32),
            # Tope de mensajes que el agente conserva. Sin esto, el
            # historial crece sin limite (reset_session() no se llama
            # nunca) y se reenvia entero al modelo en cada turno.
            max_history_messages=_int_env("MAX_HISTORY_MESSAGES", 40),
            groq_model=os.getenv("GROQ_MODEL", "qwen/qwen3.6-27b").strip(),
            groq_fallback_model=os.getenv(
                "GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b"
            ).strip(),
            max_agent_iterations=_int_env("MAX_AGENT_ITERATIONS", 10),
            max_turn_seconds=_float_env("MAX_TURN_SECONDS", 120.0),
            groq_timeout_seconds=_float_env("GROQ_TIMEOUT_SECONDS", 30.0),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip(),
            voice_sample_rate=_int_env("VOICE_SAMPLE_RATE", 16000),
            voice_block_size=_int_env("VOICE_BLOCK_SIZE", 1280),
            vad_threshold=_float_env("VAD_THRESHOLD", 0.02),
            vad_silence_timeout_seconds=_float_env("VAD_SILENCE_TIMEOUT_SECONDS", 0.8),
            vad_min_speech_seconds=_float_env("VAD_MIN_SPEECH_SECONDS", 0.3),
            voice_max_utterance_seconds=_float_env("VOICE_MAX_UTTERANCE_SECONDS", 30.0),
            voice_conversation_timeout_seconds=_float_env(
                "VOICE_CONVERSATION_TIMEOUT_SECONDS", 10.0
            ),
            voice_order_min_chars=_int_env("VOICE_ORDER_MIN_CHARS", 2),
            voice_continuous_mode=os.getenv("VOICE_CONTINUOUS_MODE", "0")
            .strip()
            .lower()
            in {"1", "true", "yes", "on"},
            audio_input_device=os.getenv("AUDIO_INPUT_DEVICE", "").strip(),
            audio_input_samplerate=_int_env("AUDIO_INPUT_SAMPLERATE", 0),
            audio_input_channels=_int_env("AUDIO_INPUT_CHANNELS", 0),
            wake_word_model=os.getenv("WAKE_WORD_MODEL", "hey_jarvis").strip(),
            wake_word_threshold=_float_env("WAKE_WORD_THRESHOLD", 0.5),
            wake_models_dir=os.getenv("WAKE_MODELS_DIR", "models/wakeword").strip(),
            wake_word_speex_ns=os.getenv("WAKE_WORD_SPEEX_NS", "0").strip().lower()
            in {"1", "true", "yes", "on"},
            stt_model=os.getenv("STT_MODEL", "whisper-large-v3-turbo").strip(),
            stt_language=os.getenv("STT_LANGUAGE", "es").strip(),
            stt_provider=os.getenv("STT_PROVIDER", "groq").strip().lower() or "groq",
            stt_allow_cloud=os.getenv("STT_ALLOW_CLOUD", "1").strip().lower()
            in {"1", "true", "yes", "on"},
            stt_min_speech_ratio=float(os.getenv("STT_MIN_SPEECH_RATIO", "0.15")),
            stt_max_seconds=float(os.getenv("STT_MAX_SECONDS", "15.0")),
            stt_allow_unfiltered=os.getenv("STT_ALLOW_UNFILTERED", "0")
            .strip()
            .lower()
            in {"1", "true", "yes", "on"},
            piper_voice=os.getenv("PIPER_VOICE", "es_MX-claude-high").strip(),
            piper_models_dir=os.getenv("PIPER_MODELS_DIR", "models/piper").strip(),
            piper_espeak_data_dir=os.getenv(
                "PIPER_ESPEAK_DATA_DIR",
                os.path.join(
                    os.environ.get("LOCALAPPDATA", str(Path.home())),
                    "zix",
                    "espeak-ng-data",
                ),
            ).strip(),
            voice_runtime_dir=os.getenv("VOICE_RUNTIME_DIR", "runtime").strip(),
        )