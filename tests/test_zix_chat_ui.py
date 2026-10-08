"""Tests de la pantalla Chat de ZIX (`apps/zix-ui/zix-main.html`).

Chat cierra el flujo `LOGIN -> DESCARGA -> CONFIGURACION -> HOME -> CHAT`.
Copia byte a byte del proyecto `zix app` de Open Design (sha 1B0E371E...), que
ya llega sin datos de modelo, proveedor ni uso inventados.

Regla de este test: se comprueban las cadenas VISIBLES que afirmaban datos
falsos. Los `70%` que quedan en el CSS son paradas de opacidad de
`color-mix()` y de los degradados de aurora, no el dato de uso, y no se tocan.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parents[1] / "apps" / "zix-ui"
CHAT_PATH = UI / "zix-main.html"


@pytest.fixture(scope="module")
def chat() -> str:
    assert CHAT_PATH.exists(), f"no existe {CHAT_PATH}"
    return CHAT_PATH.read_text(encoding="utf-8")


def _visible(texto: str) -> str:
    """Markup sin comentarios ni CSS: solo lo que el usuario ve o ejecuta."""
    limpio = re.sub(r"<!--.*?-->", " ", texto, flags=re.S)
    limpio = re.sub(r"<style[^>]*>.*?</style>", " ", limpio, flags=re.S)
    return re.sub(r"/\*.*?\*/", " ", limpio, flags=re.S)


# ───────────────────── ningún dato inventado en pantalla ───────────────


@pytest.mark.parametrize(
    "falso",
    [
        "GPT-4o",
        "OpenAI",
        "128k tokens",
        "21 de 30",
        "Único modelo configurado",
        "2024-08-06",
        "Potencia",
    ],
)
def test_no_queda_ningun_modelo_ficticio(chat: str, falso: str) -> None:
    assert falso not in _visible(chat), f"queda el dato falso {falso!r}"


def test_el_anillo_no_muestra_el_porcentaje_falso(chat: str) -> None:
    """El centro del anillo es un guion, nunca un porcentaje."""
    centro = re.search(r'class="usage-ring-text"[^>]*>\s*([^<]*?)\s*<', chat)
    assert centro, "no se encuentra el centro del anillo"
    valor = centro.group(1).strip()
    assert valor in {"-", "—"}, f"el anillo muestra {valor!r}"
    assert "%" not in valor, "el anillo no debe mostrar porcentajes"


def test_read_model_no_inventa_un_nombre(chat: str) -> None:
    """El fallo clave: con HTML limpio pero JS devolviendo un nombre, el
    modelo volvía a aparecer solo."""
    codigo = _visible(chat)
    assert "readModel" in codigo
    assert "|| 'GPT-4o'" not in codigo
    assert "GPT-4o" not in codigo


# ─────────────────────────── estados vacíos ────────────────────────────


def test_sidebar_modelo_esta_vacio(chat: str) -> None:
    assert 'data-od-id="sidebar-model"' in chat
    assert "Aún no hay un modelo vinculado" in chat


def test_ajustes_modelo_esta_vacio(chat: str) -> None:
    grupo = chat[chat.index('data-od-id="settings-model"') :]
    grupo = grupo[: grupo.index("</div><!--") + 200] if "</div><!--" in grupo else grupo[:900]
    assert 'aria-label="Modelo de IA"' in grupo
    assert "Aún no hay un modelo vinculado" in grupo
    assert 'name="zix-model"' not in grupo


def test_ajustes_proveedor_esta_vacio(chat: str) -> None:
    assert 'data-od-id="settings-provider"' in chat
    assert "Aún no hay un proveedor vinculado" in chat


def test_chip_dice_sin_modelo(chat: str) -> None:
    assert 'id="model-chip-label"' in chat
    assert ">Sin modelo<" in chat
    assert "Sin modelo vinculado. Abrir configuración" in chat


def test_el_anillo_se_conserva_sin_datos(chat: str) -> None:
    """Variante A: el componente sigue, pero sin números."""
    assert 'data-od-id="settings-usage"' in chat
    assert "is-empty" in chat
    assert "Plan mensual" in chat
    assert "Sin datos de uso" in chat


def test_reutiliza_el_componente_empty_del_diseno(chat: str) -> None:
    """.empty debe ser el mismo bloque que Home, copiado literalmente."""
    home = (UI / "zix-home-tarjeta.html").read_text(encoding="utf-8")
    bloque_chat = re.search(r"(?s)\.empty\s*\{(.*?)\}", chat)
    bloque_home = re.search(r"(?s)\.empty\s*\{(.*?)\}", home)
    assert bloque_chat and bloque_home
    normalizar = lambda s: re.sub(r"\s+", " ", s).strip()
    assert normalizar(bloque_chat.group(1)) == normalizar(bloque_home.group(1))


def test_sin_doble_borde_en_las_tarjetas_de_ajustes(chat: str) -> None:
    assert ".settings-card:has(> .empty)" in chat
    bloque = chat[chat.index(".settings-card:has(> .empty)") :][:160]
    assert "border: 0" in bloque


# ─────────────────────── lo que sí es real y se conserva ──────────────


def test_identidad_de_particulas_intacta(chat: str) -> None:
    for oid in ("particle-field", "particle-halo", "aurora-a", "aurora-b", "ambient-bg"):
        assert f'data-od-id="{oid}"' in chat
    assert "<canvas" in chat


def test_estado_y_transcripcion_intactos(chat: str) -> None:
    assert 'id="status-badge"' in chat
    assert 'id="status-text"' in chat
    assert 'id="transcription-text"' in chat
    assert "En espera de tu voz" in chat


def test_botones_de_accion_intactos(chat: str) -> None:
    assert 'id="btn-new-chat"' in chat
    assert 'id="btn-activate"' in chat
    assert 'aria-pressed="false"' in chat


def test_panel_de_ajustes_con_tema(chat: str) -> None:
    assert 'id="settings-panel"' in chat
    assert 'id="settings-overlay"' in chat
    assert 'id="theme-group"' in chat
    assert 'data-theme-value="light"' in chat
    assert 'data-theme-value="dark"' in chat
    assert 'data-theme-value="system"' in chat


def test_el_volver_apunta_a_home(chat: str) -> None:
    assert 'href="zix-home-tarjeta.html"' in chat
    assert (UI / "zix-home-tarjeta.html").exists(), "Home debe existir"


def test_la_costura_de_historial_sigue_vacia(chat: str) -> None:
    """loadChatHistory es una costura honesta: no inventa historial."""
    codigo = _visible(chat)
    assert "function loadChatHistory(id)" in codigo
    inicio = codigo.index("function loadChatHistory")
    cuerpo = codigo[inicio : inicio + 400]
    assert "id" in cuerpo
    assert "innerHTML" not in cuerpo, "no pinta historial ficticio"


def test_contexto_de_chat_por_session_storage(chat: str) -> None:
    assert "zix-chat-mode" in chat
    assert "sessionStorage.removeItem('zix-chat-mode')" in chat


# ────────────────────────── higiene y navegación ───────────────────────


def test_sin_dependencias_externas(chat: str) -> None:
    for prohibido in (
        "cdn.tailwindcss.com",
        "fonts.googleapis.com",
        "fonts.gstatic.com",
        "unpkg.com",
        "jsdelivr",
    ):
        assert prohibido not in chat


def test_no_hay_peticiones_de_red(chat: str) -> None:
    codigo = _visible(chat)
    for patron in (r"fetch\(", r"XMLHttpRequest", r"WebSocket", "/api/"):
        assert not re.search(patron, codigo), f"no debe aparecer {patron}"


def test_no_accede_al_microfono(chat: str) -> None:
    for patron in ("getUserMedia", "MediaRecorder", "AudioContext", "speechSynthesis"):
        assert patron not in chat


def test_solo_persiste_ajustes_de_interfaz(chat: str) -> None:
    permitidas = {"zix-theme", "zix-model"}
    encontradas = set(re.findall(r"localStorage\.(?:get|set)Item\(\s*'([^']+)'", chat))
    assert encontradas, "debe usar alguna clave de interfaz"
    assert encontradas <= permitidas, encontradas - permitidas


def test_home_ya_tiene_chat_conectado() -> None:
    home = (UI / "zix-home-tarjeta.html").read_text(encoding="utf-8")
    assert "var PANTALLAS = { chat: 'zix-main.html' }" in home
    assert "PANTALLAS_IMPLEMENTADAS = ['zix-main.html']" in home


def test_flujo_completo_de_pantallas() -> None:
    """Las cuatro pantallas del flujo existen y se enlazan en un solo sentido."""
    login = (UI / "zix-login.html").read_text(encoding="utf-8")
    config = (UI / "zix-config.html").read_text(encoding="utf-8")
    home = (UI / "zix-home-tarjeta.html").read_text(encoding="utf-8")
    chat = CHAT_PATH.read_text(encoding="utf-8")

    assert "const NEXT_SCREEN = 'zix-config.html';" in login
    assert 'href="zix-config.html"' in login
    assert "PANTALLAS_IMPLEMENTADAS = ['zix-home-tarjeta.html']" in config
    assert "PANTALLAS_IMPLEMENTADAS = ['zix-main.html']" in home
    assert 'href="zix-home-tarjeta.html"' in chat


def test_sin_destinos_rotos() -> None:
    chat = CHAT_PATH.read_text(encoding="utf-8")
    destinos = set(re.findall(r'href="(zix-[a-z-]+\.html)"', chat))
    assert destinos == {"zix-home-tarjeta.html"}
    for d in destinos:
        assert (UI / d).exists(), f"destino roto: {d}"