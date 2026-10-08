"""Registro de las herramientas integradas de ZIX (v0.1: solo seguras)."""
from __future__ import annotations

from ..core.tool_registry import ToolRegistry
from .calculator import calculator_tool
from .echo import echo_tool
from .open_app import open_app_tool
from .time_tool import get_current_time_tool


def register_builtin_tools(registry: ToolRegistry) -> None:
    """Registra todas las herramientas de prueba de la v0.1 en el registry."""
    for tool in (
        get_current_time_tool,
        calculator_tool,
        echo_tool,
        open_app_tool,
    ):
        registry.register(tool)