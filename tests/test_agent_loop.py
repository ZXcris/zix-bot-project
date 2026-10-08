"""Tests del bucle del agente con un proveedor falso (sin red ni cuota)."""
from __future__ import annotations

from zix.config import Config
from zix.core.agent import Agent
from zix.core.ai_provider import AIProvider, AgentResponse, ChatMessage, ToolCall, ToolSpec
from zix.core.tool_executor import ToolExecutor
from zix.core.tool_registry import ToolRegistry
from zix.tools import register_builtin_tools


class ScriptedProvider(AIProvider):
    """Devuelve respuestas preprogramadas en orden. Registra cada llamada."""

    def __init__(self, script: list[AgentResponse]) -> None:
        self._script = list(script)
        self.calls: list[list[ChatMessage]] = []

    def complete(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
    ) -> AgentResponse:
        self.calls.append(list(messages))
        step = self._script.pop(0)
        return step


def _build_agent(provider: AIProvider, max_iterations: int = 10) -> Agent:
    registry = ToolRegistry()
    register_builtin_tools(registry)
    executor = ToolExecutor(registry)
    config = Config(groq_api_key="fake-key", max_agent_iterations=max_iterations)
    return Agent(provider=provider, executor=executor, config=config)


def test_agent_executes_tool_and_returns_final_response():
    provider = ScriptedProvider(
        [
            AgentResponse(
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="calculator",
                        arguments={"expression": "25 * 48"},
                    )
                ]
            ),
            AgentResponse(content="El resultado es 1200."),
        ]
    )
    agent = _build_agent(provider)

    result = agent.run("Calcula 25 por 48")

    assert result == "El resultado es 1200."
    assert len(provider.calls) == 2
    tool_messages = [m for m in provider.calls[1] if m.role == "tool"]
    assert tool_messages
    assert "1200" in tool_messages[-1].content
    assistant_tool_call = [m for m in provider.calls[1] if m.role == "assistant"]
    assert assistant_tool_call[0].tool_calls[0].name == "calculator"


def test_unknown_tool_error_goes_back_to_agent():
    provider = ScriptedProvider(
        [
            AgentResponse(
                tool_calls=[ToolCall(id="call_1", name="no_existe", arguments={})]
            ),
            AgentResponse(content="No encontré esa herramienta, lo siento."),
        ]
    )
    agent = _build_agent(provider)

    result = agent.run("haz algo raro")

    assert result == "No encontré esa herramienta, lo siento."
    tool_messages = [m for m in provider.calls[1] if m.role == "tool"]
    assert tool_messages
    assert "ERROR" in tool_messages[0].content
    assert "no_existe" in tool_messages[0].content


def test_failed_tool_execution_is_not_hidden():
    provider = ScriptedProvider(
        [
            AgentResponse(
                tool_calls=[
                    ToolCall(id="call_1", name="calculator", arguments={"expression": "1 / 0"})
                ]
            ),
            AgentResponse(content="Eso no se puede calcular: división entre cero."),
        ]
    )
    agent = _build_agent(provider)

    result = agent.run("divide 1 entre 0")

    assert result == "Eso no se puede calcular: división entre cero."
    tool_messages = [m for m in provider.calls[1] if m.role == "tool"]
    assert "ERROR" in tool_messages[0].content


def test_agent_stops_after_max_iterations():
    provider = ScriptedProvider(
        [
            AgentResponse(
                tool_calls=[ToolCall(id=f"c{i}", name="echo", arguments={"text": "x"})]
            )
            for i in range(50)
        ]
    )
    agent = _build_agent(provider, max_iterations=3)

    result = agent.run("bucle")

    assert "límite de intentos" in result
    assert len(provider.calls) == 3


def test_agent_keeps_conversation_history():
    provider = ScriptedProvider(
        [
            AgentResponse(content="Hola, ¿qué necesitas?"),
            AgentResponse(content="Claro, abriendo Chrome."),
        ]
    )
    agent = _build_agent(provider)

    agent.run("Hola Zix")
    agent.run("Abre Chrome")

    assert len(provider.calls) == 2
    assert len(provider.calls[1]) > len(provider.calls[0])
    roles = [m.role for m in provider.calls[1]]
    assert roles[-1] == "user"
    assert "assistant" in roles


def test_agent_without_tools_answers_directly():
    provider = ScriptedProvider([AgentResponse(content="Son las 3 de la tarde.")])
    agent = _build_agent(provider)

    result = agent.run("¿Qué hora es?")

    assert result == "Son las 3 de la tarde."
    assert len(provider.calls) == 1