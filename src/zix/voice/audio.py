"""Gestión de audio: captura del micrófono y reproducción con sounddevice.

La lectura/escritura de WAV usa solo la stdlib (`wave` + numpy) para que sea
probable sin hardware y sin sounddevice.
"""
from __future__ import annotations

import wave
from pathlib import Path
from typing import Callable, Iterator

import numpy as np


class AudioError(Exception):
    """Error de audio (dispositivo, formato, reproducción)."""


class _StreamResampler:
    """Convierte un flujo mono float32 de `in_rate` a `out_rate` con estado.

    - `in_rate == out_rate`: passthrough (copia).
    - `in_rate` múltiplo entero de `out_rate` (p. ej. 48000 -> 16000):
      diezmado con FIR (sinc * ventana Hamming) para evitar aliasing.
    - resto: interpolación lineal (fallback simple).
    """

    def __init__(self, in_rate: int, out_rate: int, taps_per_step: int = 16) -> None:
        if in_rate <= 0 or out_rate <= 0:
            raise ValueError("in_rate y out_rate deben ser positivos")
        self.in_rate = in_rate
        self.out_rate = out_rate
        self._taps_per_step = taps_per_step
        self._state = np.zeros(0, dtype=np.float32)
        self._buf = np.zeros(0, dtype=np.float32)
        self._pos = 0.0
        self._kernel: np.ndarray | None = None
        self._factor: int | None = None
        self._ratio: float | None = None
        if in_rate == out_rate:
            return
        if in_rate % out_rate == 0:
            k = in_rate // out_rate
            n = self._taps_per_step * k + 1
            center = n // 2
            x = np.arange(n, dtype=np.float64) - center
            fc = 0.5 / k  # Nyquist de la señal de salida
            kernel = np.sinc(x * fc) * fc * np.hamming(n)
            kernel /= kernel.sum()  # ganancia DC = 1
            self._kernel = kernel.astype(np.float32)
            self._factor = k
        else:
            self._ratio = in_rate / out_rate

    def process(self, chunk: np.ndarray) -> np.ndarray:
        """Consume `chunk` mono float32 y devuelve la salida convertida."""
        chunk = np.asarray(chunk, dtype=np.float32).reshape(-1)
        if self._kernel is None and self._ratio is None:
            return chunk.copy()
        if self._kernel is not None:
            k = self._factor
            n = self._kernel.shape[0]
            if len(chunk) % k != 0:
                raise ValueError(f"el bloque ({len(chunk)}) debe ser múltiplo de {k}")
            combined = np.concatenate([self._state, chunk])
            out_len = (len(combined) - (n - 1)) // k
            if out_len <= 0:
                self._state = combined
                return np.zeros(0, dtype=np.float32)
            windows = np.lib.stride_tricks.sliding_window_view(combined, n)
            out = windows[::k] @ self._kernel
            self._state = combined[-(n - 1) :]
            return out.astype(np.float32)
        # interpolación lineal
        self._buf = np.concatenate([self._buf, chunk])
        out = []
        pos = self._pos
        while True:
            idx = int(pos)
            if idx + 1 >= len(self._buf):
                break
            frac = pos - idx
            out.append(self._buf[idx] * (1.0 - frac) + self._buf[idx + 1] * frac)
            pos += self._ratio
        consumed = int(pos)
        self._buf = self._buf[consumed:]
        self._pos = pos - consumed
        return np.asarray(out, dtype=np.float32)


class AudioManager:
    """Captura bloques del micrófono y reproduce WAVs (sounddevice)."""

    def __init__(
        self,
        samplerate: int = 16000,
        block_size: int = 1280,
        channels: int = 1,
        device: int | str | None = None,
        input_samplerate: int | None = None,
        input_channels: int | None = None,
        on_native_block: Callable[[np.ndarray, int, int, int, bool], None] | None = None,
    ) -> None:
        if samplerate <= 0 or block_size <= 0:
            raise ValueError("samplerate y block_size deben ser positivos")
        self.samplerate = samplerate
        self.block_size = block_size
        self.channels = channels
        # Dispositivo de entrada explícito: índice, nombre (subcadena) o None.
        # Si se configura, se abre con el formato NATIVO del dispositivo
        # (p. ej. WASAPI 48 kHz / 2 canales) y se convierte a samplerate/channels.
        self.device = device
        self.input_samplerate = input_samplerate
        self.input_channels = input_channels
        self._on_native_block = on_native_block
        self.active_input_device: int | None = None
        self.active_input_samplerate: int | None = None
        self.active_input_channels: int | None = None
        self.active_input_dtype: str | None = None
        self.active_input_frame_size: int | None = None
        self.last_input_overflow = False

    @staticmethod
    def resolve_input_device(
        spec: int | str,
        devices: list[dict],
        hostapis: list[dict],
    ) -> int:
        """Resuelve un dispositivo de entrada por índice o nombre (subcadena).

        - `spec` int: índice (debe existir y ser de entrada).
        - `spec` str numérico: índice.
        - `spec` str: coincidencia exacta y luego subcadena; si hay varios
          candidatos se prefiere el de la API host "Windows WASAPI".
        Devuelve el índice; lanza AudioError si no se encuentra o es ambiguo.
        """
        if isinstance(spec, str) and spec.strip() == "":
            raise AudioError("Especificación de dispositivo vacía")
        inputs = [
            i for i, d in enumerate(devices) if d["max_input_channels"] >= 1
        ]
        if isinstance(spec, int):
            idx = spec
        else:
            s = spec.strip()
            if s.isdigit():
                idx = int(s)
            else:
                exact = [i for i in inputs if devices[i]["name"].lower() == s.lower()]
                if len(exact) == 1:
                    return exact[0]
                matched = [
                    i for i in inputs if s.lower() in devices[i]["name"].lower()
                ]
                if len(matched) == 1:
                    return matched[0]
                wasapi = [
                    i
                    for i in matched
                    if "wasapi" in hostapis[devices[i]["hostapi"]]["name"].lower()
                ]
                if len(wasapi) == 1:
                    return wasapi[0]
                if not matched:
                    raise AudioError(
                        f"No hay dispositivo de entrada que contenga: {spec!r}"
                    )
                names = ", ".join(f"[{i}] {devices[i]['name']}" for i in matched)
                raise AudioError(f"Dispositivo ambiguo {spec!r}: {names}")
        if idx not in inputs:
            raise AudioError(f"El dispositivo [{idx}] no es un dispositivo de entrada")
        return idx

    def iter_input_blocks(self) -> Iterator[np.ndarray]:
        """Genera bloques mono float32 [-1, 1] a `samplerate` desde el micrófono.

        Sin dispositivo configurado usa el por defecto a `samplerate`/`channels`
        (comportamiento previo). Con dispositivo configurado abre su formato
        nativo y convierte a `samplerate`/mono. Se bloquea hasta que llega cada
        bloque; Ctrl+C interrumpe el loop. Cada bloque tiene exactamente
        `block_size` muestras.
        """
        import sounddevice as sd

        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
        in_index = None
        if self.device is not None:
            in_index = self.resolve_input_device(self.device, devices, hostapis)
        if in_index is None:
            in_sr = self.input_samplerate or self.samplerate
            in_ch = self.input_channels or self.channels
        else:
            dev = devices[in_index]
            in_sr = self.input_samplerate or int(dev["default_samplerate"])
            in_ch = self.input_channels or int(dev["max_input_channels"])
            in_ch = in_ch or self.channels
        if in_sr % self.samplerate == 0:
            in_block = self.block_size * (in_sr // self.samplerate)
        else:
            in_block = int(
                round(self.block_size * in_sr / self.samplerate)
            )
        self.active_input_device = in_index
        self.active_input_samplerate = in_sr
        self.active_input_channels = in_ch
        self.active_input_frame_size = in_block
        resampler = _StreamResampler(in_sr, self.samplerate)

        try:
            with sd.InputStream(
                device=in_index,
                samplerate=in_sr,
                channels=in_ch,
                dtype="float32",
                blocksize=in_block,
            ) as stream:
                self.active_input_dtype = str(
                    getattr(stream, "raw_input_dtype", "float32")
                )
                tail = np.zeros(0, dtype=np.float32)
                while True:
                    block, overflow = stream.read(in_block)
                    self.last_input_overflow = bool(overflow)
                    if self._on_native_block is not None:
                        self._on_native_block(
                            np.array(block, copy=True),
                            in_sr,
                            in_ch,
                            in_block,
                            bool(overflow),
                        )
                    mono = block.reshape(-1) if block.ndim == 1 else block.mean(axis=1)
                    mono = np.asarray(mono, dtype=np.float32).reshape(-1)
                    converted = resampler.process(mono)
                    if tail.size:
                        converted = np.concatenate([tail, converted])
                        tail = np.zeros(0, dtype=np.float32)
                    n = len(converted)
                    out_blocks = n // self.block_size
                    for i in range(out_blocks):
                        yield converted[i * self.block_size : (i + 1) * self.block_size]
                    tail = (
                        converted[out_blocks * self.block_size :]
                        if n > out_blocks * self.block_size
                        else np.zeros(0, dtype=np.float32)
                    )
        except sd.PortAudioError as exc:
            raise AudioError(f"No se pudo abrir el micrófono: {exc}") from exc

    def play(self, wav_path: Path | str) -> None:
        """Reproduce un WAV mono hasta el final (bloqueante)."""
        samplerate, samples = self.read_wav(wav_path)
        import sounddevice as sd

        try:
            sd.play(samples, samplerate)
            sd.wait()
        except sd.PortAudioError as exc:
            raise AudioError(f"No se pudo reproducir {wav_path}: {exc}") from exc

    # ------------------------------------------------------------------
    # WAV (sin sounddevice, probable sin hardware)
    # ------------------------------------------------------------------
    @staticmethod
    def to_int16(samples: np.ndarray) -> np.ndarray:
        """Convierte a int16 PCM: float32 [-1, 1] escalado o int ya PCM."""
        arr = np.asarray(samples)
        if arr.dtype.kind in "iu":
            return np.clip(arr, -32768, 32767).astype(np.int16)
        return np.clip(
            arr.astype(np.float32) * 32767.0, -32768.0, 32767.0
        ).astype(np.int16)

    @staticmethod
    def write_wav(
        path: Path | str, samples: np.ndarray, samplerate: int
    ) -> None:
        """Escribe un WAV mono int16 PCM (16 kHz recomendado para STT)."""
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        pcm = AudioManager.to_int16(np.asarray(samples).reshape(-1))
        with wave.open(str(dest), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(samplerate)
            wav.writeframes(pcm.tobytes())

    @staticmethod
    def read_wav(path: Path | str) -> tuple[int, np.ndarray]:
        """Lee un WAV mono y devuelve (samplerate, float32 [-1, 1])."""
        src = Path(path)
        if not src.exists():
            raise AudioError(f"No existe el archivo de audio: {src}")
        with wave.open(str(src), "rb") as wav:
            channels = wav.getnchannels()
            sampwidth = wav.getsampwidth()
            samplerate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())
        if channels != 1:
            raise AudioError(f"Solo se soportan WAV mono: {src} ({channels} canales)")
        if sampwidth != 2:
            raise AudioError(f"Solo se soportan WAV int16: {src} ({sampwidth} bytes)")
        pcm = np.frombuffer(frames, dtype=np.int16)
        return samplerate, pcm.astype(np.float32) / 32767.0