"""Herramienta get_current_time: fecha y hora actuales del sistema."""
from __future__ import annotations

from datetime import datetime

from ..core.tool import Tool


def get_current_time(format: str = "%A %d de %B de %Y, %H:%M:%S") -> str:
    """Devuelve la fecha y hora actuales del sistema en el formato indicado."""
    return datetime.now().strftime(format)


get_current_time_tool = Tool(
    name="get_current_time",
    description=(
        "Devuelve la fecha y hora actuales del sistema. "
        "Úsala cuando el usuario pregunte qué hora es o la fecha."
    ),
    parameters={
        "type": "object",
        "properties": {
            "format": {
                "type": "string",
                "description": (
                    "Formato strftime opcional. Por defecto: "
                    "'%A %d de %B de %Y, %H:%M:%S'"
                ),
            },
        },
    },
    func=get_current_time,
    metadata={"category": "system"},
)