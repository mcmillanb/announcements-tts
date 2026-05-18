from __future__ import annotations

import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

OUTPUT_FORMATS = {
    "wav-pcm-16k": {"ext": ".wav", "mime": "audio/wav", "rate": 16000, "codec": "pcm_s16le"},
    "wav-pcm-8k": {"ext": ".wav", "mime": "audio/wav", "rate": 8000, "codec": "pcm_s16le"},
    "wav-alaw-8k": {"ext": ".wav", "mime": "audio/wav", "rate": 8000, "codec": "pcm_alaw"},
    "wav-ulaw-8k": {"ext": ".wav", "mime": "audio/wav", "rate": 8000, "codec": "pcm_mulaw"},
    "wav-alaw-16k": {"ext": ".wav", "mime": "audio/wav", "rate": 16000, "codec": "pcm_alaw"},
    "wav-ulaw-16k": {"ext": ".wav", "mime": "audio/wav", "rate": 16000, "codec": "pcm_mulaw"},
    "wav-pcm-24k": {"ext": ".wav", "mime": "audio/wav", "rate": 24000, "codec": "pcm_s16le"},
    "mp3": {"ext": ".mp3", "mime": "audio/mpeg", "rate": 44100, "codec": "libmp3lame"},
    "flac": {"ext": ".flac", "mime": "audio/flac", "rate": 24000, "codec": "flac"},
    "ogg": {"ext": ".ogg", "mime": "audio/ogg", "rate": 24000, "codec": "libvorbis"},
}


def generate_fallback_wav(text: str, output_path: Path, duration_seconds: float | None = None, speed: float = 1.0) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 24000
    duration = duration_seconds if duration_seconds is not None else min(6.0, max(0.5, len(text) / (18.0 * max(speed, 0.1))))
    frames = int(sample_rate * duration)
    # Stable audible placeholder: low amplitude tone with frequency derived from text.
    freq = 330 + (sum(text.encode("utf-8")) % 220)
    amp = 0.16
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        payload = bytearray()
        for i in range(frames):
            # Slight envelope to avoid clicks.
            t = i / sample_rate
            env = min(1.0, i / max(1, sample_rate * 0.02), (frames - i) / max(1, sample_rate * 0.02))
            value = int(max(-1.0, min(1.0, amp * env * math.sin(2 * math.pi * freq * t))) * 32767)
            payload.extend(struct.pack("<h", value))
        wf.writeframes(bytes(payload))
    return output_path


def ffmpeg_command(input_path: Path, output_path: Path, output_format: str, amplitude: float = 1.0) -> list[str]:
    if output_format not in OUTPUT_FORMATS:
        raise ValueError(f"Unsupported output format: {output_format}")
    fmt = OUTPUT_FORMATS[output_format]
    filters = [f"volume={amplitude}"] if amplitude != 1.0 else []
    cmd = ["ffmpeg", "-y", "-i", str(input_path), "-ar", str(fmt["rate"]), "-ac", "1"]
    if filters:
        cmd += ["-filter:a", ",".join(filters)]
    cmd += ["-c:a", str(fmt["codec"]), str(output_path)]
    return cmd


def convert_audio(input_path: Path, output_path: Path, output_format: str, amplitude: float = 1.0) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("ffmpeg") is None:
        # No ffmpeg: keep API useful for WAV formats by copying native placeholder.
        if output_format.startswith("wav-"):
            output_path.write_bytes(input_path.read_bytes())
            return output_path
        raise RuntimeError("ffmpeg is required for non-WAV output conversion")
    subprocess.run(ffmpeg_command(input_path, output_path, output_format, amplitude), check=True, capture_output=True)
    return output_path


def mime_for(output_format: str) -> str:
    return str(OUTPUT_FORMATS[output_format]["mime"])


def extension_for(output_format: str) -> str:
    return str(OUTPUT_FORMATS[output_format]["ext"])
