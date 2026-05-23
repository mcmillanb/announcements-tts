from pathlib import Path
import math
import wave

import pytest

from app.config import AppConfig
from app.schemas import SynthesiseRequest
from app.synth import Synthesiser
from app.voices import BUILTIN_VOICES


def _write_wav(path: Path, frames: int = 2400):
    samples = []
    for i in range(frames):
        value = int(math.sin(i / 12.0) * 12000)
        samples.append(value.to_bytes(2, "little", signed=True))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"".join(samples))


@pytest.mark.asyncio
async def test_synthesiser_prefers_piper_before_lmstudio(tmp_path, monkeypatch):
    calls = {"piper": 0, "lmstudio": 0}

    class FakePiper:
        def __init__(self, *args, **kwargs):
            pass

        def synthesise(self, text, output_path, speed=1.0):
            calls["piper"] += 1
            _write_wav(output_path)
            return output_path

    class FakeLMStudio:
        def __init__(self, *args, **kwargs):
            pass

        async def synthesise(self, *args, **kwargs):
            calls["lmstudio"] += 1
            return None

    monkeypatch.setattr("app.synth.PiperTTSClient", FakePiper)
    monkeypatch.setattr("app.synth.LMStudioTTSClient", FakeLMStudio)

    synth = Synthesiser(AppConfig(), tmp_path)
    out = await synth.synthesise(
        SynthesiseRequest(text="Real voice please", output_format="wav-pcm-24k", filename="real"),
        BUILTIN_VOICES["uk-female-1"],
    )

    assert out.exists()
    assert synth.last_engine == "piper"
    assert calls == {"piper": 1, "lmstudio": 0}


@pytest.mark.asyncio
async def test_synthesiser_falls_back_to_lmstudio_when_piper_unavailable(tmp_path, monkeypatch):
    calls = {"piper": 0, "lmstudio": 0}

    class FakePiper:
        def __init__(self, *args, **kwargs):
            pass

        def synthesise(self, *args, **kwargs):
            calls["piper"] += 1
            return None

    class FakeLMStudio:
        def __init__(self, *args, **kwargs):
            pass

        async def synthesise(self, text, voice, output_path, speed=1.0):
            calls["lmstudio"] += 1
            _write_wav(output_path)
            return output_path

    monkeypatch.setattr("app.synth.PiperTTSClient", FakePiper)
    monkeypatch.setattr("app.synth.LMStudioTTSClient", FakeLMStudio)

    synth = Synthesiser(AppConfig(), tmp_path)
    out = await synth.synthesise(
        SynthesiseRequest(text="LM provider", output_format="wav-pcm-24k", filename="lm"),
        BUILTIN_VOICES["uk-female-1"],
    )

    assert out.exists()
    assert synth.last_engine == "lmstudio"
    assert calls == {"piper": 1, "lmstudio": 1}
