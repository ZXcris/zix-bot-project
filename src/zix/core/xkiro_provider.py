"""Implementación de AIProvider usando la API de xKiro (xkiro.com).

xKiro es un gateway OpenAI-compatible (`POST {base_url}/chat/completions`
con `Authorization: Bearer <key>` e IDs `vendor/modelo`). Este es el ÚNICO
módulo de ZIX que habla con xKiro; usa solo `urllib` de la stdlib (sin SDK
externo). Todo lo demás interactúa a través de la interfaz AIProvider.

Modelos gratuitos con tool calling (verificados en el catálogo público
`GET https://api.xkiro.com/v1/models`):
    - Principal: qwen/qwen3.8-max:free
    - Respaldo:  minimax/minimax-m3:free  (se usa si el principal falla
      por rate limit; igual que GroqProvider con su fallback)

Errores HTTP/red/timeouts/respuestas inválidas se traducen a tipos neutros
(ProviderRateLimitError, etc.) y NUNCA se ocultan.
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any, Optional

from ..config import Config
from .ai_provider import (
    AIProvider,
    AIProviderError,
    AgentResponse,
    ChatMessage,
    ProviderInvalidResponseError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ToolCall,
    ToolSpec,
)

DEFAULT_BASE_URL = "https://api.xkiro.com/v1"


class XkiroProvider(AIProvider):
    def __init__(self, config: Config) -> None:
        if not config.xkiro_api_key:
            raise ValueError(
                "XKIRO_API_KEY no está definida. Crea una clave gratuita en "
                "https://xkiro.com (Console → API Keys) y añádela a .env"
            )
        self._config = config
        self._base_url = (config.xkiro_base_url or DEFAULT_BASE_URL).rstrip("/")

    def complete(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
    ) -> AgentResponse:
        payload = {
            "model": self._config.xkiro_model,
            "messages": [self._to_api_message(m) for m in messages],
        }
        api_tools = [self._to_api_tool(t) for t in tools]
        if api_tools:
            payload["tools"] = api_tools

        try:
            return self._request(payload)
        except ProviderRateLimitError:
            fallback = self._config.xkiro_fallback_model
            if fallback and fallback != self._config.xkiro_model:
                payload["model"] = fallback
                return self._request(payload)
            raise

    def _request(self, payload: dict[str, Any]) -> AgentResponse:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._config.xkiro_api_key}",
                "Content-Type": "application/json",
                # UA de navegador: el borde de xKiro (Cloudflare) bloquea
                # el UA por defecto de urllib ("Python-urllib/x.y") con 403.
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ZIX/0.3",
            },
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self._config.xkiro_timeout_seconds
            ) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise ProviderRateLimitError(
                    f"xKiro rate limit: {exc.read().decode('utf-8', 'replace')[:200]}"
                ) from exc
            raise AIProviderError(
                f"xKiro HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:200]}"
            ) from exc
        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            raise ProviderTimeoutError(f"xKiro no respondió a tiempo: {exc}") from exc

        try:
            body = json.loads(raw)
            choice = body["choices"][0]["message"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise ProviderInvalidResponseError(
                f"La respuesta de xKiro no es un chat completion válido: {raw[:200]!r}"
            ) from exc

        tool_calls: Optional[list[ToolCall]] = None
        raw_calls = choice.get("tool_calls") or []
        if raw_calls:
            tool_calls = []
            for raw_call in raw_calls:
                function = raw_call.get("function", {})
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                except json.JSONDecodeError as exc:
                    raise ProviderInvalidResponseError(
                        f"Argumentos de tool call inválidos: "
                        f"{function.get('arguments')!r}"
                    ) from exc
                if not isinstance(arguments, dict):
                    raise ProviderInvalidResponseError(
                        f"Argumentos de tool call no son objeto: {arguments!r}"
                    )
                tool_calls.append(
                    ToolCall(
                        id=str(raw_call.get("id", "")),
                        name=str(function.get("name", "")),
                        arguments=arguments,
                    )
                )

        content = choice.get("content")
        if content is not None and not isinstance(content, str):
            raise ProviderInvalidResponseError(
                f"Contenido de respuesta no es texto: {content!r}"
            )
        return AgentResponse(content=content, tool_calls=tool_calls or None)

    # ------------------------------------------------------------------
    # Conversión de tipos neutros -> formato OpenAI (el que habla xKiro)
    # ------------------------------------------------------------------
    @staticmethod
    def _to_api_message(message: ChatMessage) -> dict[str, Any]:
        api: dict[str, Any] = {"role": message.role}
        if message.content is not None:
            api["content"] = message.content
        if message.tool_calls is not None:
            api["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in message.tool_calls
            ]
        if message.tool_call_id is not None:
            api["tool_call_id"] = message.tool_call_id
        return api

    @staticmethod
    def _to_api_tool(tool: ToolSpec) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
