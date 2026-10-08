"""Tests de la calculadora segura de ZIX."""
from __future__ import annotations

import pytest

from zix.tools.calculator import safe_eval


def test_basic_multiplication():
    assert safe_eval("25 * 48") == 1200


def test_parentheses_and_operators():
    assert safe_eval("(2 + 3) * 4") == 20
    assert safe_eval("10 / 4") == 2.5
    assert safe_eval("2 ** 10") == 1024
    assert safe_eval("7 // 2") == 3
    assert safe_eval("10 % 3") == 1


def test_constants():
    assert safe_eval("2 * pi") == pytest.approx(6.283185307179586)
    assert safe_eval("e + 1") == pytest.approx(3.718281828459045)


def test_functions():
    assert safe_eval("round(3.14159, 2)") == 3.14
    assert safe_eval("abs(-5)") == 5
    assert safe_eval("min(3, 1, 2)") == 1


def test_injection_attempts_are_rejected():
    with pytest.raises(ValueError):
        safe_eval("__import__('os').system('dir')")
    with pytest.raises(ValueError):
        safe_eval("print('hola')")
    with pytest.raises(ValueError):
        safe_eval("open('C:/Windows/win.ini')")
    with pytest.raises(ValueError):
        safe_eval("[1, 2, 3]")
    with pytest.raises(ValueError):
        safe_eval("1 + 2; 3")


def test_invalid_expression_raises():
    with pytest.raises(ValueError):
        safe_eval("2 +")
    with pytest.raises(ZeroDivisionError):
        safe_eval("1 / 0")