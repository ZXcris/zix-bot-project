"""La lista blanca de open_app no puede contener una shell.

Vigila la invariante de seguridad mas importante del nucleo: si el LLM puede
convencer a ZIX de abrir un interprete de comandos, todas las demas garantias
del proyecto dejan de valer. Un solo test lo impide.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from zix.tools.open_app import (
    FORBIDDEN_BINARIES,
    KNOWN_APPS,
    open_app,
    open_app_tool,
)

RAIZ = Path(__file__).resolve().parents[1]


def test_la_terminal_no_esta_en_la_lista_blanca() -> None:
    """Regresión: 'terminal' se quitó el 2026-10-09 tras detectarlo en vivo."""
    assert "terminal" not in KNOWN_APPS
    assert "consola" not in KNOWN_APPS
    assert "shell" not in KNOWN_APPS
    assert "cmd" not in KNOWN_APPS


def test_ninguna_app_de_la_lista_es_un_interprete() -> None:
    """Ningun ejecutable de la lista puede ser una shell, un script o un downloading tool."""
    for app, candidatos in KNOWN_APPS.items():
        for candidato in candidatos:
            nombre = os.path.basename(candidato.lower())
            assert nombre not in FORBIDDEN_BINARIES, (
                f"la app '{app}' apunta a un interprete de comandos: {candidato}"
            )


def test_la_lista_blanca_no_esta_vacia() -> None:
    """Evita que un fallo de edicion deje la herramienta inutilizable."""
    assert len(KNOWN_APPS) >= 10
    assert all(isinstance(v, list) and v for v in KNOWN_APPS.values())


def test_rechaza_una_shell_por_nombre() -> None:
    for intento in ("terminal", "cmd", "cmd.exe", "powershell", "bash", "wsl"):
        respuesta = open_app(intento).lower()
        assert "rechazada" in respuesta, f"'{intento}' deberia rechazarse"


def test_rechaza_una_ruta_arbitraria() -> None:
    """El modelo no puede pasar rutas: solo claves de la lista."""
    for intento in (
        "cmd.exe",
        "c:\\windows\\system32\\cmd.exe",
        "../../windows/system32/cmd.exe",
        "notepad.exe",
        "powershell.exe",
    ):
        respuesta = open_app(intento).lower()
        assert "rechazada" in respuesta, f"'{intento}' deberia rechazarse"


def test_la_segunda_barrara_corta_aunque_metan_una_shell(monkeypatch) -> None:
    """Si alguien anade 'notepad2' -> cmd.exe, la guarda de runtime lo impide."""
    monkeypatch.setitem(KNOWN_APPS, "notepad2", [r"C:\Windows\System32\cmd.exe"])
    monkeypatch.setattr(
        "zix.tools.open_app._resolve_candidates", lambda c: r"C:\Windows\System32\cmd.exe"
    )
    respuesta = open_app("notepad2")
    assert "Rechazada" in respuesta
    assert "intérprete de comandos" in respuesta


def test_rechaza_una_ruta_de_windows_en_cualquier_sistema(monkeypatch) -> None:
    """La segunda barrera tiene que ver una ruta de Windows tambien en Linux.

    Antes se comparaba solo os.path.basename, que en Linux parte por '/' y
    deja 'C:\\Windows\\System32\\cmd.exe' enterita: el nombre no casaba con
    ningun prohibido y la barrera se saltaba. Lo detecto el CI al correr la
    suite en Linux.
    """
    monkeypatch.setitem(KNOWN_APPS, "atajo", [r"C:\Windows\System32\cmd.exe"])
    monkeypatch.setattr(
        "zix.tools.open_app._resolve_candidates",
        lambda c: r"C:\Windows\System32\cmd.exe",
    )
    respuesta = open_app("atajo")
    assert "Rechazada" in respuesta, f"una shell debe rechazarse siempre: {respuesta}"


def test_el_nombre_de_la_herramienta_no_anuncia_shells() -> None:
    """La descripcion que ve el modelo es el contrato: no debe ofrecer terminal."""
    descripcion = open_app_tool.description.lower()
    assert "terminal" not in descripcion
    assert "cmd" not in descripcion
    assert "powerpoint" in descripcion  # sigue anunciando las apps que sí puede abrir


def test_open_app_no_usa_shell() -> None:
    """Debe seguir usando la forma de lista, que no interpreta metacaracteres.

    Se comprueba con ast, no buscando texto: 'shell=True' aparece legitimamente
    en los docstrings que explican que NO se usa, y un grep daria un falso
    positivo.
    """
    import ast

    fuente = (RAIZ / "src" / "zix" / "tools" / "open_app.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)

    llamadas_con_shell = 0
    popen_con_lista = 0
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        func = nodo.func
        nombre = getattr(func, "attr", None) or getattr(func, "id", None)
        for kw in nodo.keywords:
            if kw.arg == "shell":
                llamadas_con_shell += 1
        if nombre == "Popen":
            # shell=False explicito o, por defecto, sin shell: la forma segura es
            # pasar una lista y ningun argumento shell.
            popen_con_lista += (
                1 if isinstance(nodo.args[0] if nodo.args else None, (ast.List, ast.Name))
                else 0
            )

    assert llamadas_con_shell == 0, "ninguna llamada debe pasar shell=..."
    assert popen_con_lista == 1, "Popen debe recibir una lista, no una cadena"
    assert "os.system" not in fuente


@pytest.mark.parametrize(
    "app",
    ["chrome", "edge", "firefox", "notepad", "paint", "calculator", "explorer"],
)
def test_las_apps_normales_siguen_disponibles(app: str) -> None:
    """Quitar la shell no puede romper el resto de la herramienta."""
    assert app in KNOWN_APPS
