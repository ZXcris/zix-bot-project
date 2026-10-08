"""Herramienta echo: devuelve el texto recibido (utilidad de prueba)."""
from __future__ import annotations

from ..core.tool import Tool


def echo(text: str) -> str:
    """Devuelve el texto tal cual."""
    return text


echo_tool = Tool(
    name="echo",
    description="Devuelve el mismo texto que recibe. Útil para probar el agente.",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "El texto a repetir."},
        },
        "required": ["text"],
    },
    func=echo,
    metadata={"category": "test"},
)