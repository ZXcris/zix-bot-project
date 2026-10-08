from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import onnxruntime as ort

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from zix.config import Config, project_path
from zix.voice.audio import AudioManager, _StreamResampler
from zix.voice.openwakeword_wake_word import OpenWakeWordProvider


class NativeWavWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._wav: wave.Wave_write | None = None
        self.frames = 0
        self.dtype: str | None = None
        self.shape: tuple[int, ...] | None = None

    def write(
        self,
        samples: np.ndarray,
        samplerate: int,
        channels: int,
        frame_samples: int,
        overflow: bool,
    ) -> None:
        del frame_samples, overflow
        arr = np.asarray(samples)
        if self._wav is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._wav = wave.open(str(self.path), "wb")
            self._wav.setnchannels(channels)
            self._wav.setsampwidth(2)
            self._wav.setframerate(samplerate)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        pcm = AudioManager.to_int16(arr).astype("<i2", copy=False)
        self._wav.writeframes(pcm.tobytes())
        self.frames += int(arr.shape[0])
        self.dtype = str(arr.dtype)
        self.shape = tuple(int(value) for value in arr.shape)

    def close(self) -> None:
        if self._wav is not None:
            self._wav.close()
            self._wav = None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_contract(path: Path) -> dict:
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    return {
        "providers": session.get_providers(),
        "inputs": [
            {"name": item.name, "shape": item.shape, "type": item.type}
            for item in session.get_inputs()
        ],
        "outputs": [
            {"name": item.name, "shape": item.shape, "type": item.type}
            for item in session.get_outputs()
        ],
        "metadata": session.get_modelmeta().custom_metadata_map,
    }


def provider_state(provider: OpenWakeWordProvider) -> dict:
    preprocessor = provider._model.preprocessor
    feature_buffer = np.asarray(preprocessor.feature_buffer)
    return {
        "raw_buffer_samples": len(preprocessor.raw_data_buffer),
        "feature_buffer_shape": [
            int(value) for value in feature_buffer.shape
        ],
        "feature_buffer_checksum": float(feature_buffer.sum(dtype=np.float64)),
        "prediction_buffer_length": len(
            provider._model.prediction_buffer[provider._key]
        ),
    }


def read_native_wav(path: Path) -> tuple[int, int, np.ndarray]:
    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        samplerate = source.getframerate()
        frames = source.readframes(source.getnframes())
    if channels < 1:
        raise RuntimeError(f"Native WAV has no channels: {path}")
    if sample_width != 2:
        raise RuntimeError(f"Native WAV is not int16: {path}")
    pcm = np.frombuffer(frames, dtype="<i2").reshape(-1, channels)
    return samplerate, channels, pcm.astype(np.float32) / 32767.0


def replay_native(
    path: Path,
    output_sample_rate: int,
    output_block_size: int,
    input_frame_size: int,
    model: str,
    models_dir: Path,
    threshold: float,
    speex_noise_suppression: bool,
    seed: int,
) -> dict:
    input_sample_rate, channels, native = read_native_wav(path)
    np.random.seed(seed)
    provider = OpenWakeWordProvider(
        model=model,
        threshold=threshold,
        models_dir=models_dir,
        speex_noise_suppression=speex_noise_suppression,
    )
    resampler = _StreamResampler(input_sample_rate, output_sample_rate)
    initial_state = provider_state(provider)
    pending = np.zeros(0, dtype=np.float32)
    processed: list[np.ndarray] = []
    scores: list[float] = []
    for start in range(0, len(native), input_frame_size):
        chunk = native[start : start + input_frame_size]
        mono = chunk.reshape(-1) if channels == 1 else chunk.mean(axis=1)
        converted = resampler.process(np.asarray(mono, dtype=np.float32))
        pending = np.concatenate([pending, converted])
        while len(pending) >= output_block_size:
            block = pending[:output_block_size]
            pending = pending[output_block_size:]
            processed.append(AudioManager.to_int16(block))
            provider.process(block)
            scores.append(float(provider.last_score or 0.0))
    processed_pcm = (
        np.concatenate(processed) if processed else np.zeros(0, dtype=np.int16)
    )
    return {
        "input_sample_rate": input_sample_rate,
        "input_channels": channels,
        "input_frame_samples": input_frame_size,
        "processed_frames": int(len(processed_pcm)),
        "pending_samples": int(len(pending)),
        "scores": scores,
        "processed_pcm": processed_pcm,
        "initial_state": initial_state,
        "final_state": provider_state(provider) if scores else initial_state,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--seed", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.duration <= 0:
        raise ValueError("--duration debe ser mayor que cero")

    config = Config.from_env()
    seed = args.seed if args.seed is not None else secrets.randbits(32)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = args.output_dir or project_path(config.voice_runtime_dir) / f"wakeword-diagnostic-{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "microphone-native.wav"
    processed_path = output_dir / "microphone-16k-mono.wav"
    replayed_path = output_dir / "microphone-16k-mono-from-raw.wav"
    frames_path = output_dir / "frames.jsonl"
    summary_path = output_dir / "summary.json"

    model_path = project_path(config.wake_models_dir) / f"{config.wake_word_model}.onnx"
    data_path = model_path.with_suffix(model_path.suffix + ".data")
    if not model_path.exists():
        raise FileNotFoundError(model_path)
    if not data_path.exists():
        raise FileNotFoundError(data_path)

    np.random.seed(seed)
    provider = OpenWakeWordProvider(
        model=config.wake_word_model,
        threshold=config.wake_word_threshold,
        models_dir=project_path(config.wake_models_dir),
        speex_noise_suppression=config.wake_word_speex_ns,
    )
    initial_state = provider_state(provider)
    native_writer = NativeWavWriter(raw_path)
    processed_pcm: list[np.ndarray] = []
    online_records: list[dict] = []
    started_utc = datetime.now(timezone.utc)
    started = time.monotonic()

    audio = AudioManager(
        samplerate=config.voice_sample_rate,
        block_size=config.voice_block_size,
        device=config.audio_input_device or None,
        input_samplerate=config.audio_input_samplerate or None,
        input_channels=config.audio_input_channels or None,
        on_native_block=native_writer.write,
    )
    stream = audio.iter_input_blocks()
    print(
        f"Capturando {args.duration:.1f} s; habla después de 5 s. "
        f"Semilla openWakeWord={seed}",
        flush=True,
    )
    try:
        with frames_path.open("w", encoding="utf-8") as frame_log:
            for frame_index, block in enumerate(stream):
                elapsed = time.monotonic() - started
                arr = np.asarray(block)
                pcm = AudioManager.to_int16(arr)
                processed_pcm.append(pcm)
                detected = provider.process(block)
                score = float(provider.last_score or 0.0)
                state = provider_state(provider)
                record = {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "elapsed_seconds": elapsed,
                    "frame_index": frame_index,
                    "input_device": audio.active_input_device,
                    "input_sample_rate": audio.active_input_samplerate,
                    "input_channels": audio.active_input_channels,
                    "input_dtype": audio.active_input_dtype,
                    "input_frame_samples": audio.active_input_frame_size,
                    "input_overflow": audio.last_input_overflow,
                    "output_sample_rate": config.voice_sample_rate,
                    "frame_samples": int(arr.size),
                    "dtype": str(arr.dtype),
                    "rms": float(np.sqrt(np.mean(np.square(arr.astype(np.float64))))),
                    "peak": float(np.max(np.abs(arr))),
                    "minimum": float(np.min(arr)),
                    "maximum": float(np.max(arr)),
                    "score": score,
                    "threshold": config.wake_word_threshold,
                    "would_trigger": bool(detected),
                    **state,
                }
                frame_log.write(json.dumps(record, ensure_ascii=False) + "\n")
                online_records.append(record)
                if elapsed >= args.duration:
                    break
    finally:
        stream.close()
        native_writer.close()

    processed = np.concatenate(processed_pcm) if processed_pcm else np.zeros(0, dtype=np.int16)
    AudioManager.write_wav(processed_path, processed, config.voice_sample_rate)

    np.random.seed(seed)
    offline_provider = OpenWakeWordProvider(
        model=config.wake_word_model,
        threshold=config.wake_word_threshold,
        models_dir=project_path(config.wake_models_dir),
        speex_noise_suppression=config.wake_word_speex_ns,
    )
    offline_initial_state = provider_state(offline_provider)
    sample_rate, samples = AudioManager.read_wav(processed_path)
    if sample_rate != config.voice_sample_rate:
        raise RuntimeError(
            f"Processed sample rate mismatch: {sample_rate} != {config.voice_sample_rate}"
        )
    offline_scores: list[float] = []
    offline_states: list[dict] = []
    for start in range(0, len(samples) - config.voice_block_size + 1, config.voice_block_size):
        block = samples[start : start + config.voice_block_size]
        offline_provider.process(block)
        offline_scores.append(float(offline_provider.last_score or 0.0))
        offline_states.append(provider_state(offline_provider))

    online_scores = [record["score"] for record in online_records]
    common = min(len(online_scores), len(offline_scores))
    deltas = [
        abs(online_scores[index] - offline_scores[index])
        for index in range(common)
    ]
    online_max_index = int(np.argmax(online_scores)) if online_scores else -1
    offline_max_index = int(np.argmax(offline_scores)) if offline_scores else -1

    input_frame_size = int(audio.active_input_frame_size or config.voice_block_size)
    raw_replay = replay_native(
        raw_path,
        output_sample_rate=config.voice_sample_rate,
        output_block_size=config.voice_block_size,
        input_frame_size=input_frame_size,
        model=config.wake_word_model,
        models_dir=project_path(config.wake_models_dir),
        threshold=config.wake_word_threshold,
        speex_noise_suppression=config.wake_word_speex_ns,
        seed=seed,
    )
    replay_scores = raw_replay.pop("scores")
    replay_pcm = raw_replay.pop("processed_pcm")
    AudioManager.write_wav(replayed_path, replay_pcm, config.voice_sample_rate)
    replay_common = min(len(online_scores), len(replay_scores))
    replay_deltas = [
        abs(online_scores[index] - replay_scores[index])
        for index in range(replay_common)
    ]
    replay_max_index = int(np.argmax(replay_scores)) if replay_scores else -1
    pcm_equal = np.array_equal(processed, replay_pcm)
    pcm_max_delta = (
        int(np.max(np.abs(processed.astype(np.int32) - replay_pcm.astype(np.int32))))
        if len(processed) == len(replay_pcm) and len(processed)
        else None
    )

    summary = {
        "capture_started_utc": started_utc.isoformat(),
        "capture_finished_utc": datetime.now(timezone.utc).isoformat(),
        "requested_duration_seconds": args.duration,
        "seed": seed,
        "threshold": config.wake_word_threshold,
        "model": {
            "path": str(model_path),
            "sha256": sha256(model_path),
            "data_path": str(data_path),
            "data_sha256": sha256(data_path),
            "contract": model_contract(model_path),
        },
        "capture": {
            "raw_wav": str(raw_path),
            "raw_frames": native_writer.frames,
            "raw_dtype": native_writer.dtype,
            "raw_shape": native_writer.shape,
            "processed_wav": str(processed_path),
            "reprocessed_wav": str(replayed_path),
            "processed_frames": int(len(processed)),
            "processed_sample_rate": sample_rate,
            "processed_channels": 1,
            "processed_dtype": "int16",
            "online_frame_count": len(online_records),
            "offline_frame_count": len(offline_scores),
        },
        "online": {
            "maximum_score": max(online_scores) if online_scores else 0.0,
            "maximum_frame_index": online_max_index,
            "maximum_elapsed_seconds": (
                online_records[online_max_index]["elapsed_seconds"]
                if online_max_index >= 0
                else 0.0
            ),
            "trigger_count": sum(
                record["score"] >= config.wake_word_threshold
                for record in online_records
            ),
            "initial_state": initial_state,
            "final_state": online_records[-1] if online_records else initial_state,
        },
        "offline": {
            "maximum_score": max(offline_scores) if offline_scores else 0.0,
            "maximum_frame_index": offline_max_index,
            "trigger_count": sum(
                score >= config.wake_word_threshold for score in offline_scores
            ),
            "initial_state": offline_initial_state,
            "final_state": offline_states[-1] if offline_states else offline_initial_state,
        },
        "raw_replay": {
            **raw_replay,
            "processed_pcm_identical": bool(pcm_equal),
            "processed_pcm_maximum_absolute_delta": pcm_max_delta,
            "maximum_score": max(replay_scores) if replay_scores else 0.0,
            "maximum_frame_index": replay_max_index,
            "trigger_count": sum(
                score >= config.wake_word_threshold for score in replay_scores
            ),
            "online_parity": {
                "compared_frames": replay_common,
                "maximum_absolute_score_delta": (
                    max(replay_deltas) if replay_deltas else 0.0
                ),
                "mean_absolute_score_delta": (
                    float(np.mean(np.asarray(replay_deltas, dtype=np.float64)))
                    if replay_deltas
                    else 0.0
                ),
                "frames_with_delta_above_1e_9": sum(
                    delta > 1e-9 for delta in replay_deltas
                ),
            },
        },
        "parity": {
            "compared_frames": common,
            "maximum_absolute_score_delta": max(deltas) if deltas else 0.0,
            "mean_absolute_score_delta": (
                float(np.mean(np.asarray(deltas, dtype=np.float64)))
                if deltas
                else 0.0
            ),
            "frames_with_delta_above_1e_9": sum(
                delta > 1e-9 for delta in deltas
            ),
        },
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
