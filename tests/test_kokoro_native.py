import sys
import types
import wave
from pathlib import Path

import pytest

from app.adapters.kokoro_native import KokoroNativeTTSClient


def test_kokoro_native_writes_real_audio_when_package_available(tmp_path, monkeypatch):
    calls = {}

    class FakePipeline:
        def __init__(self, lang_code):
            calls["lang_code"] = lang_code

        def __call__(self, text, voice, speed=1.0):
            calls["text"] = text
            calls["voice"] = voice
            calls["speed"] = speed
            yield "graphemes", "phonemes", [0.0, 0.2, -0.2] * 800

    fake_kokoro = types.SimpleNamespace(KPipeline=FakePipeline)
    monkeypatch.setitem(sys.modules, "kokoro", fake_kokoro)

    out = tmp_path / "speech.wav"
    client = KokoroNativeTTSClient(enabled=True)
    produced = client.synthesise_sync("Hello Billy", "bf_emma", out, speed=1.25)

    assert produced == out
    assert calls == {"lang_code": "b", "text": "Hello Billy", "voice": "bf_emma", "speed": 1.25}
    with wave.open(str(out), "rb") as wav:
        assert wav.getframerate() == 24000
        assert wav.getnchannels() == 1
        assert wav.getnframes() > 1000


def test_kokoro_native_returns_none_when_package_missing(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "kokoro", None)
    client = KokoroNativeTTSClient(enabled=True)
    assert client.synthesise_sync("Hello", "bf_emma", tmp_path / "x.wav") is None


def test_kokoro_native_uses_american_pipeline_for_non_british_voice(tmp_path, monkeypatch):
    seen = {}

    class FakePipeline:
        def __init__(self, lang_code):
            seen["lang_code"] = lang_code

        def __call__(self, text, voice, speed=1.0):
            yield "g", "p", [0.0] * 1000

    monkeypatch.setitem(sys.modules, "kokoro", types.SimpleNamespace(KPipeline=FakePipeline))
    produced = KokoroNativeTTSClient(enabled=True).synthesise_sync("Hi", "af_heart", tmp_path / "x.wav")
    assert produced is not None
    assert seen["lang_code"] == "a"
