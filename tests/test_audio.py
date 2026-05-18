import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from app.audio import convert_audio, generate_fallback_wav, OUTPUT_FORMATS


def wav_info(path: Path):
    with wave.open(str(path), "rb") as wf:
        return wf.getframerate(), wf.getnchannels(), wf.getsampwidth(), wf.getnframes()


def test_fallback_wav_is_deterministic_24k_mono(tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    generate_fallback_wav("hello", a, duration_seconds=0.1)
    generate_fallback_wav("hello", b, duration_seconds=0.1)
    assert a.read_bytes() == b.read_bytes()
    assert wav_info(a)[:3] == (24000, 1, 2)


def test_output_format_matrix_contains_required_formats():
    assert set(OUTPUT_FORMATS) == {"wav-pcm-16k","wav-pcm-8k","wav-alaw-8k","wav-ulaw-8k","wav-alaw-16k","wav-ulaw-16k","wav-pcm-24k","mp3","flac","ogg"}


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg/ffprobe unavailable")
def test_convert_to_alaw_8k_mono(tmp_path):
    source = tmp_path / "source.wav"
    out = tmp_path / "prompt.wav"
    generate_fallback_wav("hello", source, duration_seconds=0.2)
    convert_audio(source, out, "wav-alaw-8k", amplitude=1.2)
    probe = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,sample_rate,channels", "-of", "csv=p=0", str(out)
    ], text=True).strip()
    assert "pcm_alaw" in probe
    assert ",8000," in probe
    assert probe.endswith(",1")
