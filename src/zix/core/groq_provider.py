"""Implementación de AIProvider usando la API de Groq.

Este es el ÚNICO módulo de ZIX que importa el paquete `groq`. Todo lo demás
interactúa con Groq a través de la interfaz AIProvider y los tipos neutros.

Modelos (free tier, soportan tool calling, verificados vía API en 2026):
    - Principal: qwen/qwen3.6-27b
    - Respaldo:  openai/gpt-oss-20b  (se usa si el principal agota cuota)

Errores de API, rate limits, timeouts y respuestas inválidas se traducen a
tipos neutros (ProviderRateLimitError, etc.) y NUNCA se ocultan: el Agent
los recibe y decide cómo continuar.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import groq
from groq import Groq

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


class GroqProvider(AIProvider):
    def __init__(self, config: Config) -> None:
        if not config.groq_api_key:
            raise ValueError(
                "GROQ_API_KEY no está definida. Copia .env.example a .env "
                "y añade tu clave gratuita de https://console.groq.com"
            )
        self._config = config
        self._client = Groq(
            api_key=config.groq_api_key,
            timeout=config.groq_timeout_seconds,
        )

    def complete(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
    ) -> AgentResponse:
        api_messages = [self._to_api_message(m) for m in messages]
        api_tools = [self._to_api_tool(t) for t in tools] or None

        try:
            return self._request(self._config.groq_model, api_messages, api_tools)
        except ProviderRateLimitError:
            fallback = self._config.groq_fallback_model
            if fallback and fallback != self._config.groq_model:
                return self._request(fallback, api_messages, api_tools)
            raise

    def _request(
        self,
        model: str,
        api_messages: list[dict[str, Any]],
        api_tools: Optional[list[dict[str, Any]]],
    ) -> AgentResponse:
        try:
            chat = self._client.chat.completions.create(
                model=model,
                messages=api_messages,
                tools=api_tools,
            )
        except groq.RateLimitError as exc:
            raise ProviderRateLimitError(str(exc)) from exc
        except groq.APITimeoutError as exc:
            raise ProviderTimeoutError(str(exc)) from exc
        except groq.APIError as exc:
            raise AIProviderError(str(exc)) from exc

        try:
            choice = chat.choices[0].message
        except (IndexError, AttributeError) as exc:
            raise ProviderInvalidResponseError(
                "La respuesta de Groq no contiene mensajes válidos."
            ) from exc

        tool_calls: Optional[list[ToolCall]] = None
        raw_calls = getattr(choice, "tool_calls", None)
        if raw_calls:
            tool_calls = []
            for raw in raw_calls:
                try:
                    arguments = json.loads(raw.function.arguments or "{}")
                except json.JSONDecodeError as exc:
                    raise ProviderInvalidResponseError(
                        f"Argumentos de tool call inválidos: "
                        f"{raw.function.arguments!r}"
                    ) from exc
                tool_calls.append(
                    ToolCall(id=raw.id, name=raw.function.name, arguments=arguments)
                )

        return AgentResponse(content=getattr(choice, "content", None), tool_calls=tool_calls)

    # ------------------------------------------------------------------
    # Conversión de tipos neutros -> formato API de Groq (OpenAI-compatible)
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