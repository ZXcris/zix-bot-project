"""Invariantes de seguridad y accesibilidad compartidas por las pantallas ZIX.

Cubre lo que quedo abierto tras la auditoria profunda con navegador real:
la CSP declarada y el boton de menu como disclosure.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parents[1] / "apps" / "zix-ui"
PAGINAS = ["zix-login.html", "zix-config.html", "zix-home-tarjeta.html", "zix-main.html"]


@pytest.fixture(scope="module", params=PAGINAS)
def pagina(request) -> tuple[str, str]:
    ruta = UI / request.param
    assert ruta.exists(), f"no existe {ruta}"
    return request.param, ruta.read_text(encoding="utf-8")


def csp_de(html: str) -> str | None:
    m = re.search(
        r'<meta[^>]*http-equiv="Content-Security-Policy"[^>]*content="([^"]*)"', html
    )
    return m.group(1) if m else None


# ────────────────────────────────  CSP  ────────────────────────────────


def test_todas_las_pantallas_declaran_csp(pagina) -> None:
    nombre, html = pagina
    assert csp_de(html), f"{nombre} no declara Content-Security-Policy"


def test_la_csp_prohibe_salir_a_la_red(pagina) -> None:
    """connect-src 'none' convierte en garantia que la pagina no telefonea."""
    nombre, html = pagina
    politica = csp_de(html)
    assert "connect-src 'none'" in politica, f"{nombre} permite conexiones salientes"
    assert "default-src 'none'" in politica, f"{nombre} no cierra por defecto"


def test_la_csp_no_promete_lo_que_el_navegador_ignora(pagina) -> None:
    """frame-ancestors dentro de un meta se ignora: no hay que vender proteccion falsa."""
    nombre, html = pagina
    politica = csp_de(html)
    assert "frame-ancestors" not in politica, (
        f"{nombre} declara frame-ancestors, que los navegadores ignoran en un meta"
    )


def test_la_csp_permite_lo_que_la_pagina_usa(pagina) -> None:
    """Script y estilo son inline: sin 'unsafe-inline' la pagina se quedaria muda."""
    nombre, html = pagina
    politica = csp_de(html)
    assert "'unsafe-inline'" in politica
    for directiva in ("script-src", "style-src", "img-src", "font-src"):
        assert directiva in politica, f"{nombre} sin {directiva}"


def test_la_csp_cierra_objetivos_y_formularios(pagina) -> None:
    nombre, html = pagina
    politica = csp_de(html)
    assert "object-src 'none'" in politica, f"{nombre} permite object/embed"
    assert "form-action 'none'" in politica, f"{nombre} permite enviar formularios"
    assert "base-uri 'none'" in politica, f"{nombre} permite manipular <base>"


# ───────────────────────  boton de menu = disclosure  ──────────────────


def test_el_boton_de_menu_declara_su_estado() -> None:
    chat = (UI / "zix-main.html").read_text(encoding="utf-8")
    boton = re.search(r'<button[^>]*id="btn-menu"[^>]*>', chat)
    assert boton, "no existe el boton de menu"
    etiqueta = boton.group(0)
    assert 'aria-expanded="false"' in etiqueta, "no declara el estado inicial"
    assert 'aria-controls="sidebar"' in etiqueta, "no declara que controla"
    assert "aria-label=" in etiqueta


def test_el_boton_de_menu_sincroniza_aria_al_alternar() -> None:
    """Un disclosure que no actualiza su estado no sirve de nada."""
    chat = (UI / "zix-main.html").read_text(encoding="utf-8")
    manejador = re.search(r"(?s)btnMenu\.addEventListener\('click'.*?\n\s*\}\);", chat)
    assert manejador, "no se encuentra el manejador del boton de menu"
    cuerpo = manejador.group(0)
    assert "setAttribute('aria-expanded'" in cuerpo
    assert "setAttribute('aria-label'" in cuerpo
    assert "sidebarOpen" in cuerpo


# ──────────────────  ningun control sin nombre accesible  ───────────────


def test_ningun_control_se_queda_sin_nombre() -> None:
    """Cada control necesita aria-label, texto visible o <label for>."""
    # selector de atributos + tags con contenido textual
    controles = re.compile(
        r"<(button|a\s[^>]*href=|input|select|textarea)\b([^>]*)>", re.I
    )
    for pagina in PAGINAS:
        html = (UI / pagina).read_text(encoding="utf-8")
        cuerpo = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", html, flags=re.S)
        ids_con_label = set(re.findall(r'<label[^>]*for="([^"]+)"', cuerpo))
        for m in controles.finditer(cuerpo):
            atributos = m.group(0)
            tag = m.group(1).split()[0].lower()
            etiqueta_id = re.search(r'id="([^"]+)"', atributos)
            tiene = (
                "aria-label=" in atributos
                or "aria-labelledby=" in atributos
                or "title=" in atributos
                or (etiqueta_id and etiqueta_id.group(1) in ids_con_label)
            )
            if not tiene and tag in ("button", "a"):
                # necesita texto visible entre la apertura y el cierre
                resto = cuerpo[m.end(): m.end() + 6000]
                cierre = re.compile(rf"(?s)(.*?)</{re.escape(tag)}\s*>", re.I).match(resto)
                if cierre:
                    # los <svg aria-hidden> no aportan texto al nombre accesible
                    interior = re.sub(r"(?s)<svg.*?</svg>", " ", cierre.group(1))
                    tiene = bool(re.sub(r"<[^>]*>", " ", interior).strip())
            assert tiene, f"{pagina}: control sin nombre accesible -> {atributos[:90]}"