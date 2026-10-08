"""Herramienta calculator: evalúa expresiones aritméticas de forma segura.

NO usa eval() crudo: parsea el AST y solo permite nodos aritméticos y un
conjunto fijo de funciones, por lo que es imposible inyectar código.
"""
from __future__ import annotations

import ast
import operator

from ..core.tool import Tool

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_CONSTANTS = {
    "pi": 3.141592653589793,
    "e": 2.718281828459045,
}

_FUNCTIONS = {
    "round": round,
    "abs": abs,
    "min": min,
    "max": max,
}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Solo se permiten números.")
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Name) and node.id in _CONSTANTS:
        return _CONSTANTS[node.id]
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FUNCTIONS
    ):
        args = [_eval_node(arg) for arg in node.args]
        return _FUNCTIONS[node.func.id](*args)
    raise ValueError(f"Operación no permitida: {type(node).__name__}")


def safe_eval(expression: str) -> float:
    """Evalúa una expresión aritmética permitida (+, -, *, /, //, %, **)."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Expresión inválida: {exc}") from exc
    return _eval_node(tree)


def _format_result(value: float) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def calculator(expression: str) -> str:
    """Evalúa una expresión aritmética básica y devuelve el resultado."""
    return _format_result(safe_eval(expression))


calculator_tool = Tool(
    name="calculator",
    description=(
        "Evalúa una expresión aritmética básica (+, -, *, /, //, %, **, "
        "paréntesis, constantes pi y e, funciones round/abs/min/max). "
        "Devuelve el resultado numérico. Úsala para cualquier cálculo."
    ),
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": (
                    "La expresión aritmética a evaluar, p. ej. '25 * 48' o "
                    "'(2 + 3) * 4'."
                ),
            },
        },
        "required": ["expression"],
    },
    func=calculator,
    metadata={"category": "math"},
)