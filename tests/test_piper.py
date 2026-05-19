from pathlib import Path
import subprocess

from app.adapters.piper import PiperTTSClient


def test_piper_returns_none_when_model_missing(tmp_path):
    client = PiperTTSClient(tmp_path / "missing.onnx")

    result = client.synthesise("hello", tmp_path / "out.wav")

    assert result is None


def test_piper_invokes_cli_and_writes_real_audio(tmp_path):
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model")
    out = tmp_path / "out.wav"
    calls = []

    def fake_runner(cmd, **kwargs):
        calls.append((cmd, kwargs))
        Path(cmd[cmd.index("--output_file") + 1]).write_bytes(b"RIFF" + b"x" * 100)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    client = PiperTTSClient(model, runner=fake_runner)

    result = client.synthesise("hello world", out, speed=1.25)

    assert result == out
    assert out.read_bytes().startswith(b"RIFF")
    assert calls[0][0][:3] == ("piper", "--model", str(model))
    assert calls[0][1]["input"] == "hello world"
    assert "--length-scale" in calls[0][0]
