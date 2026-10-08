"""Tests del VAD por energía RMS (sin hardware ni red)."""
from __future__ import annotations

import numpy as np
import pytest

from zix.voice.vad import VAD


def test_rms_of_silence_is_zero():
    assert VAD.rms(np.zeros(1280, dtype=np.float32)) == 0.0


def test_rms_of_constant_signal():
    signal = np.full(1280, 0.1, dtype=np.float32)
    assert VAD.rms(signal) == pytest.approx(0.1)


def test_rms_of_sine():
    t = np.arange(1280, dtype=np.float32) / 16000.0
    sine = 0.5 * np.sin(2 * np.pi * 440 * t)
    assert VAD.rms(sine) == pytest.approx(0.5 / np.sqrt(2), rel=0.01)


def test_rms_of_empty_and_none():
    assert VAD.rms(np.array([], dtype=np.float32)) == 0.0
    assert VAD.rms(None) == 0.0


def test_is_speech_above_threshold():
    vad = VAD(threshold=0.02)
    assert vad.is_speech(np.full(1280, 0.1, dtype=np.float32))
    # 0.03125 = 2^-5 es exacto en float32 y queda por encima de 0.02
    assert vad.is_speech(np.full(1280, 0.03125, dtype=np.float32))
    assert not vad.is_speech(np.full(1280, 0.01, dtype=np.float32))


def test_negative_threshold_rejected():
    with pytest.raises(ValueError):
        VAD(threshold=-0.1)