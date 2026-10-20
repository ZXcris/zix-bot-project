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

# --- Topes de seguridad ---------------------------------------------------
#
# Sin topes, '9**9**9' produce un numero de 369 millones de digitos. No es
# una excepcion: es una CONGELACION. El hilo que la calcula monopoliza el
# GIL, y como el pipeline de voz de ZIX es sincrono, el microfono deja de
# capturarse y ZIX entero deja de responder. Medido en este equipo
# (2026-10-20): la llamada no terminaba tras 5 minutos.
#
# Son topes generosos: cualquier calculo que una persona pida de verdad
# cabe de sobra.

# Longitud maxima de la expresion.
MAX_EXPRESION_CHARS = 200
# Maximo de nodos del AST (corta '1+1+1+...' sin fin).
MAX_NODOS = 100
# Maximo de bits del resultado de una potencia. 4096 bits son unos 1233
# digitos decimales: de sobra para cualquier calculo real, y suficiente
# para que 9**9**9 (que proyectaria 1,5 miles de millones de bits) se
# rechace al instante.
MAX_BITS_RESULTADO = 4096
# Maximo de digitos decimales del resultado final.
MAX_DIGITOS_RESULTADO = 4000


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Solo se permiten números.")
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        izquierda = _eval_node(node.left)
        derecha = _eval_node(node.right)
        if isinstance(node.op, ast.Pow):
            _comprobar_potencia(izquierda, derecha)
        return _BIN_OPS[type(node.op)](izquierda, derecha)
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


def _comprobar_potencia(base: float, exponente: float) -> None:
    """Rechaza la potencia antes de calcularla.

    El tamaño del resultado es base^exponente, asi que en bits sale de
    multiplicar el exponente por los bits de la base. Se comprueba esa
    proyeccion ANTES de calcular, que es lo que evita la congelacion.
    """
    if not (isinstance(base, int) and isinstance(exponente, int)):
        # Con float, operator.pow lanza OverflowError, que el ejecutor
        # captura. No hay riesgo de congelacion.
        return
    if exponente < 0 or base in (0, 1, -1):
        return
    bits = abs(exponente) * max(base.bit_length(), 1)
    if bits > MAX_BITS_RESULTADO:
        raise ValueError(
            f"Resultado demasiado grande para calcular (unos {bits} bits). "
            f"El tope es {MAX_BITS_RESULTADO} bits."
        )


def safe_eval(expression: str) -> float:
    """Evalúa una expresión aritmética permitida (+, -, *, /, //, %, **)."""
    if len(expression) > MAX_EXPRESION_CHARS:
        raise ValueError(
            f"Expresión demasiado larga (máximo {MAX_EXPRESION_CHARS} caracteres)."
        )
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Expresión inválida: {exc}") from exc
    nodos = sum(1 for _ in ast.walk(tree))
    if nodos > MAX_NODOS:
        raise ValueError(f"Expresión demasiado compleja (más de {MAX_NODOS} nodos).")
    resultado = _eval_node(tree)
    if isinstance(resultado, int) and abs(resultado.bit_length()) > MAX_BITS_RESULTADO:
        raise ValueError("El resultado es demasiado grande.")
    if isinstance(resultado, float) and resultado in (float("inf"), float("-inf")):
        raise ValueError("El resultado es infinito.")
    digitos = len(str(int(resultado))) if isinstance(resultado, float) else 0
    if digitos > MAX_DIGITOS_RESULTADO:
        raise ValueError("El resultado tiene demasiados dígitos.")
    return resultado


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