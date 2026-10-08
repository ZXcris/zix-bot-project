"""Definición de una herramienta registrable de ZIX."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .ai_provider import ToolSpec


@dataclass
class Tool:
    """Una herramienta ejecutable registrada en el ToolRegistry.

    Atributos:
        name: nombre único con el que el modelo la invoca.
        description: qué hace y cuándo usarla (la ve el modelo).
        parameters: esquema JSON de parámetros (JSON Schema).
        func: función de ejecución, recibe los argumentos como kwargs.
        metadata: información adicional (categoría, autor, etc.).
    """

    name: str
    description: str
    parameters: dict[str, Any]
    func: Callable[..., Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
            metadata=self.metadata,
        )