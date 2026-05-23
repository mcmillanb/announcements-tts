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


def generate_tone_wav(
    output_path: Path,
    frequency_hz: float = 440.0,
    beep_seconds: float = 0.25,
    total_seconds: float = 1.0,
    silence_before_seconds: float = 0.0,
    silence_after_seconds: float = 0.0,
    amplitude: float = 0.8,
    sample_rate: int = 24000,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total_frames = max(1, int(sample_rate * total_seconds))
    start_frame = min(total_frames, max(0, int(sample_rate * silence_before_seconds)))
    latest_end = max(start_frame, total_frames - max(0, int(sample_rate * silence_after_seconds)))
    tone_frames = max(0, min(int(sample_rate * beep_seconds), latest_end - start_frame))
    end_frame = start_frame + tone_frames
    safe_amplitude = max(0.0, min(1.0, amplitude))
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        payload = bytearray()
        fade_frames = max(1, int(sample_rate * 0.01))
        for i in range(total_frames):
            if start_frame <= i < end_frame:
                tone_index = i - start_frame
                env = min(1.0, tone_index / fade_frames, (end_frame - i) / fade_frames)
                t = tone_index / sample_rate
                sample = safe_amplitude * env * math.sin(2 * math.pi * frequency_hz * t)
            else:
                sample = 0.0
            value = int(max(-1.0, min(1.0, sample)) * 32767)
            payload.extend(struct.pack("<h", value))
        wf.writeframes(bytes(payload))
    return output_path


def generate_silence_wav(
    output_path: Path,
    duration_seconds: float,
    sample_rate: int = 24000,
    channels: int = 1,
    sample_width: int = 2,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frames = max(1, int(sample_rate * duration_seconds))
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00" * frames * channels * sample_width)
    return output_path


def concatenate_wavs(input_paths: list[Path], output_path: Path) -> Path:
    if not input_paths:
        raise ValueError("At least one WAV input is required")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    params = None
    payload = bytearray()
    for input_path in input_paths:
        with wave.open(str(input_path), "rb") as wf:
            current = wf.getparams()
            comparable = (current.nchannels, current.sampwidth, current.framerate, current.comptype, current.compname)
            if params is None:
                params = comparable
            elif comparable != params:
                raise ValueError("Cannot concatenate WAV files with different audio parameters")
            payload.extend(wf.readframes(current.nframes))
    assert params is not None
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(params[0])
        wf.setsampwidth(params[1])
        wf.setframerate(params[2])
        wf.writeframes(bytes(payload))
    return output_path


def ffmpeg_command(
    input_path: Path,
    output_path: Path,
    output_format: str,
    amplitude: float = 1.0,
    pitch_semitones: float = 0.0,
    source_rate: int = 24000,
) -> list[str]:
    if output_format not in OUTPUT_FORMATS:
        raise ValueError(f"Unsupported output format: {output_format}")
    fmt = OUTPUT_FORMATS[output_format]
    filters = []
    if pitch_semitones != 0.0:
        pitch_factor = 2 ** (pitch_semitones / 12)
        shifted_rate = max(1, int(round(source_rate * pitch_factor)))
        filters.append(f"asetrate={shifted_rate},aresample={source_rate},atempo={1 / pitch_factor:.6f}")
    if amplitude != 1.0:
        filters.append(f"volume={amplitude}")
    cmd = ["ffmpeg", "-y", "-i", str(input_path), "-ar", str(fmt["rate"]), "-ac", "1"]
    if filters:
        cmd += ["-filter:a", ",".join(filters)]
    cmd += ["-c:a", str(fmt["codec"]), str(output_path)]
    return cmd


def convert_audio(
    input_path: Path,
    output_path: Path,
    output_format: str,
    amplitude: float = 1.0,
    pitch_semitones: float = 0.0,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("ffmpeg") is None:
        # No ffmpeg: keep API useful for WAV formats by copying native placeholder.
        if output_format.startswith("wav-"):
            output_path.write_bytes(input_path.read_bytes())
            return output_path
        raise RuntimeError("ffmpeg is required for non-WAV output conversion")
    with wave.open(str(input_path), "rb") as wf:
        source_rate = wf.getframerate()
    subprocess.run(
        ffmpeg_command(input_path, output_path, output_format, amplitude, pitch_semitones, source_rate),
        check=True,
        capture_output=True,
    )
    return output_path


def mime_for(output_format: str) -> str:
    return str(OUTPUT_FORMATS[output_format]["mime"])


def extension_for(output_format: str) -> str:
    return str(OUTPUT_FORMATS[output_format]["ext"])
