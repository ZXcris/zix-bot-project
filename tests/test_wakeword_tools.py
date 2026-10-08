"""Tests de las herramientas de wake word (scripts opt-in de entrenamiento).

Cubren la logica pura y la proteccion anti-entrenamiento. No abren el
microfono, no cargan zix.onnx y no tocan .env ni models/.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPTS = RAIZ / "scripts" / "wakeword_training"
sys.path.insert(0, str(SCRIPTS))

import _audio_utils as au  # noqa: E402
import grabar_clips  # noqa: E402
import verify_heldout  # noqa: E402


# ───────────────────────────  _audio_utils  ───────────────────────────


def test_to_int16_escala_a_rango_pcm() -> None:
    salida = au.to_int16(np.array([0.0, 1.0, -1.0, 0.5], dtype=np.float32))
    assert salida.dtype == np.int16
    assert salida[0] == 0
    assert salida[1] == 32767
    assert salida[2] == -32767
    assert salida[3] == pytest.approx(16383, abs=2)


def test_to_int16_recorta_en_vez_de_ponerla() -> None:
    """Un microfono que se pasa de rango no debe dar la vuelta al signo."""
    salida = au.to_int16(np.array([3.0, -3.0], dtype=np.float32))
    assert salida[0] == 32767
    assert salida[1] == -32768


def test_downmix_hace_media_de_canales() -> None:
    stereo = np.array([[1.0, 0.0], [0.5, 0.5]], dtype=np.float32)
    mono = au.downsample(stereo)
    assert mono.shape == (2,)
    assert mono[0] == pytest.approx(0.5)
    assert mono[1] == pytest.approx(0.5)


def test_downmix_acepta_mono_sin_tocarlo() -> None:
    mono = np.array([0.1, -0.2], dtype=np.float32)
    assert np.array_equal(au.downsample(mono), mono)


def test_medir_devuelve_duracion_rms_y_pico() -> None:
    # 3200 muestras a 16 kHz = 0.2 s
    x = np.ones(3200, dtype=np.float32) * 0.5
    dur, rms, pico = au.medir(x)
    assert dur == pytest.approx(0.2)
    assert rms == pytest.approx(0.5, abs=1e-4)
    assert pico == pytest.approx(0.5, abs=1e-4)


def test_medir_no_revienta_con_audio_vacio() -> None:
    assert au.medir(np.array([], dtype=np.float32)) == (0.0, 0.0, 0.0)


def test_ida_y_vuelta_wav_conserva_la_señal(tmp_path: Path) -> None:
    original = np.sin(np.linspace(0, 40, 4000)).astype(np.float32) * 0.4
    ruta = tmp_path / "prueba.wav"
    au.save_wav(ruta, original)
    sr, recuperado = au.load_wav(ruta)
    assert sr == au.SR_OBJETIVO
    assert len(recuperado) == len(original)
    # la cuantizacion a int16 es la unica perdida tolerada
    assert np.max(np.abs(recuperado - original)) < 1e-4


def test_resample_ajusta_la_longitud() -> None:
    x = np.zeros(4800, dtype=np.float32)  # 0.1 s a 48 kHz
    salida = au.resample(x, 48000, 16000)
    assert len(salida) == pytest.approx(1600, abs=2)


def test_resample_es_passthrough_si_ya_es_16k() -> None:
    x = np.linspace(-1, 1, 100, dtype=np.float32)
    assert au.resample(x, 16000, 16000) is x


def test_speech_fraction_no_falla_con_audio_corto() -> None:
    assert au.speech_fraction(np.zeros(100, dtype=np.int16)) == 0.0


def test_speech_fraction_devuelve_una_proporcion() -> None:
    x = (np.sin(np.linspace(0, 300, 16000)) * 0.3 * 32767).astype(np.int16)
    valor = au.speech_fraction(x)
    assert 0.0 <= valor <= 1.0


# ─────────────────────  grabar_clips: cobertura  ──────────────────────


def test_siguiente_condicion_empieza_por_la_mas_barata() -> None:
    cond, cuantos = grabar_clips.siguiente_condicion([])
    assert cond == ("cerca", "cuarto", "silencio")
    assert cuantos == 0


def test_siguiente_condicion_rota_tras_cubrir_una() -> None:
    hechos = [f"heyzix_cristian_cuarto-cerca-silencio_{i:02d}.wav" for i in range(1, 4)]
    cond, cuantos = grabar_clips.siguiente_condicion(hechos)
    assert cond != ("cerca", "cuarto", "silencio")
    assert cuantos == 0


def test_siguiente_condicion_cuenta_los_existentes() -> None:
    """Cubriendo todo por igual, recomienda la primera e informa cuantos hay."""
    hechos = [
        f"heyzix_cristian_{lugar}-{dist}-{fondo}_01.wav"
        for dist, lugar, fondo in grabar_clips.CONDICIONES
    ]
    cond, cuantos = grabar_clips.siguiente_condicion(hechos)
    assert cond == ("cerca", "cuarto", "silencio")
    assert cuantos == 1


def test_siguiente_condicion_busca_la_no_cubierta() -> None:
    """Con todas menos una cubiertas, debe pedir exactamente la que falta."""
    hechos = [
        f"heyzix_cristian_{lugar}-{dist}-{fondo}_01.wav"
        for dist, lugar, fondo in grabar_clips.CONDICIONES[:-1]
    ]
    cond, cuantos = grabar_clips.siguiente_condicion(hechos)
    assert cond == grabar_clips.CONDICIONES[-1]
    assert cuantos == 0


def test_siguiente_condicion_ignora_nombres_ajenos() -> None:
    cond, cuantos = grabar_clips.siguiente_condicion(["nota.wav", "respuesta_0001.wav"])
    assert cond == ("cerca", "cuarto", "silencio")
    assert cuantos == 0


def test_la_matriz_de_condicion_es_variada() -> None:
    """Un dataset sin variedad no arregla nada: lo comprobamos aqui."""
    lugares = {l for _, l, _ in grabar_clips.CONDICIONES}
    fondos = {f for _, _, f in grabar_clips.CONDICIONES}
    assert len(lugares) >= 3
    assert fondos == {"silencio", "musica", "ruido"}


# ─────────────────  verify_heldout: decision de umbral  ───────────────


def test_mejor_umbral_propone_el_corte_con_margen() -> None:
    """Debe caer entre el negativo mas alto y el positivo mas bajo, no pegarse a uno."""
    pos, neg = [0.9, 0.8, 0.75], [0.01, 0.02, 0.0]
    umbral, motivo = verify_heldout.mejor_umbral(pos, neg)
    assert umbral is not None
    assert max(neg) < umbral < min(pos), f"{umbral} no queda en el margen"
    assert "margen" in motivo


def test_mejor_umbral_avisa_si_no_se_puede_separar() -> None:
    """El caso real de hoy: positivos y negativos solapados."""
    umbral, motivo = verify_heldout.mejor_umbral([0.001, 0.002], [0.0005, 0.001])
    assert umbral is None
    assert "solapamiento" in motivo


def test_mejor_umbral_sin_negativos_usa_el_defecto() -> None:
    assert verify_heldout.mejor_umbral([0.9], [])[0] == 0.5


def test_mejor_umbral_sin_positivos_no_inventa() -> None:
    assert verify_heldout.mejor_umbral([], [0.1])[0] is None


def test_barrer_ignora_fragmentos_mas_cortos_que_un_bloque() -> None:
    assert verify_heldout.barrer(np.zeros(100, dtype=np.int16), lambda x: 1.0) == 0.0


def test_barrer_toma_el_maximo_de_los_bloques() -> None:
    audio = np.zeros(1280 * 5, dtype=np.int16)
    llamadas: list[int] = []

    def proceso(bloque: np.ndarray) -> float:
        llamadas.append(len(bloque))
        return 0.9 if len(llamadas) == 3 else 0.1

    assert verify_heldout.barrer(audio, proceso) == 0.9
    assert llamadas == [1280] * 5


# ─────────────  proteccion: nunca puntuar clips de entrenamiento  ─────


@pytest.mark.parametrize("ruta", ["zix_model/positive/train", "C:/tmp/zix_model/positive/train"])
def test_el_verificador_rechaza_carpetas_de_entrenamiento(ruta: str) -> None:
    """Debe plantarse ANTES de cargar el modelo, con codigo de salida 1."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "verify_heldout.py"), ruta],
        capture_output=True, text=True, cwd=str(RAIZ), timeout=120,
    )
    assert proc.returncode == 1
    salida = proc.stdout + proc.stderr
    assert "ENTRENAMIENTO" in salida.upper()
    assert "zix.onnx" not in salida  # no debe haber llegado a cargar el modelo


def test_el_verificador_no_toca_env_ni_models() -> None:
    fuente = (SCRIPTS / "verify_heldout.py").read_text(encoding="utf-8")
    assert "write_text" not in fuente
    assert "shutil.rmtree" not in fuente


def test_el_grabador_no_toca_env_ni_models() -> None:
    fuente = (SCRIPTS / "grabar_clips.py").read_text(encoding="utf-8")
    assert "write_text" not in fuente
    assert "shutil.rmtree" not in fuente
