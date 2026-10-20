"""Tests de los limites de seguridad del nucleo (no del proveedor).

Dos problemas que el proveedor local deja al alcance:

1. `calculator` evalua '**' sin tope. Una expresion como '9**9**9' produce un
   numero con 369 millones de digitos: el hilo que la calcula monopoliza el
   GIL, y como el pipeline de voz es sincrono, **ZIX entero deja de
   responder**. No es una excepcion: es una congelacion.

2. `Agent.reset_session()` no se llama nunca, asi que el historial crece sin
   limite. Cada turno anade mensajes, y con el bucle de tools anaden mas.
   Eso consume memoria y amplifica cualquier contenido inyectado, porque
   todo el historial se reenvia al modelo en cada turno.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from zix.config import Config
from zix.core.agent import Agent
from zix.core.ai_provider import AgentResponse, ChatMessage, ToolCall, ToolSpec
from zix.core.tool_executor import ToolExecutor
from zix.core.tool_registry import ToolRegistry
from zix.tools import register_builtin_tools
from zix.tools.calculator import safe_eval


# --- 1. la calculadora no se puede congelar ------------------------------


def test_una_potencia_descomunal_se_rechaza_rapido():
    """'9**9**9' son 369 millones de digitos: antes colgaba el proceso."""
    inicio = time.monotonic()
    with pytest.raises(ValueError):
        safe_eval("9**9**9")
    assert time.monotonic() - inicio < 2.0, "tardo demasiado en rechazarlo"


def test_una_potencia_con_exponente_enorme_se_rechaza():
    inicio = time.monotonic()
    with pytest.raises(ValueError):
        safe_eval("10**100000000")
    assert time.monotonic() - inicio < 2.0


def test_una_expresion_larguisima_se_rechaza():
    with pytest.raises(ValueError):
        safe_eval("1+" * 5000 + "1")


def test_una_expresion_con_muchos_terminos_se_rechaza():
    with pytest.raises(ValueError):
        safe_eval("+".join(["1"] * 5000))


def test_las_calculaciones_normales_siguen_funcionando():
    assert safe_eval("25 * 48") == 1200
    assert safe_eval("(2 + 3) * 4") == 20
    assert safe_eval("2 ** 10") == 1024
    assert safe_eval("10 ** 6") == 1000000
    assert safe_eval("round(3.14159, 2)") == 3.14
    assert safe_eval("max(1, 7, 3)") == 7
    assert safe_eval("abs(-5)") == 5


# --- 2. el historial del agente no crece sin limite -----------------------


class _ProveedorFicticio:
    """Devuelve siempre una respuesta de texto, sin llamar a nadie."""

    def __init__(self) -> None:
        self.turnos = 0

    def complete(self, messages, tools) -> AgentResponse:
        self.turnos += 1
        return AgentResponse(content=f"respuesta {self.turnos}")


def _agente() -> tuple[Agent, _ProveedorFicticio]:
    registro = ToolRegistry()
    register_builtin_tools(registro)
    proveedor = _ProveedorFicticio()
    agente = Agent(
        provider=proveedor,
        executor=ToolExecutor(registro),
        config=Config(max_agent_iterations=3, max_history_messages=20),
    )
    return agente, proveedor


def test_el_historial_no_crece_sin_limite():
    """60 turnos con el limite en 20: el historial se queda acotado."""
    agente, _ = _agente()
    for i in range(60):
        agente.run(f"mensaje {i}")
    assert len(agente._messages) <= 20, (
        f"el historial llego a {len(agente._messages)} mensajes"
    )


def test_el_prompt_de_sistema_siempre_se_conserva():
    """Al truncar, el mensaje de sistema no se puede perder: es el que
    dice que hable espanol y que use las tools."""
    agente, _ = _agente()
    for i in range(40):
        agente.run(f"mensaje {i}")
    assert agente._messages[0].role == "system"
    assert "ZIX" in agente._messages[0].content


def test_tras_truncar_el_agente_sigue_respondiendo():
    agente, _ = _agente()
    for i in range(40):
        agente.run(f"mensaje {i}")
    assert agente.run("otra vez").startswith("respuesta")


# --- 3. el turno tiene un presupuesto de tiempo --------------------------


class _ProveedorLento:
    """Tarda como un motor local que no contesta, y pide otra tool.

    Si devolviera solo texto, el agente terminaria en la primera iteracion
    y el presupuesto no tendria nada que acotar. Con una tool call, el
    bucle sigue iterando, que es justo el caso peligroso.
    """

    def __init__(self, segundos: float) -> None:
        self._segundos = segundos
        self.turnos = 0

    def complete(self, messages, tools) -> AgentResponse:
        self.turnos += 1
        time.sleep(self._segundos)
        return AgentResponse(
            content=None,
            tool_calls=[ToolCall(id=f"c{self.turnos}", name="echo",
                                arguments={"text": "sigo"})],
        )


def test_un_turno_no_puede_durar_mas_alla_del_presupuesto():
    """Sin presupuesto, 10 iteraciones x 300 s = 50 min sin microfono."""
    registro = ToolRegistry()
    register_builtin_tools(registro)
    proveedor = _ProveedorLento(segundos=0.3)
    agente = Agent(
        provider=proveedor,
        executor=ToolExecutor(registro),
        config=Config(max_agent_iterations=50, max_turn_seconds=1.0),
    )
    inicio = time.monotonic()
    respuesta = agente.run("dime algo")
    duracion = time.monotonic() - inicio
    assert duracion < 6, f"el turno duro {duracion:.1f} s"
    assert "tiempo" in respuesta.lower()
    assert proveedor.turnos < 50, "no se respeta el presupuesto"
