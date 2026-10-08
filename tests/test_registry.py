"""Tests del ToolRegistry de ZIX."""
from __future__ import annotations

import pytest

from zix.core.ai_provider import ToolSpec
from zix.core.tool import Tool
from zix.core.tool_registry import ToolRegistry


def _dummy(text: str) -> str:
    return text


def _make_tool(name: str = "echo") -> Tool:
    return Tool(
        name=name,
        description="Devuelve el texto recibido.",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        func=_dummy,
        metadata={"category": "test"},
    )


def test_register_and_get():
    registry = ToolRegistry()
    tool = _make_tool()
    registry.register(tool)
    assert registry.get("echo") is tool
    assert registry.get("no_existe") is None


def test_duplicate_register_raises():
    registry = ToolRegistry()
    registry.register(_make_tool())
    with pytest.raises(ValueError):
        registry.register(_make_tool())


def test_all_and_specs():
    registry = ToolRegistry()
    registry.register(_make_tool("echo"))
    registry.register(_make_tool("echo2"))
    assert len(registry.all()) == 2
    specs = registry.specs()
    assert len(specs) == 2
    assert all(isinstance(spec, ToolSpec) for spec in specs)
    assert specs[0].name == "echo"
    assert specs[0].parameters["required"] == ["text"]