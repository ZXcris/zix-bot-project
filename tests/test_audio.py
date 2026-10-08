"""Tests de lectura/escritura de WAV y conversión de muestras (sin hardware)."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np
import pytest

from zix.voice.audio import AudioError, AudioManager, _StreamResampler


def test_to_int16_clips_and_scales(tmp_path):
    samples = np.array([-1.0, 0.0, 1.0, 2.0, -2.0], dtype=np.float32)
    pcm = AudioManager.to_int16(samples)
    assert pcm.tolist() == [-32767, 0, 32767, 32767, -32768]
    assert pcm.dtype == np.int16


def test_write_read_roundtrip(tmp_path):
    path = tmp_path / "prueba.wav"
    sr = 16000
    t = np.arange(sr, dtype=np.float32) / sr
    samples = 0.25 * np.sin(2 * np.pi * 440 * t)

    AudioManager.write_wav(path, samples, sr)
    assert path.exists()

    read_sr, read = AudioManager.read_wav(path)
    assert read_sr == sr
    assert read.shape == samples.shape
    np.testing.assert_allclose(read, samples, atol=1 / 32767.0)


def test_write_wav_int16_input(tmp_path):
    path = tmp_path / "int16.wav"
    pcm = np.array([0, 1000, -1000], dtype=np.int16)
    AudioManager.write_wav(path, pcm, 16000)
    _sr, read = AudioManager.read_wav(path)
    np.testing.assert_allclose(read, pcm / 32767.0, atol=1 / 32767.0)


def test_read_missing_file_raises(tmp_path):
    with pytest.raises(AudioError):
        AudioManager.read_wav(tmp_path / "no_existe.wav")


def test_audio_manager_validates_args():
    with pytest.raises(ValueError):
        AudioManager(samplerate=0)
    with pytest.raises(ValueError):
        AudioManager(block_size=0)


def test_iter_input_blocks_records_native_diagnostics(monkeypatch):
    samples = np.full(1280, 0.25, dtype=np.float32)
    callback_records = []

    class FakeInputStream:
        raw_input_dtype = np.dtype("float32")

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self, frames):
            return samples[:frames], False

    class FakePortAudioError(Exception):
        pass

    fake_sounddevice = SimpleNamespace(
        query_devices=lambda: [],
        query_hostapis=lambda: [],
        InputStream=FakeInputStream,
        PortAudioError=FakePortAudioError,
    )
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sounddevice)

    def record(*values):
        callback_records.append(values)

    manager = AudioManager(
        samplerate=16000,
        block_size=1280,
        on_native_block=record,
    )
    block = next(manager.iter_input_blocks())

    assert block.dtype == np.float32
    assert block.shape == (1280,)
    assert manager.active_input_device is None
    assert manager.active_input_samplerate == 16000
    assert manager.active_input_channels == 1
    assert manager.active_input_dtype == "float32"
    assert manager.active_input_frame_size == 1280
    assert manager.last_input_overflow is False
    assert len(callback_records) == 1
    callback_samples, callback_rate, callback_channels, callback_frame, callback_overflow = callback_records[0]
    np.testing.assert_array_equal(callback_samples, samples)
    assert callback_rate == 16000
    assert callback_channels == 1
    assert callback_frame == 1280
    assert callback_overflow is False


# ----------------------------------------------------------------------
# _StreamResampler
# ----------------------------------------------------------------------

SR_IN, SR_OUT, K = 48000, 16000, 3


def _tone(freq: float, sr: int, seconds: float, amp: float = 1.0) -> np.ndarray:
    t = np.arange(int(sr * seconds), dtype=np.float32) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_resampler_passthrough():
    r = _StreamResampler(16000, 16000)
    x = _tone(440, 16000, 0.5)
    y = r.process(x)
    np.testing.assert_array_equal(y, x)


def test_resampler_integer_decimation_length_and_freq():
    r = _StreamResampler(SR_IN, SR_OUT)
    x = _tone(1000, SR_IN, 1.0)
    y = r.process(x)
    n = r._kernel.shape[0]
    assert len(y) == (len(x) - (n - 1)) // K
    delay = (n // 2) / SR_IN  # retardo de grupo del FIR
    t_out = np.arange(len(y)) / SR_OUT
    expected = np.sin(2 * np.pi * 1000.0 * (t_out - delay))
    np.testing.assert_allclose(y[200:], expected[200:], atol=0.03)


def test_resampler_dc_gain_one():
    r = _StreamResampler(SR_IN, SR_OUT)
    y = r.process(np.full(3 * 400, 0.5, dtype=np.float32))
    np.testing.assert_allclose(y, np.full(len(y), 0.5), atol=1e-5)


def test_resampler_suppresses_high_frequencies():
    r = _StreamResampler(SR_IN, SR_OUT)
    x = _tone(12000, SR_IN, 1.0)  # por encima del Nyquist de salida (8 kHz)
    y = r.process(x)
    assert float(np.max(np.abs(y))) < 0.05


def test_resampler_chunk_continuity_matches_oneshot():
    r1 = _StreamResampler(SR_IN, SR_OUT)
    r2 = _StreamResampler(SR_IN, SR_OUT)
    x = _tone(1000, SR_IN, 1.0)
    y = r1.process(x)
    chunks = [x[i : i + 3 * 1280] for i in range(0, len(x), 3 * 1280)]
    ys = [r2.process(c) for c in chunks]
    np.testing.assert_allclose(np.concatenate(ys), y, atol=1e-6)


def test_resampler_chunk_must_be_multiple_of_factor():
    r = _StreamResampler(SR_IN, SR_OUT)
    with pytest.raises(ValueError):
        r.process(np.zeros(100, dtype=np.float32))


def test_resampler_linear_fallback_continuity():
    sr_in, sr_out = 22050, 16000
    r1 = _StreamResampler(sr_in, sr_out)
    r2 = _StreamResampler(sr_in, sr_out)
    x = _tone(440, sr_in, 1.0)
    y = r1.process(x)
    assert len(y) == round(len(x) * sr_out / sr_in)
    chunks = np.array_split(x, 7)
    ys = [r2.process(c) for c in chunks]
    np.testing.assert_allclose(np.concatenate(ys), y, atol=1e-5)


def test_resampler_linear_fallback_preserves_signal():
    sr_in, sr_out = 22050, 16000
    r = _StreamResampler(sr_in, sr_out)
    x = _tone(440, sr_in, 1.0)
    y = r.process(x)
    assert float(np.sqrt(np.mean(y**2))) > 0.5


# ----------------------------------------------------------------------
# resolve_input_device (sin hardware)
# ----------------------------------------------------------------------


def _devices_and_hostapis():
    hostapis = [
        {"name": "Windows WDM-KS"},
        {"name": "Windows DirectSound"},
        {"name": "Windows WASAPI"},
        {"name": "MME"},
    ]
    devices = [
        {"name": "Altavoces (Realtek(R) Audio)", "hostapi": 1, "max_input_channels": 0, "default_samplerate": 44100},
        {"name": "Microphone (Realtek(R) Audio)", "hostapi": 3, "max_input_channels": 1, "default_samplerate": 44100},
        {"name": "Microphone Array (Realtek(R) Audio)", "hostapi": 3, "max_input_channels": 2, "default_samplerate": 48000},
        {"name": "Microphone Array (Realtek(R) Audio)", "hostapi": 1, "max_input_channels": 2, "default_samplerate": 44100},
        {"name": "Microphone Array (Realtek(R) Audio)", "hostapi": 2, "max_input_channels": 2, "default_samplerate": 48000},
        {"name": "Array de prueba A", "hostapi": 1, "max_input_channels": 1, "default_samplerate": 16000},
        {"name": "Array de prueba B", "hostapi": 3, "max_input_channels": 1, "default_samplerate": 16000},
    ]
    return devices, hostapis


def test_resolve_device_by_index():
    devices, hostapis = _devices_and_hostapis()
    assert AudioManager.resolve_input_device(2, devices, hostapis) == 2
    assert AudioManager.resolve_input_device("3", devices, hostapis) == 3


def test_resolve_device_by_exact_name():
    devices, hostapis = _devices_and_hostapis()
    idx = AudioManager.resolve_input_device("Microphone (Realtek(R) Audio)", devices, hostapis)
    assert idx == 1


def test_resolve_device_substring_unique():
    devices, hostapis = _devices_and_hostapis()
    assert AudioManager.resolve_input_device("Microphone (Realtek", devices, hostapis) == 1


def test_resolve_device_substring_prefers_wasapi():
    devices, hostapis = _devices_and_hostapis()
    idx = AudioManager.resolve_input_device("Microphone Array (Realtek(R) Audio)", devices, hostapis)
    assert idx == 4  # el de WASAPI (hostapi 2)


def test_resolve_device_ambiguous_raises():
    devices, hostapis = _devices_and_hostapis()
    with pytest.raises(AudioError, match="ambiguo"):
        AudioManager.resolve_input_device("Array de prueba", devices, hostapis)


def test_resolve_device_no_match_raises():
    devices, hostapis = _devices_and_hostapis()
    with pytest.raises(AudioError, match="No hay dispositivo"):
        AudioManager.resolve_input_device("No existe tal micrófono", devices, hostapis)


def test_resolve_device_not_input_raises():
    devices, hostapis = _devices_and_hostapis()
    with pytest.raises(AudioError, match="no es un dispositivo de entrada"):
        AudioManager.resolve_input_device(0, devices, hostapis)
    with pytest.raises(AudioError, match="no es un dispositivo de entrada"):
        AudioManager.resolve_input_device(99, devices, hostapis)


def test_resolve_device_empty_raises():
    devices, hostapis = _devices_and_hostapis()
    with pytest.raises(AudioError):
        AudioManager.resolve_input_device("   ", devices, hostapis)