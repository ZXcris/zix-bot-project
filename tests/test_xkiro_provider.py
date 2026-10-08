"""Tests de XkiroProvider con red simulada (sin cuota ni API key real)."""
from __future__ import annotations

import io
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
from zix.core.provider_factory import build_provider
from zix.core.xkiro_provider import XkiroProvider


def _config(**overrides) -> Config:
    base = dict(
        groq_api_key="",
        ai_provider="xkiro",
        xkiro_api_key="fake-xkiro-key",
        xkiro_model="mistralai/mistral-small-2603",
        xkiro_fallback_model="minimax/minimax-m3:free",
        xkiro_base_url="https://api.xkiro.com/v1",
        xkiro_timeout_seconds=5.0,
    )
    base.update(overrides)
    return Config(**base)


def _messages() -> list[ChatMessage]:
    return [ChatMessage(role="user", content="Hola")]


def _tools() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="echo",
            description="Repite texto",
            parameters={"type": "object", "properties": {}},
        )
    ]


class _FakeResponse:
    """Context manager que imita http.client.HTTPResponse para urlopen."""

    def __init__(self, payload: dict) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload


def _chat_payload(content=None, tool_calls=None) -> dict:
    message: dict = {}
    if content is not None:
        message["content"] = content
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message}]}


def test_missing_key_raises():
    with pytest.raises(ValueError, match="XKIRO_API_KEY"):
        XkiroProvider(_config(xkiro_api_key=""))


def test_text_response():
    provider = XkiroProvider(_config())
    with patch(
        "zix.core.xkiro_provider.urllib.request.urlopen",
        return_value=_FakeResponse(_chat_payload(content="Hola, soy ZIX.")),
    ):
        response = provider.complete(_messages(), _tools())
    assert isinstance(response, AgentResponse)
    assert response.content == "Hola, soy ZIX."
    assert response.tool_calls is None


def test_tool_call_parsed():
    provider = XkiroProvider(_config())
    payload = _chat_payload(
        tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "calculator",
                    "arguments": '{"expression": "25 * 48"}',
                },
            }
        ]
    )
    with patch(
        "zix.core.xkiro_provider.urllib.request.urlopen",
        return_value=_FakeResponse(payload),
    ):
        response = provider.complete(_messages(), _tools())
    assert response.tool_calls is not None
    assert len(response.tool_calls) == 1
    call = response.tool_calls[0]
    assert (call.id, call.name) == ("call_1", "calculator")
    assert call.arguments == {"expression": "25 * 48"}


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.xkiro.com/v1/chat/completions",
        code,
        "error",
        {},
        io.BytesIO(b'{"error": "boom"}'),
    )


def test_rate_limit_uses_fallback_model():
    provider = XkiroProvider(_config())
    seen_models: list[str] = []

    def fake_urlopen(request, timeout=None):
        body = json.loads(request.data.decode("utf-8"))
        seen_models.append(body["model"])
        if len(seen_models) == 1:
            raise _http_error(429)
        return _FakeResponse(_chat_payload(content="OK tras fallback"))

    with patch("zix.core.xkiro_provider.urllib.request.urlopen", fake_urlopen):
        response = provider.complete(_messages(), _tools())
    assert response.content == "OK tras fallback"
    assert seen_models == [
        "mistralai/mistral-small-2603",
        "minimax/minimax-m3:free",
    ]


def test_rate_limit_without_fallback_raises():
    provider = XkiroProvider(_config(xkiro_fallback_model=""))
    with (
        patch(
            "zix.core.xkiro_provider.urllib.request.urlopen",
            side_effect=_http_error(429),
        ),
        pytest.raises(ProviderRateLimitError),
    ):
        provider.complete(_messages(), _tools())


def test_http_error_maps_to_provider_error():
    provider = XkiroProvider(_config())
    with (
        patch(
            "zix.core.xkiro_provider.urllib.request.urlopen",
            side_effect=_http_error(500),
        ),
        pytest.raises(AIProviderError),
    ):
        provider.complete(_messages(), _tools())


def test_network_error_maps_to_timeout():
    provider = XkiroProvider(_config())
    with (
        patch(
            "zix.core.xkiro_provider.urllib.request.urlopen",
            side_effect=urllib.error.URLError("red caída"),
        ),
        pytest.raises(ProviderTimeoutError),
    ):
        provider.complete(_messages(), _tools())


def test_invalid_json_maps_to_invalid_response():
    class _Raw:
        def __enter__(self):
            return self

        def __exit__(self, *args) -> bool:
            return False

        def read(self) -> bytes:
            return b"esto no es json"

    provider = XkiroProvider(_config())
    with (
        patch(
            "zix.core.xkiro_provider.urllib.request.urlopen", return_value=_Raw()
        ),
        pytest.raises(ProviderInvalidResponseError),
    ):
        provider.complete(_messages(), _tools())


def test_bad_tool_arguments_raise():
    provider = XkiroProvider(_config())
    payload = _chat_payload(
        tool_calls=[
            {
                "id": "call_x",
                "type": "function",
                "function": {"name": "echo", "arguments": "{mal json"},
            }
        ]
    )
    with (
        patch(
            "zix.core.xkiro_provider.urllib.request.urlopen",
            return_value=_FakeResponse(payload),
        ),
        pytest.raises(ProviderInvalidResponseError),
    ):
        provider.complete(_messages(), _tools())


def test_factory_selects_provider():
    from zix.core.groq_provider import GroqProvider

    assert isinstance(
        build_provider(_config(ai_provider="xkiro")), XkiroProvider
    )
    assert isinstance(
        build_provider(Config(groq_api_key="k", ai_provider="groq")), GroqProvider
    )
    with pytest.raises(ValueError, match="AI_PROVIDER"):
        build_provider(Config(groq_api_key="k", ai_provider="otro"))
