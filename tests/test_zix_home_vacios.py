"""Tests de los estados vacíos del Home de ZIX.

ZIX todavía no tiene datos vinculados: chats, modelos, proveedores ni MCPs
existen solo como interfaz preparada. Estos tests fijan que la UI no invente
entidades ni Connections, y que el catálogo del Hub use paquetes MCP reales.

Blueprint: proyecto `zix app` de Open Design. El componente de estado vacío es
`.empty`, que el diseño ya define y usa en `mcp-empty`, `cmd-empty` y
`cfg-no-results`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

HOME_PATH = (
    Path(__file__).resolve().parents[1] / "apps" / "zix-ui" / "zix-home-tarjeta.html"
)


@pytest.fixture(scope="module")
def home() -> str:
    assert HOME_PATH.exists(), f"no existe {HOME_PATH}"
    return HOME_PATH.read_text(encoding="utf-8")


def _sin_comentarios(texto: str) -> str:
    limpio = re.sub(r"<!--.*?-->", " ", texto, flags=re.S)
    limpio = re.sub(r"/\*.*?\*/", " ", limpio, flags=re.S)
    return re.sub(r"//[^\n]*", " ", limpio)


# ─────────────────── no hay datos de demostración ──────────────────────


@pytest.mark.parametrize(
    "demo",
    [
        "Conversación actual",
        "Despertador",
        "Resumen de hoy",
        "Reproducir música",
        "GPT-4o",
        "GPT-4",
        "OpenAI",
        "4 de 4",
        "Único modelo configurado",
    ],
)
def test_no_queda_ningun_dato_demo(home: str, demo: str) -> None:
    assert demo not in home, f"queda el dato de ejemplo {demo!r}"


def test_no_hay_radios_de_modelo_ni_proveedor(home: str) -> None:
    """Solo queda el radio de la plantilla para proveedores dados de alta.

    Ese radio nace marcado `disabled` porque la verificación real es backend
    pendiente; no es un dato de ejemplo.
    """
    codigo = _sin_comentarios(home)
    assert 'type="radio" name="zix-model"' not in codigo
    lineas = [ln for ln in codigo.splitlines() if 'type="radio"' in ln]
    for linea in lineas:
        assert "name=\"zix-provider\"" in linea, linea.strip()
        assert "disabled" in linea, "el radio de la plantilla va deshabilitado"
    assert "checked" not in "".join(lineas), "ningún proveedor nace marcado"


def test_no_hay_chats_de_ejemplo(home: str) -> None:
    """Los chats recientes no pueden tener filas de ejemplo."""
    inicio = home.index('data-od-id="home-recent"')
    fin = home.index('<div class="section"', inicio + 10)
    seccion = home[inicio:fin]
    assert "data-open-chat" not in seccion
    assert "row-label" not in seccion
    assert "Aún no hay chats." in seccion


def test_el_js_no_fabrica_modelo_ni_proveedor(home: str) -> None:
    codigo = _sin_comentarios(home)
    assert "MODEL_DEFAULT" not in codigo
    assert "PROVIDER_DEFAULT" not in codigo
    assert "storeGet('zix-model', '')" in codigo
    assert "var MODEL_VACIO = 'Aún no hay un modelo vinculado';" in codigo
    assert "var PROVIDER_VACIO = 'Aún no hay un proveedor vinculado';" in codigo


def test_los_textos_vacios_se_inyectan_en_las_filas(home: str) -> None:
    codigo = _sin_comentarios(home)
    assert "[data-model-sub]" in codigo
    assert "MODEL_VACIO" in codigo
    assert "PROVIDER_VACIO" in codigo
    assert 'data-model-sub>Aún no hay un modelo vinculado' in home
    assert "Aún no hay un proveedor vinculado" in home


# ───────────────────────── estados vacíos presentes ─────────────────────


def test_chats_recientes_esta_vacio(home: str) -> None:
    assert 'data-od-id="recent-empty"' in home
    assert "Aún no hay chats." in home


def test_modelos_esta_vacio(home: str) -> None:
    assert 'data-od-id="modelos-empty"' in home
    assert "Aún no hay un modelo vinculado." in home


def test_proveedores_esta_vacio(home: str) -> None:
    assert 'id="provider-empty"' in home
    assert "Aún no hay un proveedor vinculado." in home


def test_el_vacio_de_proveedores_se_muestra_solo_si_no_hay_lista(home: str) -> None:
    codigo = _sin_comentarios(home)
    assert "var providerEmptyEl = document.getElementById('provider-empty');" in codigo
    assert (
        "providerEmptyEl.classList.toggle('hidden', providerList.children.length > 0)"
        in codigo
    ), "el vacío se oculta cuando hay proveedores dados de alta"


def test_recursos_pasa_a_describir_los_mcp(home: str) -> None:
    assert "4 de 4" not in home
    fila = home[home.index('data-od-id="state-recursos"') :][:220]
    assert "Servidores MCP" in fila
    assert "0 conectados" in fila


def test_se_reutiliza_el_componente_empty_del_diseno(home: str) -> None:
    """.empty ya existe en el diseño: no se crea un componente nuevo."""
    assert re.search(r"\.empty\s*\{", home), "debe existir el componente .empty"
    for oid in ("recent-empty", "modelos-empty", "proveedores-empty", "mcp-empty", "cmd-empty"):
        assert f'data-od-id="{oid}"' in home, oid
        assert f'class="empty' in home  # al menos una vez


def test_no_se_inventan_estados_que_no_existen_en_el_diseno(home: str) -> None:
    """Sin estado de 'cargando' ni de error: no hay backend que los produzca."""
    for inventado in ("Cargando chats", "Error al cargar", "Reintentando", "No se pudo conectar"):
        assert inventado not in home


# ───────────────────── el Hub usa servidores MCP reales ─────────────────


def test_el_hub_conserva_las_cuatro_recomendaciones(home: str) -> None:
    for oid in (
        "hub-filesystem",
        "hub-github",
        "hub-postgres",
        "hub-playwright",
    ):
        assert f'data-od-id="{oid}"' in home, oid
    assert len(re.findall(r'data-od-id="hub-', home)) == 4


def test_los_paquetes_del_hub_son_reales(home: str) -> None:
    """Paquetes verificados contra npm: nada de paquetes inventados."""
    codigo = _sin_comentarios(home)
    assert "@modelcontextprotocol/server-filesystem" in codigo
    assert "@modelcontextprotocol/server-github" in codigo
    assert "@modelcontextprotocol/server-postgres" in codigo
    assert "@playwright/mcp" in codigo
    # Este paquete NO existe: el oficial de Playwright es @playwright/mcp.
    # Solo puede mencionarse en un comentario que explique la decisión.
    assert "@modelcontextprotocol/server-playwright" not in codigo


def test_los_credenciales_usan_los_nombres_correctos(home: str) -> None:
    assert "GITHUB_PERSONAL_ACCESS_TOKEN" in home
    assert "GITHUB_TOKEN: ''" not in home, "el oficial exige GITHUB_PERSONAL_ACCESS_TOKEN"


def test_postgres_recibe_la_url_como_argumento(home: str) -> None:
    postgres = home[home.index("name: 'PostgreSQL'") :][:400]
    assert "postgresql://localhost/mydb" in postgres
    assert "POSTGRES_URL" not in postgres, "la URL va como argumento, no como env"


def test_los_comandos_npx_llevan_el_envoltorio_de_windows(home: str) -> None:
    """ZIX corre en Windows: npx necesita el envoltorio cmd /c."""
    catalogo = home[home.index("var MCP_HUB = [") : home.index("var mcpListEl")]
    comandos = re.findall(r"command: '([^']+)'", catalogo)
    assert comandos, "debe haber comandos en el catálogo"
    assert set(comandos) == {"cmd"}, f"se esperaba cmd en Windows, hay {set(comandos)}"
    assert catalogo.count("'/c', 'npx'") == len(comandos)


def test_integrar_sigue_deshabilitado(home: str) -> None:
    linea = home[home.index('id="btn-mcp-integrate"') :]
    linea = linea[: linea.index(">")]
    assert "disabled" in linea


def test_no_se_declaran_mcp_conectados(home: str) -> None:
    """El único conteo de MCPs es cero; "Conectado" solo describe la red."""
    assert "0 conectados" in home
    for afirmacion in ("1 conectados", "2 conectados", "3 conectados", "4 conectados"):
        assert afirmacion not in home
    conexion = home[home.index('data-od-id="state-conexion"') :][:200]
    assert "Conectado" in conexion, "el estado de red sigue presente (navigator.onLine)"


# ───────────────────────────── navegación ───────────────────────────────


def test_la_navegacion_a_chat_sigue_pendiente(home: str) -> None:
    """Chat ya esta implementado, pero la guarda se mantiene por si acaso."""
    assert "var PANTALLAS = { chat: 'zix-main.html' }" in home
    assert "var PANTALLAS_IMPLEMENTADAS = ['zix-main.html']" in home
    assert "if (!screenReady(PANTALLAS.chat)) return;" in home
