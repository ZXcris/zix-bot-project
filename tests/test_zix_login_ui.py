"""Tests de la cadena Login → Configuración de ZIX.

`zix-login.html` es siempre la entrada y `zix-config.html` la única puerta a
Home: el login NO decide si la voz ya está configurada. Blueprint visual:
proyecto `zix app` de Open Design.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parents[1] / "apps" / "zix-ui"
LOGIN_PATH = UI / "zix-login.html"
CONFIG_PATH = UI / "zix-config.html"


@pytest.fixture(scope="module")
def login() -> str:
    assert LOGIN_PATH.exists(), f"no existe {LOGIN_PATH}"
    return LOGIN_PATH.read_text(encoding="utf-8")


def test_la_pantalla_de_configuracion_existe() -> None:
    assert CONFIG_PATH.exists(), "el login apunta a zix-config.html: debe existir"


def test_el_login_siempre_entra_en_configuracion(login: str) -> None:
    assert "const NEXT_SCREEN = 'zix-config.html';" in login
    assert "function nextScreen() { return NEXT_SCREEN; }" in login


def test_el_login_no_decide_segun_el_estado_de_voz(login: str) -> None:
    """La decisión vive en un único sitio: Configuración."""
    assert "zix-voice-setup" not in _sin_comentarios(login)
    assert "zix-home-tarjeta" not in login


def test_el_href_estatico_respeta_la_misma_ruta(login: str) -> None:
    ancla = login[login.index('id="btn-enter"') :]
    ancla = ancla[: ancla.index(">")]
    assert 'href="zix-config.html"' in ancla, "respaldo sin JavaScript"


def test_el_ancla_tiene_id_para_el_js(login: str) -> None:
    """Sin `id`, el TypeError deja la página en blanco (body opacity: 0)."""
    ancla = login[login.index("<a class=\"btn btn-primary\"") :]
    ancla = ancla[: ancla.index(">")]
    assert 'id="btn-enter"' in ancla
    assert "document.getElementById('btn-enter')" in login


def test_la_navegacion_no_deja_la_pantalla_a_medias(login: str) -> None:
    assert "document.body.classList.add('page-out')" in login
    assert "setTimeout(() => { window.location.href = target; }, 230)" in login
    assert "enterLink.addEventListener('click', (e) => { e.preventDefault(); goNext(); })" in login


def test_la_descarga_sigue_siendo_visual(login: str) -> None:
    assert "CAPTURE_MS" not in login  # la descarga usa su propio setStep
    assert "runDownload" in login
    assert "Punto único de pintado del estado" in login
    for patron in ("getUserMedia", "MediaRecorder", "fetch(", "XMLHttpRequest"):
        assert patron not in _sin_comentarios(login)


def test_configuracion_es_la_unica_puerta_a_home() -> None:
    config = CONFIG_PATH.read_text(encoding="utf-8")
    assert (UI / "zix-home-tarjeta.html").exists(), "Home ya está implementado"
    assert "zix-home-tarjeta.html" in config
    assert "PANTALLAS_IMPLEMENTADAS = ['zix-home-tarjeta.html']" in config
    assert "function screenReady(file)" in config
    assert "if (!screenReady(target)) { markHomePending(); return; }" in config
    assert 'href="zix-home-tarjeta.html"' not in config, "sin 404"


def test_los_tres_estados_de_configuracion() -> None:
    config = CONFIG_PATH.read_text(encoding="utf-8")
    assert "value === 'done'" in config
    assert "value === 'skipped'" in config
    assert "applySkippedState()" in config
    assert "saveSetup('done')" in config
    assert "saveSetup('skipped')" in config


def test_no_se_persiste_nada_en_el_login(login: str) -> None:
    assert not re.findall(r"localStorage\.setItem\('([^']+)'", _sin_comentarios(login))


def _sin_comentarios(texto: str) -> str:
    limpio = re.sub(r"<!--.*?-->", " ", texto, flags=re.S)
    limpio = re.sub(r"/\*.*?\*/", " ", limpio, flags=re.S)
    return re.sub(r"//[^\n]*", " ", limpio)
