"""Tests de OllamaProvider con red simulada (sin levantar Ollama).

Ollama corre en este equipo, pero los tests NO deben depender de que
estea arrancado ni de que el modelo este descargado: si lo hicieran, la
suite fallaria en un PC sin Ollama y no diria nada del codigo.

Lo que se comprueba es el contrato: como se pide, como se traduce la
respuesta, y como se traducen los errores.

El modelo por defecto se elige aqui: `openbmb/minicpm-v4.6` es el UNICO de
los tres modelos locales que emite tool calls de verdad (verificado el
2026-10-20 contra el endpoint real). El agente de ZIX vive de las tools,
asi que con `phi4-mini` o `qwen2.5-coder:1.5b` ZIX contesta pero no
actua.
"""
from __future__ import annotations

import json
import urllib.error
from unittest.mock import patch

import pytest

from zix.config import Config
from zix.core.ai_provider import (
    AgentResponse,
    AIProviderError,
    ChatMessage,
    ProviderInvalidResponseError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ToolSpec,
)
from zix.core.ollama_provider import OllamaProvider
from zix.core.provider_factory import build_provider


def _config(**overrides) -> Config:
    base = dict(
        ai_provider="ollama",
        ollama_base_url="http://127.0.0.1:11434/v1",
        ollama_model="openbmb/minicpm-v4.6:latest",
        ollama_timeout_seconds=5.0,
    )
    base.update(overrides)
    return Config(**base)


def _messages() -> list[ChatMessage]:
    return [ChatMessage(role="user", content="Hola")]


def _tools() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="calculator",
            description="Calcula una expresion",
            parameters={"type": "object", "properties": {}},
        )
    ]


class _FakeResponse:
    """Context manager que imita http.client.HTTPResponse para urlopen.

    Acepta `read(n)` y `read1(n)` porque el proveedor los usa para leer en
    trozos y poder comprobar el plazo total entre ellos.
    """

    def __init__(self, payload: dict) -> None:
        self._payload = json.dumps(payload).encode("utf-8")
        self._pos = 0

    def __enter__(self):
        return self

    def __exit__(self, *args) -> bool:
        return False

    def read(self, n=-1) -> bytes:
        if n is None or n < 0:
            n = len(self._payload) - self._pos
        trozo = self._payload[self._pos:self._pos + n]
        self._pos += len(trozo)
        return trozo

    def read1(self, n=-1) -> bytes:
        # Como un stream de verdad: devuelve lo que hay y, agotado, vacio.
        return self.read(n)


def _chat_payload(content=None, tool_calls=None) -> dict:
    message: dict = {}
    if content is not None:
        message["content"] = content
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message}]}


def _captured_request() -> dict:
    """Lo que se mando al servidor en la ultima llamada."""
    return _captured["request"]


_captured: dict = {}


def _fake_urlopen(payload: dict):
    """urlopen falso que guarda la peticion para poder inspeccionarla."""

    def _urlopen(request, timeout=None):
        _captured["request"] = request
        _captured["payload"] = json.loads(request.data.decode("utf-8"))
        _captured["timeout"] = timeout
        return _FakeResponse(payload)

    return _urlopen


# --- la fabrica lo conoce ----------------------------------------------

def test_la_fabrica_construye_el_proveedor_ollama():
    provider = build_provider(_config())
    assert isinstance(provider, OllamaProvider)


def test_ollama_no_necesita_ninguna_clave():
    """A diferencia de Groq y xKiro, aqui no hay nada que pegar en .env."""
    provider = OllamaProvider(_config())
    assert provider.model == "openbmb/minicpm-v4.6:latest"


def test_un_proveedor_desconocido_sigue_siendo_error():
    with pytest.raises(ValueError, match="no válido"):
        build_provider(_config(ai_provider="inventado"))


# --- la peticion -------------------------------------------------------

def test_pide_al_endpoint_openai_compatible():
    provider = OllamaProvider(_config())
    with patch(
        "zix.core.ollama_provider.urllib.request.urlopen",
        side_effect=_fake_urlopen(_chat_payload(content="Hola")),
    ):
        provider.complete(_messages(), _tools())

    request = _captured_request()
    assert request.full_url == "http://127.0.0.1:11434/v1/chat/completions"
    assert request.method == "POST"
    assert request.get_header("Content-type") == "application/json"


def test_manda_el_modelo_configurado_y_el_mensaje():
    provider = OllamaProvider(_config(ollama_model="phi4-mini:latest"))
    with patch(
        "zix.core.ollama_provider.urllib.request.urlopen",
        side_effect=_fake_urlopen(_chat_payload(content="Hola")),
    ):
        provider.complete(_messages(), _tools())

    payload = _captured["payload"]
    assert payload["model"] == "phi4-mini:latest"
    assert payload["messages"] == [{"role": "user", "content": "Hola"}]
    assert payload["stream"] is False


def test_manda_el_mensaje_de_sistema_sin_tocarlo():
    """El agente mete un prompt de sistema en espanol; Ollama debe recibirlo.

    Si este mensaje se perdiera, el modelo local responderia en ingles
    (que es lo que hace sin el), porque su prompt de sistema es el unico
    que le dice que hable espanol.
    """
    provider = OllamaProvider(_config())
    mensajes = [
        ChatMessage(role="system", content="Eres ZIX. Responde en espanol."),
        ChatMessage(role="user", content="Hola"),
    ]
    with patch(
        "zix.core.ollama_provider.urllib.request.urlopen",
        side_effect=_fake_urlopen(_chat_payload(content="Hola")),
    ):
        provider.complete(mensajes, _tools())

    payload = _captured["payload"]
    assert payload["messages"][0] == {
        "role": "system",
        "content": "Eres ZIX. Responde en espanol.",
    }


def test_manda_las_tools_en_formato_openai():
    provider = OllamaProvider(_config())
    with patch(
        "zix.core.ollama_provider.urllib.request.urlopen",
        side_effect=_fake_urlopen(_chat_payload(content="Hola")),
    ):
        provider.complete(_messages(), _tools())

    tools = _captured["payload"]["tools"]
    assert len(tools) == 1
    assert tools[0]["type"] == "function"
    assert tools[0]["function"]["name"] == "calculator"


def test_usa_el_timeout_configurado():
    provider = OllamaProvider(_config(ollama_timeout_seconds=7.0))
    with patch(
        "zix.core.ollama_provider.urllib.request.urlopen",
        side_effect=_fake_urlopen(_chat_payload(content="Hola")),
    ):
        provider.complete(_messages(), _tools())
    assert _captured["timeout"] == 7.0


# --- las respuestas ----------------------------------------------------

def test_respuesta_de_texto():
    provider = OllamaProvider(_config())
    with patch(
        "zix.core.ollama_provider.urllib.request.urlopen",
        return_value=_FakeResponse(_chat_payload(content="Hola, soy ZIX.")),
    ):
        response = provider.complete(_messages(), _tools())
    assert isinstance(response, AgentResponse)
    assert response.content == "Hola, soy ZIX."
    assert response.tool_calls is None


def test_tool_call_con_argumentos_como_objeto():
    """Ollama devuelve los argumentos ya parseados, no como cadena."""
    provider = OllamaProvider(_config())
    payload = _chat_payload(
        tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "calculator", "arguments": {"expression": "25 * 48"}},
            }
        ]
    )
    with patch(
        "zix.core.ollama_provider.urllib.request.urlopen",
        return_value=_FakeResponse(payload),
    ):
        response = provider.complete(_messages(), _tools())
    assert response.tool_calls is not None
    call = response.tool_calls[0]
    assert (call.id, call.name) == ("call_1", "calculator")
    assert call.arguments == {"expression": "25 * 48"}


def test_tool_call_con_argumentos_como_cadena_tambien_se_acepta():
    """Por compatibilidad con el formato de OpenAI."""
    provider = OllamaProvider(_config())
    payload = _chat_payload(
        tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "calculator", "arguments": '{"expression": "25 * 48"}'},
            }
        ]
    )
    with patch(
        "zix.core.ollama_provider.urllib.request.urlopen",
        return_value=_FakeResponse(payload),
    ):
        response = provider.complete(_messages(), _tools())
    assert response.tool_calls[0].arguments == {"expression": "25 * 48"}


def test_argumentos_que_no_son_objeto_da_error():
    provider = OllamaProvider(_config())
    payload = _chat_payload(
        tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "calculator", "arguments": [1, 2, 3]},
            }
        ]
    )
    with patch(
        "zix.core.ollama_provider.urllib.request.urlopen",
        return_value=_FakeResponse(payload),
    ):
        with pytest.raises(ProviderInvalidResponseError):
            provider.complete(_messages(), _tools())


def test_respuesta_que_no_es_json_da_error():
    provider = OllamaProvider(_config())
    with patch(
        "zix.core.ollama_provider.urllib.request.urlopen",
        return_value=_FakeResponse({"no_soy": "un chat completion"}),
    ):
        with pytest.raises(ProviderInvalidResponseError):
            provider.complete(_messages(), _tools())


# --- los errores -------------------------------------------------------

def test_ollama_apagado_da_error_que_dice_como_arrancarlo():
    """El caso mas probable: el usuario no ha lanzado 'ollama serve'."""
    provider = OllamaProvider(_config())
    with patch(
        "zix.core.ollama_provider.urllib.request.urlopen",
        side_effect=urllib.error.URLError("Connection refused"),
    ):
        with pytest.raises(ProviderTimeoutError) as exc:
            provider.complete(_messages(), _tools())
    assert "ollama serve" in str(exc.value).lower()


def test_timeout_se_traduce_a_error_de_tiempo():
    provider = OllamaProvider(_config())
    with patch(
        "zix.core.ollama_provider.urllib.request.urlopen",
        side_effect=TimeoutError("timed out"),
    ):
        with pytest.raises(ProviderTimeoutError):
            provider.complete(_messages(), _tools())


def test_modelo_inexistente_dice_cual_falta():
    provider = OllamaProvider(_config(ollama_model="no-existe"))
    error = urllib.error.HTTPError(
        url="http://127.0.0.1:11434/v1/chat/completions",
        code=404,
        msg="Not Found",
        hdrs=None,
        fp=None,
    )
    with patch(
        "zix.core.ollama_provider.urllib.request.urlopen", side_effect=error
    ):
        with pytest.raises(AIProviderError) as exc:
            provider.complete(_messages(), _tools())
    assert "no-existe" in str(exc.value)
    assert "ollama list" in str(exc.value)


def test_429_se_traduce_a_rate_limit():
    provider = OllamaProvider(_config())
    error = urllib.error.HTTPError(
        url="http://127.0.0.1:11434/v1/chat/completions",
        code=429,
        msg="Too Many Requests",
        hdrs=None,
        fp=None,
    )
    with patch(
        "zix.core.ollama_provider.urllib.request.urlopen", side_effect=error
    ):
        with pytest.raises(ProviderRateLimitError):
            provider.complete(_messages(), _tools())


def test_otro_http_no_se_esconde():
    provider = OllamaProvider(_config())
    error = urllib.error.HTTPError(
        url="http://127.0.0.1:11434/v1/chat/completions",
        code=500,
        msg="Server Error",
        hdrs=None,
        fp=None,
    )
    with patch(
        "zix.core.ollama_provider.urllib.request.urlopen", side_effect=error
    ):
        with pytest.raises(AIProviderError) as exc:
            provider.complete(_messages(), _tools())
    assert "500" in str(exc.value)


# --- V-1 / V-2: el destino de la conexion se valida ---------------------
# Sin esto, OLLAMA_BASE_URL puede apuntar a cualquier sitio (SSRF) y
# urllib acepta esquemas como file:// que leen ficheros locales.

def test_esquema_no_http_se_rechaza():
    """file://, data:, ftp: no son gateways de IA: se rechazan."""
    for esquema in ("file", "data", "ftp", "gopher"):
        with pytest.raises(ValueError) as exc:
            OllamaProvider(_config(ollama_base_url=f"{esquema}://ejemplo/v1"))
        assert "http" in str(exc.value).lower()


def test_host_fuera_de_este_equipo_se_rechaza_sin_permiso():
    """Por defecto, el motor local no puede enviar la conversacion fuera."""
    with pytest.raises(ValueError) as exc:
        OllamaProvider(_config(ollama_base_url="http://servidor-remoto:11434/v1"))
    assert "OLLAMA_ALLOW_REMOTE" in str(exc.value)


def test_host_remoto_se_puede_permitir_explicitamente():
    provider = OllamaProvider(
        _config(ollama_base_url="http://servidor-remoto:11434/v1",
                ollama_allow_remote=True)
    )
    assert provider is not None


def test_loopback_en_forma_ipv6_tambien_valida():
    provider = OllamaProvider(_config(ollama_base_url="http://[::1]:11434/v1"))
    assert provider is not None


# --- V-9: el timeout tiene que ser un PLAZO TOTAL ------------------------
# El timeout de urlopen es por operacion de socket, no un plazo total: un
# servidor que manda un byte cada poco mantiene la conexion viva para
# siempre. Y como el pipeline de voz es sincrono, ZIX se queda sin microfono.

def test_un_servidor_lento_no_puede_colgar_zix_mas_alla_del_plazo():
    """El timeout de urlopen es por operacion de socket, NO un plazo total.

    Medido contra el proveedor real en este equipo (2026-10-20): con un
    servidor que manda un byte cada 0,2 s, urlopen(timeout=2) NO corto a los
    2 s; la llamada duro lo que duro el servidor (8,0 s con un servidor de
    8 s; 20,1 s con uno de 20 s). Con el timeout por defecto de 300 s y las
    10 iteraciones del agente, ZIX puede quedarse 50 minutos sin microfono,
    porque el pipeline de voz es sincrono.

    Aqui el servidor lento es un doble: no hay sockets ni hilos, asi que el
    test no depende de como se comporten las temporizaciones de la red.
    """
    import time

    class _RespuestaLenta:
        """Se comporta como un servidor que dribla: cada lectura tarda."""

        def __init__(self) -> None:
            self._lecturas = 0

        def __enter__(self):
            return self

        def __exit__(self, *args) -> bool:
            return False

        def read(self, n=-1):
            return self.read1(n)

        def read1(self, n=-1):
            self._lecturas += 1
            if self._lecturas > 40:  # 40 x 0,2 s = 8 s de servidor lento
                raise OSError("fin del servidor lento")
            time.sleep(0.2)
            return b"x" * 16

    provider = OllamaProvider(_config(ollama_timeout_seconds=2.0))
    inicio = time.monotonic()
    with pytest.raises(ProviderTimeoutError):
        provider.complete(_messages(), _tools())
    duracion = time.monotonic() - inicio
    assert duracion < 6, (
        f"tardo {duracion:.1f} s: el timeout no se esta aplicando como plazo total"
    )


# --- V-4: la respuesta no puede ser infinita ------------------------------

def test_una_respuesta_enorme_se_corta():
    class _RespuestaEnorme:
        def __init__(self) -> None:
            self._restantes = 50 * 1024 * 1024

        def __enter__(self):
            return self

        def __exit__(self, *args) -> bool:
            return False

        def read(self, *args):
            if self._restantes <= 0:
                return b""
            self._restantes -= 65536
            return b"x" * 65536

        def read1(self, n=-1):
            return self.read(n)

    provider = OllamaProvider(_config())
    with patch(
        "zix.core.ollama_provider.urllib.request.urlopen",
        return_value=_RespuestaEnorme(),
    ):
        with pytest.raises(ProviderInvalidResponseError) as exc:
            provider.complete(_messages(), _tools())
    assert "grande" in str(exc.value).lower() or "tamaño" in str(exc.value).lower()


# --- V-5: numero de tool calls por respuesta -----------------------------

def test_demasiadas_tool_calls_se_rechazan():
    llamadas = [
        {
            "id": f"call_{i}",
            "type": "function",
            "function": {"name": "echo", "arguments": {"text": "x"}},
        }
        for i in range(200)
    ]
    provider = OllamaProvider(_config())
    with patch(
        "zix.core.ollama_provider.urllib.request.urlopen",
        return_value=_FakeResponse(_chat_payload(tool_calls=llamadas)),
    ):
        with pytest.raises(ProviderInvalidResponseError):
            provider.complete(_messages(), _tools())


# --- V-3: el nombre del modelo se valida ----------------------------------

def test_un_nombre_de_modelo_con_travesia_se_rechaza():
    for malo in ("../../etc/passwd", "..\\..\\Windows\\win.ini", "a b"):
        with pytest.raises(ValueError):
            OllamaProvider(_config(ollama_model=malo))


# --- V-8: el contenido crudo del servidor no se le al usuario -------------

def test_el_error_no_repite_el_contenido_crudo_del_servidor():
    """Lo que devuelve un endpoint hostil puede acabar LEIDO por el TTS."""
    secreto = "CONTRASENA_SECRETA_DEL_SERVIDOR"
    provider = OllamaProvider(_config())
    with patch(
        "zix.core.ollama_provider.urllib.request.urlopen",
        return_value=_FakeResponse({"no_soy": "chat", "detalle": secreto}),
    ):
        with pytest.raises(ProviderInvalidResponseError) as exc:
            provider.complete(_messages(), _tools())
    assert secreto not in str(exc.value)
