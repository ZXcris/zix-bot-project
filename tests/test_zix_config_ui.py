"""Tests de la pantalla de configuración de ZIX (`apps/zix-ui/zix-config.html`).

La pantalla es VISUAL en esta etapa: no hay backend, no se captura audio y no
se ejecutan las peticiones habladas. Estos tests fijan ese contrato para que
nadie introduzca functionality falsa por descuido.

Blueprint visual: proyecto `zix app` de Open Design.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "apps" / "zix-ui" / "zix-config.html"
)
UI = CONFIG_PATH.parent


@pytest.fixture(scope="module")
def html() -> str:
    assert CONFIG_PATH.exists(), f"no existe {CONFIG_PATH}"
    return CONFIG_PATH.read_text(encoding="utf-8")


def _sin_comentarios(texto: str) -> str:
    """Quita comentarios CSS/JS/HTML para no validar lo que solo se explica."""
    limpio = re.sub(r"<!--.*?-->", " ", texto, flags=re.S)
    limpio = re.sub(r"/\*.*?\*/", " ", limpio, flags=re.S)
    return re.sub(r"//[^\n]*", " ", limpio)


# ───────────────────────────── estructura ─────────────────────────────


def test_la_pantalla_existe(html: str) -> None:
    assert "<!doctype html>" in html
    assert '<html lang="es">' in html
    assert "ZIX IA — Configura ZIX" in html


def test_cuatro_pasos_guizados(html: str) -> None:
    """El flujo tiene 4 pasos, tal como define `zix app`."""
    pasos = re.findall(r'data-step="(\d)"', html)
    assert pasos == ["1", "2", "3", "4"]
    assert html.count('<i class="on"></i><i></i><i></i><i></i>') == 1
    assert "Paso 1 de 4" in html
    assert "'Paso ' + n + ' de 4'" in html


def test_copy_de_los_cuatro_pasos(html: str) -> None:
    for copy in (
        "Busca un lugar tranquilo",
        "Di: Hey Zix",
        "Repite la frase",
        "Tu voz está configurada",
    ):
        assert copy in html


def test_estado_final(html: str) -> None:
    assert 'id="ready"' in html
    assert "ZIX está listo" in html
    assert 'id="btn-enter"' in html
    assert "Entrar a ZIX" in html


# ────────────────────────────── 5 muestras ──────────────────────────────


def test_cinco_muestras(html: str) -> None:
    assert html.count('class="seg"') == 5
    assert "SAMPLES = REQUESTS.length" in html
    assert "samplesCount.textContent = '1 / ' + SAMPLES" in html
    assert 'id="sample-progress"' in html, "el id que consulta '#sample-progress .seg'"


def test_cinco_peticiones_distintas(html: str) -> None:
    bloque = re.search(r"var REQUESTS = \[(.*?)\];", html, re.S)
    assert bloque, "no se encuentra REQUESTS"
    peticiones = re.findall(r"'([^']+)'", bloque.group(1))
    assert len(peticiones) == 5
    assert len(set(peticiones)) == 5, "las peticiones deben ser distintas"
    assert "Hey Zix" in html


def test_contador_y_segmentos_coinciden(html: str) -> None:
    """`N / 5` y las líneas encendidas no pueden desincronizarse.

    El segmento se enciende al EMPEZAR la muestra, por eso la línea que enciende
    tiene que aparecer ANTES de `capture(...)`.
    """
    assert "(sample + 1) + ' / ' + SAMPLES" in html
    take = html[html.index("function takeSample()") :]
    encender = take.index("segs[sample].classList.add('on')")
    capturar = take.index("capture(rec3")
    assert encender < capturar, "el segmento debe encenderse al empezar la muestra"


def test_no_vuelve_a_tres_muestras(html: str) -> None:
    assert "3 / 3" not in html
    assert "SAMPLES = 3" not in html
    assert html.count('class="seg"') != 3


def test_no_hay_estado_de_muestra_invalida(html: str) -> None:
    """Open Design no define estado de muestra inválida: no se inventa.

    Cuando exista diseño oficial para una muestra rechazada, este test debe
    cambiar para describir ese estado.
    """
    assert "--error" not in html
    for inventado in ("reintentar", "Reintentar", "muestra inválida", "No se detectó voz"):
        assert inventado not in html


# ───────────────────────── persistencia permitida ───────────────────────


def test_solo_se_persiste_zix_voice_setup(html: str) -> None:
    guardadas = re.findall(r"localStorage\.setItem\('([^']+)'", html)
    assert set(guardadas) == {"zix-voice-setup"}, guardadas


def test_configuracion_completada_y_omitida(html: str) -> None:
    assert "saveSetup('done')" in html
    assert "saveSetup('skipped')" in html
    assert re.search(r"act === 'finish'\) \{ saveSetup\('done'\)", html)


def test_no_se_guarda_audio_ni_datos_sensibles(html: str) -> None:
    codigo = _sin_comentarios(html)
    for prohibido in (
        "embedding",
        "biometric",
        "credential",
        "apiKey",
        "audioBase64",
        "zix-voice-print",
        "zix-collab",
    ):
        assert prohibido not in codigo, f"no debe aparecer {prohibido}"


def test_el_tema_solo_se_lee(html: str) -> None:
    assert "localStorage.getItem('zix-theme')" in html
    assert "localStorage.setItem('zix-theme'" not in html


# ─────────────────────────── colaboración ───────────────────────────────


def test_bloque_de_colaboracion(html: str) -> None:
    assert "Colabora con ZIX" in html
    assert "Quiero colaborar" in html
    assert "Tu participación es opcional." in html
    assert "Ahora no" in html


def test_consentimiento_explicito(html: str) -> None:
    consent = html[html.index('id="consent"') : html.index('id="btn-skip"')]
    assert consent.count("<li>") == 3, "los 3 puntos del consentimiento oficial"
    assert "HeY ZiX".replace("HeY ZiX", "‘Hey Zix’") in consent


def test_aceptar_colaborar_deshabilitado(html: str) -> None:
    boton = html[html.index('id="btn-accept-collab"') :]
    boton = boton[: boton.index(">")]
    assert "disabled" in boton
    assert 'title="Disponible cuando ZIX tenga servicio de envío"' in boton


def test_no_se_finge_colaboracion(html: str) -> None:
    """El botón es un seam vacío: no persiste ni envía nada."""
    assert "submitVoiceContribution()" in html
    assert "TODO backend: submitVoiceContribution()" in html
    assert "setItem('zix-collab'" not in html


# ───────────────────── sin backend ni ejecución real ────────────────────


def test_no_hay_dependencia_de_backend(html: str) -> None:
    for patron in (
        r"fetch\(",
        r"XMLHttpRequest",
        r"WebSocket",
        r"/api/",
        r"localhost",
        r"https?://(?!www\.w3\.org)",
    ):
        assert not re.search(patron, html), f"no debe aparecer {patron}"


def test_no_se_accede_al_microfono(html: str) -> None:
    for patron in ("getUserMedia", "MediaRecorder", "AudioContext", "speechSynthesis"):
        assert patron not in html


def test_no_se_ejecutan_las_peticiones_habladas(html: str) -> None:
    """Las 5 peticiones son texto de referencia, nunca llamadas a un agente."""
    codigo = _sin_comentarios(html)
    assert "REQUESTS[sample]" in codigo
    assert "agent.run" not in codigo
    assert "fetch" not in codigo


def test_captura_es_simulada(html: str) -> None:
    assert "CAPTURE_MS" in html
    assert "function capture(" in html
    assert "Escucha SIMULADA" in html
    assert "grabVoiceSample()" in html, "deja documentada la costura de backend"


# ───────────────────────── navegación segura ────────────────────────────


def test_navega_a_home_ya_implementado(html: str) -> None:
    """Home existe: 'Entrar a ZIX' queda habilitado y navega de verdad."""
    assert (UI / "zix-home-tarjeta.html").exists()
    assert "PANTALLAS_IMPLEMENTADAS = ['zix-home-tarjeta.html']" in html
    assert "function screenReady(file)" in html
    assert "if (!screenReady(target)) { markHomePending(); return; }" in html, "el guardia se conserva para pantallas futuras"
    assert 'href="zix-home-tarjeta.html"' not in html, "el destino lo arma el JS, no un href estático"


def test_continuar_sin_configurar_no_depende_de_home(html: str) -> None:
    assert 'id="btn-skip"' in html
    assert "Continuar sin configurar" in html


# ─────────────────────── tokens y accesibilidad ─────────────────────────


def test_tokens_locales_del_diseno(html: str) -> None:
    for token in (
        "--bg:      #ffffff",
        "--surface: #f4f4f4",
        "--accent:    #2563eb",
        "--accent-ink: #1d4ed8",
        "--radius-card:    28px",
        "--radius-control: 20px",
        "--font-body: 'Inter'",
    ):
        assert token in html
    assert "1a1a1a" in html, "variante oscura del monolito"
    assert "8ab0ff" in html, "accent-ink oscuro"
    assert "--bg-warm" not in html, "auth/setup usa --bg, no el canvas de la app"


def test_sin_dependencias_externas(html: str) -> None:
    assert "cdn.tailwindcss.com" not in html
    assert "fonts.googleapis.com" not in html
    assert "fonts.gstatic.com" not in html
    assert "Material Symbols" not in html


def test_accesibilidad_definida(html: str) -> None:
    assert ":focus-visible" in html
    assert "prefers-reduced-motion" in html
    assert "aria-live" in html
    assert "aria-hidden" in html
    assert "[hidden] { display: none !important; }" in html
    assert "<noscript>" in html
    assert "min-height: 48px" in html


def test_responsive(html: str) -> None:
    assert "@media (max-width: 640px)" in html
    assert "@media (max-width: 420px)" in html


def test_data_od_id_en_los_elementos_estructurales(html: str) -> None:
    for oid in (
        "config-shell",
        "config-setup",
        "config-header",
        "card-configure-voice",
        "btn-configurar-voz",
        "voice-flow",
        "flow-step-lugar",
        "flow-step-frase",
        "record-indicator",
        "flow-step-muestras",
        "sample-progress",
        "flow-step-listo",
        "card-collaborate",
        "btn-colaborar",
        "collab-consent",
        "btn-aceptar-colaboracion",
        "skip-setup",
        "btn-continuar-sin-configurar",
        "config-ready",
        "btn-entrar-a-zix",
    ):
        assert f'data-od-id="{oid}"' in html, f"falta data-od-id {oid}"


def test_sin_placeholders_de_pantallas_futuras(html: str) -> None:
    """No se crean Home/Chat para tapar un 404."""
    assert "zix-main.html" not in html
    assert "zix-chat" not in html
