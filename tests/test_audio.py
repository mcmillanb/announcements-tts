import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from app.audio import concatenate_wavs, convert_audio, ffmpeg_command, generate_silence_wav, generate_tone_wav, OUTPUT_FORMATS


def wav_info(path: Path):
    with wave.open(str(path), "rb") as wf:
        return wf.getframerate(), wf.getnchannels(), wf.getsampwidth(), wf.getnframes()


def test_tone_wav_is_deterministic_24k_mono(tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    generate_tone_wav(a, frequency_hz=440, beep_seconds=0.1, total_seconds=0.2, amplitude=0.5)
    generate_tone_wav(b, frequency_hz=440, beep_seconds=0.1, total_seconds=0.2, amplitude=0.5)
    assert a.read_bytes() == b.read_bytes()
    assert wav_info(a)[:3] == (24000, 1, 2)


def test_output_format_matrix_contains_required_formats():
    assert set(OUTPUT_FORMATS) == {"wav-pcm-16k","wav-pcm-8k","wav-alaw-8k","wav-ulaw-8k","wav-alaw-16k","wav-ulaw-16k","wav-pcm-24k","mp3","flac","ogg"}


def test_ffmpeg_command_can_adjust_pitch_and_volume(tmp_path):
    cmd = ffmpeg_command(tmp_path / "in.wav", tmp_path / "out.wav", "wav-pcm-16k", amplitude=1.2, pitch_semitones=12, source_rate=24000)

    assert "-filter:a" in cmd
    filters = cmd[cmd.index("-filter:a") + 1]
    assert "asetrate=48000" in filters
    assert "aresample=24000" in filters
    assert "atempo=0.500000" in filters
    assert "volume=1.2" in filters


def test_can_insert_silence_between_wavs(tmp_path):
    a = tmp_path / "a.wav"
    pause = tmp_path / "pause.wav"
    out = tmp_path / "out.wav"
    generate_tone_wav(a, frequency_hz=440, beep_seconds=0.1, total_seconds=0.1)
    generate_silence_wav(pause, 0.25)

    concatenate_wavs([a, pause], out)

    assert wav_info(out)[3] == wav_info(a)[3] + wav_info(pause)[3]


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg/ffprobe unavailable")
def test_convert_to_alaw_8k_mono(tmp_path):
    source = tmp_path / "source.wav"
    out = tmp_path / "prompt.wav"
    generate_tone_wav(source, frequency_hz=440, beep_seconds=0.2, total_seconds=0.2)
    convert_audio(source, out, "wav-alaw-8k", amplitude=1.2)
    probe = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,sample_rate,channels", "-of", "csv=p=0", str(out)
    ], text=True).strip()
    assert "pcm_alaw" in probe
    assert ",8000," in probe
    assert probe.endswith(",1")
