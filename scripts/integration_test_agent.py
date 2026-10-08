"""Prueba de integración MANUAL del Agent Core con Groq real (tool calling).

NO forma parte de la suite de pytest. Ejecutar a mano:

    python scripts/integration_test_agent.py

Requiere .env con GROQ_API_KEY válida. Nunca imprime la API key.

Verifica:
1. Groq recibe correctamente las herramientas registradas.
2. Groq genera un tool_call real.
3. El Agent identifica la herramienta y ToolExecutor la ejecuta.
4. El resultado vuelve al Agent (mensaje 'tool') y Groq genera la respuesta final usándolo.
5. No se ejecuta ninguna herramienta que no haya sido solicitada por el modelo.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zix.config import Config  # noqa: E402
from zix.core.agent import Agent  # noqa: E402
from zix.core.groq_provider import GroqProvider  # noqa: E402
from zix.core.tool_executor import ToolExecutor  # noqa: E402
from zix.core.tool_registry import ToolRegistry  # noqa: E402
from zix.tools import register_builtin_tools  # noqa: E402

TASK = "Calcula 25 por 48"
EXPECTED_SUBSTRING = "1200"


class RecordingProvider:
    """Envuelve el proveedor real para registrar lo que el modelo solicita."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.calls: list[dict] = []

    def complete(self, messages, tools):
        response = self._inner.complete(messages, tools)
        self.calls.append(
            {
                "tools_received": [t.name for t in tools],
                "tool_messages": [m for m in messages if m.role == "tool"],
                "tool_calls": [
                    (tc.name, tc.arguments) for tc in (response.tool_calls or [])
                ],
            }
        )
        return response


class RecordingExecutor(ToolExecutor):
    """Registra cada herramienta que el Agent ordena ejecutar."""

    def __init__(self, registry: ToolRegistry) -> None:
        super().__init__(registry)
        self.executed: list[tuple[str, dict]] = []

    def execute(self, name: str, arguments: dict):
        self.executed.append((name, arguments))
        return super().execute(name, arguments)


def main() -> int:
    config = Config.from_env()
    if not config.groq_api_key:
        print("ERROR: GROQ_API_KEY no está definida en .env. No se puede ejecutar la prueba real.")
        return 1

    registry = ToolRegistry()
    register_builtin_tools(registry)

    executor = RecordingExecutor(registry)
    provider = RecordingProvider(GroqProvider(config))
    agent = Agent(provider=provider, executor=executor, config=config)

    print(f"Tarea: {TASK!r}")
    response = agent.run(TASK)
    print(f"Respuesta final de ZIX: {response!r}")
    print()

    # 1. Groq recibió las herramientas
    tools_received = provider.calls[0]["tools_received"]
    assert "calculator" in tools_received, f"Groq no recibió 'calculator'. Recibió: {tools_received}"
    print(f"[OK] 1. Groq recibió las herramientas: {tools_received}")

    # 2. Groq generó un tool_call real
    requested = [tc for call in provider.calls for tc in call["tool_calls"]]
    assert requested, f"Groq NO generó ningún tool_call. Respuesta: {response!r}"
    print(f"[OK] 2. Groq generó tool_calls: {requested}")

    # 3. El Agent identificó y ejecutó la herramienta
    assert executor.executed, "El Agent no ejecutó ninguna herramienta."
    print(f"[OK] 3. ToolExecutor ejecutó: {executor.executed}")

    # 5. No se ejecutó ninguna herramienta no solicitada por el modelo
    requested_names = {name for name, _ in requested}
    for name, _ in executor.executed:
        assert name in requested_names, (
            f"¡Herramienta '{name}' ejecutada sin que el modelo la solicitara!"
        )
    print("[OK] 4. Todas las herramientas ejecutadas fueron solicitadas por el modelo.")

    # 4. El resultado volvió al Agent como mensaje 'tool' para Groq
    tool_messages = [
        m
        for call in provider.calls
        for m in call["tool_messages"]
    ]
    assert tool_messages, "El resultado de la herramienta no volvió al Agent."
    print(f"[OK] 5. Resultado devuelto al Agent: {tool_messages[-1].content!r}")

    # 6. Groq generó la respuesta final usando el resultado
    assert EXPECTED_SUBSTRING in response, (
        f"La respuesta final no contiene el resultado esperado "
        f"({EXPECTED_SUBSTRING!r}): {response!r}"
    )
    print(f"[OK] 6. Respuesta final usa el resultado: {response!r}")

    print()
    print("PRUEBA DE INTEGRACIÓN SUPERADA.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - mostrar el error exacto, no ocultarlo
        print(f"\nPRUEBA DE INTEGRACIÓN FALLIDA: {type(exc).__name__}: {exc}")
        sys.exit(1)