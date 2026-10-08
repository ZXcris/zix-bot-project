"""El agente de ZIX: bucle de razonamiento y ejecución de herramientas.

El Agent es agnóstico de I/O: recibe texto y devuelve texto. En la v0.1 la
CLI lo alimenta; en el futuro lo hará el pipeline de voz
(Microfono -> STT -> Agent -> TTS -> Altavoz). El Agent NO imprime ni
muestra nada: devuelve la respuesta final como texto.
"""
from __future__ import annotations

from typing import Optional

from ..config import Config
from .ai_provider import AIProvider, AIProviderError, ChatMessage
from .tool_executor import ToolExecutor

DEFAULT_SYSTEM_PROMPT = (
    "Eres ZIX, un asistente personal de IA para Windows. "
    "Responde de forma breve, natural y directa, en español, como en una "
    "conversación hablada. "
    "Si necesitas realizar una acción en el sistema, usa las herramientas "
    "disponibles. "
    "Cuando una herramienta falle, intenta una alternativa si existe; "
    "si no puedes resolverlo, explícalo al usuario. "
    "No inventes resultados: confía solo en lo que devuelven las herramientas."
)


class Agent:
    def __init__(
        self,
        provider: AIProvider,
        executor: ToolExecutor,
        config: Config,
        system_prompt: Optional[str] = None,
    ) -> None:
        self._provider = provider
        self._executor = executor
        self._config = config
        self._system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._messages: list[ChatMessage] = []

    def reset_session(self) -> None:
        """Borra el historial de conversación actual."""
        self._messages = []

    def run(self, user_input: str) -> str:
        """Procesa una entrada de texto (futuro: procedente de STT) y
        devuelve la respuesta final (futuro: para TTS)."""
        if not self._messages:
            self._messages.append(ChatMessage(role="system", content=self._system_prompt))
        self._messages.append(ChatMessage(role="user", content=user_input))

        tools = self._executor.registry.specs()

        for _ in range(self._config.max_agent_iterations):
            try:
                response = self._provider.complete(self._messages, tools)
            except AIProviderError as exc:
                return f"No pude completar tu petición ({type(exc).__name__}): {exc}"

            if not response.tool_calls:
                final = response.content
                if final is None or not final.strip():
                    final = "No tengo una respuesta para eso."
                self._messages.append(ChatMessage(role="assistant", content=final))
                return final

            self._messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )
            for call in response.tool_calls:
                result = self._executor.execute(call.name, call.arguments)
                self._messages.append(
                    ChatMessage(
                        role="tool",
                        tool_call_id=call.id,
                        content=result.to_content(),
                    )
                )

        return (
            "He alcanzado el límite de intentos para completar tu petición. "
            "Intenta reformularla o dividirla en pasos más pequeños."
        )