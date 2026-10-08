"""Ejecutor de herramientas: valida argumentos, ejecuta y captura resultados/errores.

Los errores de ejecución NO se lanzan: se devuelven dentro de ToolResult para
que el Agent los entregue de vuelta al modelo, que decide cómo continuar.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from .tool import Tool
from .tool_registry import ToolRegistry


@dataclass
class ToolResult:
    ok: bool
    value: Any = None
    error: Optional[str] = None

    def to_content(self) -> str:
        """Convierte el resultado en texto para el mensaje 'tool' del modelo."""
        if not self.ok:
            return f"ERROR: {self.error}"
        if isinstance(self.value, str):
            return self.value
        try:
            return json.dumps(self.value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(self.value)


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self._registry.get(name)
        if tool is None:
            return ToolResult(ok=False, error=f"Herramienta desconocida: '{name}'")

        missing = self._missing_required(tool, arguments)
        if missing:
            return ToolResult(
                ok=False,
                error=f"Faltan parámetros requeridos: {', '.join(missing)}",
            )

        try:
            value = tool.func(**arguments)
            return ToolResult(ok=True, value=value)
        except Exception as exc:  # noqa: BLE001 - el error se devuelve al agente
            return ToolResult(ok=False, error=f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _missing_required(tool: Tool, arguments: dict[str, Any]) -> list[str]:
        required = tool.parameters.get("required", [])
        return [key for key in required if key not in arguments]