"""CLI temporal de ZIX v0.1 — SOLO para desarrollo y testing del Agent Core.

La interfaz definitiva de ZIX será por voz:
    Microfono -> Wake Word -> STT -> Agent -> TTS -> Altavoz

Esta CLI es un adaptador temporal que alimenta al Agent con texto y muestra
su respuesta. El Agent NO depende de esta CLI.
"""
from __future__ import annotations

import sys

from zix.config import ENV_FILE, Config
from zix.core.agent import Agent
from zix.core.provider_factory import build_provider
from zix.core.tool_executor import ToolExecutor
from zix.core.tool_registry import ToolRegistry
from zix.tools import register_builtin_tools

EXIT_COMMANDS = {"salir", "exit", "quit", "adios", "adiós"}


def main() -> None:
    config = Config.from_env()
    if config.ai_provider == "xkiro" and not config.xkiro_api_key:
        print("No se encontró XKIRO_API_KEY.")
        print(
            f"Copia '{ENV_FILE.parent / '.env.example'}' a '{ENV_FILE}' "
            "y añade tu clave gratuita de https://xkiro.com (Console → API Keys)"
        )
        sys.exit(1)
    if config.ai_provider == "groq" and not config.groq_api_key:
        print("No se encontró GROQ_API_KEY.")
        print(
            f"Copia '{ENV_FILE.parent / '.env.example'}' a '{ENV_FILE}' "
            "y añade tu clave gratuita de https://console.groq.com"
        )
        sys.exit(1)

    registry = ToolRegistry()
    register_builtin_tools(registry)

    provider = build_provider(config)
    executor = ToolExecutor(registry)
    agent = Agent(provider=provider, executor=executor, config=config)

    print("ZIX v0.1 — núcleo del agente (CLI temporal para pruebas)")
    print("Herramientas disponibles:", ", ".join(tool.name for tool in registry.all()))
    print("Escribe 'salir' para terminar.")
    print("-" * 60)

    try:
        while True:
            user_input = input("Tú: ").strip()
            if not user_input:
                continue
            if user_input.lower() in EXIT_COMMANDS:
                break
            response = agent.run(user_input)
            print(f"ZIX: {response}")
    except (KeyboardInterrupt, EOFError):
        print("\nAdiós.")


if __name__ == "__main__":
    main()