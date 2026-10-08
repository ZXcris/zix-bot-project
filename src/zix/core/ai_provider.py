"""Interfaces y tipos neutros del proveedor de IA.

El núcleo de ZIX (Agent, ToolRegistry, ToolExecutor) NUNCA importa un SDK
concreto (p. ej. `groq`). Solo conoce estos tipos y esta interfaz, de modo
que un proveedor pueda sustituirse (Groq, Ollama, OpenRouter...) sin tocar
el resto del sistema.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


class AIProviderError(Exception):
    """Error base del proveedor de IA."""


class ProviderRateLimitError(AIProviderError):
    """Se alcanzó el límite de peticiones/tokens del proveedor."""


class ProviderTimeoutError(AIProviderError):
    """El proveedor tardó demasiado en responder."""


class ProviderInvalidResponseError(AIProviderError):
    """El proveedor devolvió una respuesta que no se pudo interpretar."""


@dataclass
class ToolCall:
    """Llamada a herramienta decidida por el modelo."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatMessage:
    """Mensaje neutro del historial de conversación."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None
    tool_call_id: Optional[str] = None


@dataclass
class ToolSpec:
    """Descripción de una herramienta tal y como la ve el modelo."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResponse:
    """Respuesta del proveedor: contenido de texto y/o llamadas a herramientas."""

    content: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None


class AIProvider(ABC):
    """Contrato que debe cumplir cualquier proveedor de IA (Groq, Ollama, ...)."""

    @abstractmethod
    def complete(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
    ) -> AgentResponse:
        """Envía el historial y las herramientas disponibles al modelo.

        Devuelve contenido de texto y/o llamadas a herramientas.
        Lanza AIProviderError (o subclases) si el proveedor falla; el error
        nunca se oculta y puede ser manejado por el Agent.
        """
        raise NotImplementedError