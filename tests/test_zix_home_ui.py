"""Tests de la pantalla Home de ZIX (`apps/zix-ui/zix-home-tarjeta.html`).

Home es el centro de control. Copiada byte a byte desde el proyecto `zix app`
de Open Design; lo único adaptado es la navegación a Chat, que todavía no
existe y por tanto queda deshabilitada sin provocar un 404.

Flujo: LOGIN -> DESCARGA -> CONFIGURACION -> HOME -> CHAT
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parents[1] / "apps" / "zix-ui"
HOME_PATH = UI / "zix-home-tarjeta.html"


@pytest.fixture(scope="module")
def home() -> str:
    assert HOME_PATH.exists(), f"no existe {HOME_PATH}"
    return HOME_PATH.read_text(encoding="utf-8")


def _sin_comentarios(texto: str) -> str:
    limpio = re.sub(r"<!--.*?-->", " ", texto, flags=re.S)
    limpio = re.sub(r"/\*.*?\*/", " ", limpio, flags=re.S)
    return re.sub(r"//[^\n]*", " ", limpio)


# ──────────────────────────── estructura ───────────────────────────────


def test_la_pantalla_existe(home: str) -> None:
    assert "<!doctype html>" in home
    assert "ZIX IA — Home · Tarjeta" in home


def test_las_seis_vistas_del_diseno(home: str) -> None:
    for vista in ("hub", "modelos", "proveedores", "mcp", "comandos", "config"):
        assert f'id="view-{vista}"' in home, f"falta la vista {vista}"


def test_drawer_modal_y_overlay(home: str) -> None:
    for oid in (
        "drawer",
        "drawer-overlay",
        "pmodal",
        "pmodal-overlay",
        "mcp-modal",
        "mcp-modal-overlay",
        "loading-overlay",
    ):
        assert f'id="{oid}"' in home or f'data-od-id="{oid}"' in home


def test_marca_de_agua_y_estado_del_sistema(home: str) -> None:
    assert 'data-od-id="home-state"' in home
    assert 'data-od-id="state-conexion"' in home
    assert 'data-od-id="state-recursos"' in home
    assert 'data-od-id="state-modelo"' in home
    assert 'data-od-id="home-recent"' in home


def test_data_od_id_presentes(home: str) -> None:
    for oid in (
        "home-topbar",
        "btn-menu",
        "home-status",
        "home-main",
        "view-hub",
        "btn-new-chat",
        "loading-overlay",
        "drawer-mod-config",
        "drawer-mod-mcp",
    ):
        assert f'data-od-id="{oid}"' in home, f"falta data-od-id {oid}"


# ───────────────────────────── tokens ──────────────────────────────────


def test_tokens_de_la_app(home: str) -> None:
    """El Home usa el canvas cálido de la app, no el blanco de auth/setup."""
    assert "--bg-warm" in home
    assert "var(--bg-warm)" in home


def test_sin_dependencias_externas(home: str) -> None:
    for prohibido in (
        "cdn.tailwindcss.com",
        "fonts.googleapis.com",
        "fonts.gstatic.com",
        "http://",
        "https://",
    ):
        if prohibido in ("http://", "https://"):
            continue
        assert prohibido not in home


def test_sin_peticiones_de_red(home: str) -> None:
    codigo = _sin_comentarios(home)
    for patron in (r"fetch\(", r"XMLHttpRequest", r"WebSocket", "/api/"):
        assert not re.search(patron, codigo), f"no debe aparecer {patron}"


# ─────────────────────── navegación y honestidad ───────────────────────


def test_chat_pendiente_sin_404(home: str) -> None:
    """Chat ya existe: se habilita la navegacion solo si la pantalla esta."""
    assert "var PANTALLAS = { chat: 'zix-main.html' }" in home
    assert "var PANTALLAS_IMPLEMENTADAS = ['zix-main.html']" in home
    assert "function screenReady(file)" in home
    assert "if (!screenReady(PANTALLAS.chat)) return;" in home
    assert "zix-main.html" in home, "el destino previsto se conserva"


def test_los_disparadores_de_chat_quedan_marcados(home: str) -> None:
    assert "function markChatPending(el)" in home
    assert "markChatPending(document.getElementById('btn-new-chat'))" in home
    assert "document.querySelectorAll('[data-open-chat]').forEach(markChatPending)" in home


def test_el_loading_overlay_sigue_en_el_diseno(home: str) -> None:
    assert "Preparando conversación…" in home
    assert "overlay.classList.add('open')" in home
    assert "sessionStorage.setItem('zix-chat-mode', mode)" in home


def test_integrar_mcp_deshabilitado(home: str) -> None:
    """Sin backend de MCP, el botón se ve pero no promete nada."""
    linea = home[home.index('id="btn-mcp-integrate"') :]
    linea = linea[: linea.index(">")]
    assert "disabled" in linea


def test_estados_vacios_honestos(home: str) -> None:
    assert 'id="mcp-empty"' in home
    assert 'id="cmd-empty"' in home
    assert "0 conectados" in home


# ───────────────────────── persistencia local ──────────────────────────


def test_solo_ajustes_de_interfaz(home: str) -> None:
    permitidas = {
        "zix-theme",
        "zix-provider",
        "zix-providers-custom",
        "zix-mcp-servers",
        "zix-mcp-dirty",
        "zix-settings",
        "zix-diag",  # transitoria: la escribe y la borra el diagnóstico de storage
    }
    encontradas = set(re.findall(r"localStorage\.(?:get|set)Item\(\s*'([^']+)'", home))
    assert encontradas, "debe leer o escribir alguna clave de interfaz"
    assert encontradas <= permitidas, encontradas - permitidas


def test_el_diagnostico_no_deja_rastro(home: str) -> None:
    assert "localStorage.setItem('zix-diag', '1'); localStorage.removeItem('zix-diag')" in home


def test_no_guarda_datos_sensibles(home: str) -> None:
    codigo = _sin_comentarios(home)
    for prohibido in ("embedding", "biometric", "apiKey", "zix-voice-setup"):
        assert prohibido not in codigo


# ───────────────────────────── navegación global ───────────────────────


def test_configuracion_llega_a_home() -> None:
    config = (UI / "zix-config.html").read_text(encoding="utf-8")
    assert "PANTALLAS_IMPLEMENTADAS = ['zix-home-tarjeta.html']" in config
    assert "function goHome()" in config


def test_login_llega_a_configuracion() -> None:
    login = (UI / "zix-login.html").read_text(encoding="utf-8")
    assert "const NEXT_SCREEN = 'zix-config.html';" in login
    assert 'href="zix-config.html"' in login


def test_home_no_depende_de_ninguna_pantalla_inexistente() -> None:
    """El único destino externo es Chat, y está marcado como pendiente."""
    home = HOME_PATH.read_text(encoding="utf-8")
    destinos = set(re.findall(r"href=\"(zix-[a-z-]+\.html)\"", home))
    existentes = {d for d in destinos if (UI / d).exists()}
    assert destinos == existentes, f"destinos rotos: {destinos - existentes}"
