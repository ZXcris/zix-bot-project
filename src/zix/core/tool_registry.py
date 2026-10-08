"""Registro central de herramientas de ZIX.

Las herramientas propias y las futuras herramientas MCP se registrarán aquí
de forma uniforme (véase ToolAdapter/MCP en fases posteriores).
"""
from __future__ import annotations

from typing import Optional

from .ai_provider import ToolSpec
from .tool import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(
                f"Ya existe una herramienta registrada con el nombre '{tool.name}'"
            )
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def specs(self) -> list[ToolSpec]:
        return [tool.spec() for tool in self._tools.values()]