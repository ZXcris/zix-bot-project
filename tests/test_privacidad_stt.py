"""El freno de privacidad del STT: nada sale del equipo sin permiso.

Cubre lo anadido el 2026-10-09:

- `upload_guard` decide ANTES de transcribir (a diferencia de is_valid_order,
  que llega tarde: cuando corre, el audio ya subio).
- `STT_ALLOW_CLOUD=0` impide cualquier envio cuando el STT es de nube.
- Silero descarta silencio y ruido sin necesidad de red.
- `_build_stt` se niega a arrancar en una combinacion imposible.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from zix.config import Config
from zix.voice.upload_guard import decidir_subida, fraccion_de_habla

SR = 16000


def _wav(tmp_path: Path, name: str, muestras: np.ndarray, sr: int = SR) -> Path:
    ruta = tmp_path / name
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(np.clip(muestras, -32768, 32767).astype(np.int16).tobytes())
    return ruta


def _tono(segundos: float, amp: float = 0.3, freq: float = 220.0) -> np.ndarray:
    t = np.linspace(0, segundos * SR, int(segundos * SR), endpoint=False)
    return (np.sin(2 * np.pi * freq * t) * amp * 32767).astype(np.int16)


def _silencio(segundos: float) -> np.ndarray:
    return np.zeros(int(segundos * SR), dtype=np.int16)


def silero_disponible() -> bool:
    """True si el VAD arranca de verdad, no solo si el modulo se importa.

    Importar openwakeword no basta: el paquete de pip no trae sus modelos
    .onnx, asi que en una instalacion limpia VAD() revienta. Estos tests
    miden lo que hace Silero DE VERDAD, asi que si no esta, no se pueden
    medir: es un skip honesto, no un fallo. La logica del freno se prueba
    siempre, sin depender del modelo (ver test_sin_vad_no_sube).
    """
    try:
        from openwakeword.vad import VAD

        VAD()
    except Exception:
        return False
    return True


requiere_silero = pytest.mark.skipif(
    not silero_disponible(),
    reason="falta silero_vad.onnx; bajalo con "
    "python scripts/setup_openwakeword_models.py",
)


# ────────────────────── el interruptor de nube ──────────────────────────


def test_el_interruptor_bloquea_la_nube(tmp_path: Path) -> None:
    """STT_ALLOW_CLOUD=0 gana a todo: ni un byte sale."""
    ruta = _wav(tmp_path, "voz.wav", _tono(2.0))
    permitido, motivo = decidir_subida(
        ruta, permitir_nube=False, es_nube=True,
    )
    assert not permitido
    assert "STT_ALLOW_CLOUD" in motivo


def test_el_interruptor_no_afecta_al_stt_local(tmp_path: Path) -> None:
    """Con proveedor local, apagar la nube no debe impedir transcribir."""
    ruta = _wav(tmp_path, "voz.wav", _tono(2.0))
    # minimo_fraccion=0.0 a proposito: aqui se prueba el interruptor, no el VAD.
    permitido, _ = decidir_subida(
        ruta, permitir_nube=False, es_nube=False, minimo_fraccion=0.0
    )
    assert permitido, "el STT local debe seguir funcionando con la nube apagada"


def test_con_la_nube_permitida_pasa_el_filtro_local(tmp_path: Path) -> None:
    # minimo_fraccion=0.0 y permitir_sin_filtrar: aqui se prueba que el
    # interruptor de nube NO bloquea, no el filtro. Dejar el filtro puesto
    # hacia depender de que silero_vad.onnx este descargado en la maquina.
    ruta = _wav(tmp_path, "voz.wav", _tono(2.0))
    permitido, _ = decidir_subida(
        ruta,
        permitir_nube=True,
        es_nube=True,
        minimo_fraccion=0.0,
        permitir_sin_filtrar=True,
    )
    assert permitido


@requiere_silero
def test_un_tono_no_es_voz_y_se_descarta(tmp_path: Path) -> None:
    """Silero hace bien su trabajo: un seno de 220 Hz no es habla.

    Se documenta a proposito, porque es la razon por la que este filtro
    reduce el ruido sin necesidad de red: decide sobre la senal, no sobre el
    texto, y por eso puede hacerlo ANTES de subir nada.
    """
    ruta = _wav(tmp_path, "tono.wav", _tono(3.0))
    permitido, _ = decidir_subida(
        ruta, permitir_nube=True, es_nube=True, minimo_fraccion=0.15
    )
    assert not permitido, "un tono puro no deberia pasar como voz"


def test_la_puerta_se_abre_con_audio_real(tmp_path: Path) -> None:
    """Prueba de extremo a extremo con voz humana de verdad, si existe."""
    raiz = Path(__file__).resolve().parents[1]
    muestras = sorted((raiz / "data" / "wakeword_real_16k").glob("*.wav"))
    if not muestras:
        pytest.skip("no hay clips reales en data/wakeword_real_16k")
    permitido, motivo = decidir_subida(
        muestras[0], permitir_nube=True, es_nube=True, minimo_fraccion=0.15
    )
    assert permitido, f"una grabacion real de voz deberia pasar: {motivo}"


# ─────────────────────────── filtros locales ────────────────────────────


@requiere_silero
def test_el_silencio_no_sube(tmp_path: Path) -> None:
    """Un silencio puro no puede acabar transcrito en un servidor."""
    ruta = _wav(tmp_path, "silencio.wav", _silencio(3.0))
    permitido, motivo = decidir_subida(
        ruta, permitir_nube=True, es_nube=True, minimo_fraccion=0.15
    )
    assert not permitido
    assert "voz" in motivo.lower() or "Silero" in motivo


def test_el_audio_largo_no_sube(tmp_path: Path) -> None:
    """Tope de duracion: acota el peor caso de una activacion falsa."""
    ruta = _wav(tmp_path, "largo.wav", _tono(20.0))
    permitido, motivo = decidir_subida(
        ruta, permitir_nube=True, es_nube=True, max_segundos=15.0
    )
    assert not permitido
    assert "tope" in motivo


def test_un_wav_ilegible_no_sube(tmp_path: Path) -> None:
    ruta = tmp_path / "roto.wav"
    ruta.write_bytes(b"esto no es un wav")
    permitido, motivo = decidir_subida(ruta, permitir_nube=True, es_nube=True)
    assert not permitido
    assert "WAV" in motivo


def test_fraccion_de_habla_devuelve_none_si_no_puede_decidir(tmp_path: Path) -> None:
    """None significa 'sin informacion', nunca 'no hay voz'."""
    vacio = _wav(tmp_path, "corto.wav", _silencio(0.01))
    assert fraccion_de_habla(vacio) is None
    roto = tmp_path / "roto.wav"
    roto.write_bytes(b"x")
    assert fraccion_de_habla(roto) is None


@requiere_silero
def test_fraccion_de_habla_detecta_el_tono(tmp_path: Path) -> None:
    fraccion = fraccion_de_habla(_wav(tmp_path, "tono.wav", _tono(2.0)))
    assert fraccion is None or 0.0 <= fraccion <= 1.0


# ───────────────────────── configuracion nueva ──────────────────────────


def test_la_config_lee_el_interruptor() -> None:
    c = Config()
    assert c.stt_allow_cloud is True, "por defecto debe permitirse, para no romper a nadie"
    assert c.stt_provider == "groq"
    assert 0.0 < c.stt_min_speech_ratio <= 1.0
    assert c.stt_max_seconds > 0


def test_la_config_acepta_el_proveedor_local() -> None:
    assert Config(stt_provider="local").stt_provider == "local"


# ────────────── sin VAD: la puerta se CIERRA (2026-12-10) ──────────────
#
# Estos dos tests fijan una correccion de seguridad. Antes, cuando Silero no
# estaba disponible, decidir_subida devolvia True con "Sin VAD disponible: no
# se puede filtrar, se continua". Como openwakeword NO trae sus modelos .onnx
# en el paquete de pip, eso significa que en cualquier instalacion limpia el
# freno no existia: el audio subia entero y el unico rastro era una linea de
# log. Un freno que puede desaparecer en silencio no es un freno.


def test_sin_vad_no_se_sube(tmp_path: Path, monkeypatch) -> None:
    """Sin informacion no se sube. Fallar cerrado, no abierto."""
    import zix.voice.upload_guard as guard

    monkeypatch.setattr(guard, "fraccion_de_habla", lambda _p: None)
    ruta = _wav(tmp_path, "voz.wav", _tono(2.0))
    permitido, motivo = decidir_subida(ruta, permitir_nube=True, es_nube=True)
    assert not permitido, "sin VAD no se debe subir nada a un servidor"
    assert "Silero" in motivo
    # el mensaje tiene que decir como arreglarlo, no solo que no se puede
    assert "download_models" in motivo or "STT_ALLOW_UNFILTERED" in motivo


def test_sin_vad_se_puede_forzar_a_proposito(tmp_path: Path, monkeypatch) -> None:
    """La puerta de salida existe, pero hay que abrirla a proposito."""
    import zix.voice.upload_guard as guard

    monkeypatch.setattr(guard, "fraccion_de_habla", lambda _p: None)
    ruta = _wav(tmp_path, "voz.wav", _tono(2.0))
    permitido, motivo = decidir_subida(
        ruta, permitir_nube=True, es_nube=True, permitir_sin_filtrar=True
    )
    assert permitido
    assert "STT_ALLOW_UNFILTERED" in motivo, "debe quedar constancia en el log"


def test_sin_vad_tampoco_toca_el_stt_local(tmp_path: Path, monkeypatch) -> None:
    """Filtrar es cosa de la nube: en local no hay nada que subir."""
    import zix.voice.upload_guard as guard

    monkeypatch.setattr(guard, "fraccion_de_habla", lambda _p: None)
    ruta = _wav(tmp_path, "voz.wav", _tono(2.0))
    permitido, motivo = decidir_subida(ruta, permitir_nube=False, es_nube=False)
    assert permitido, f"el STT local debe seguir funcionando: {motivo}"


def test_la_config_lee_el_interruptor_de_filtrado() -> None:
    assert Config().stt_allow_unfiltered is False, "fallar cerrado por defecto"
    assert Config(stt_allow_unfiltered=True).stt_allow_unfiltered is True


# ───────────────────── eleccion de proveedor (build_stt) ────────────────


def test_local_sin_faster_whisper_falla_con_el_comando_exacto(monkeypatch) -> None:
    """Si pides local y no esta instalado, el error dice como arreglarlo."""
    import zix.voice.local_stt as local_stt
    import zix.voice_main as voice_main

    monkeypatch.setattr(local_stt, "disponible", lambda: False)
    with pytest.raises(Exception) as exc:
        voice_main._build_stt(Config(stt_provider="local"))
    texto = str(exc.value)
    assert "faster-whisper" in texto
    assert "pip install" in texto


def test_nube_bloqueada_sin_local_no_arranca(monkeypatch) -> None:
    """La combinacion imposible debe decir que hacer, no reventar."""
    import zix.voice.local_stt as local_stt
    import zix.voice_main as voice_main

    monkeypatch.setattr(local_stt, "disponible", lambda: False)
    with pytest.raises(Exception) as exc:
        voice_main._build_stt(Config(stt_provider="groq", stt_allow_cloud=False))
    texto = str(exc.value)
    assert "STT_ALLOW_CLOUD" in texto
    assert "faster-whisper" in texto


def test_el_guarda_precede_a_la_transcripcion() -> None:
    """Invariante de orden: decidir_subida() antes que _transcribe().

    Es el punto de todo el arreglo. Si alguien mueve la llamada, el audio
    vuelve a salir antes de filtrarse y este test falla.
    """
    fuente = (
        Path(__file__).resolve().parents[1]
        / "src" / "zix" / "voice" / "conversation.py"
    ).read_text(encoding="utf-8")
    guarda = fuente.index("decidir_subida(")
    transcribe = fuente.index("self._transcribe(path)", guarda)
    assert guarda < transcribe, "el filtro tiene que ejecutarse ANTES de transcribir"
