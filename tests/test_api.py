import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.audio import generate_tone_wav
from app.main import create_app


class FakeBundledClient:
    def __init__(self, *args, **kwargs):
        pass

    async def synthesise(self, text, voice, output_path, speed=1.0):
        generate_tone_wav(output_path, frequency_hz=440, beep_seconds=0.1, total_seconds=max(0.1, len(text) / 100))
        return output_path


def test_health_and_voices(tmp_path, monkeypatch):
    monkeypatch.setenv("BRITISHTTS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BRITISHTTS_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("BRITISHTTS_SAMPLE_DIR", str(tmp_path / "samples"))
    client = TestClient(create_app())
    health = client.get("/health").json()
    assert health["status"] == "ok"
    assert "fallback_available" not in health["engine"]
    voices = client.get("/voices").json()["voices"]
    assert any(v["id"] == "uk-female-1" and v["type"] == "builtin" for v in voices)


def test_synthesise_returns_audio_and_persists_file(tmp_path, monkeypatch):
    monkeypatch.setenv("BRITISHTTS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BRITISHTTS_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("BRITISHTTS_SAMPLE_DIR", str(tmp_path / "samples"))
    monkeypatch.setattr(main_module, "BundledRemoteTTSClient", FakeBundledClient)
    client = TestClient(create_app())
    resp = client.post("/synthesise", json={"text":"Hello Billy", "output_format":"wav-pcm-16k", "filename":"hello"})
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("audio/wav")
    assert "attachment" in resp.headers["content-disposition"]
    files = list((tmp_path / "output").glob("hello*.wav"))
    assert len(files) == 1
    assert files[0].stat().st_size > 44


def test_synthesise_validation_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("BRITISHTTS_OUTPUT_DIR", str(tmp_path / "output"))
    client = TestClient(create_app())
    assert client.post("/synthesise", json={"text":"", "amplitude": 1}).status_code == 422
    assert client.post("/synthesise", json={"text":"x", "amplitude": 9}).status_code == 422
    assert client.post("/synthesise", json={"text":"x", "pitch": 13}).status_code == 422
    assert client.post("/synthesise", json={"text":"x", "voice_id":"nope"}).status_code == 404


def test_upload_sample_adds_file(tmp_path, monkeypatch):
    monkeypatch.setenv("BRITISHTTS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BRITISHTTS_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("BRITISHTTS_SAMPLE_DIR", str(tmp_path / "samples"))
    client = TestClient(create_app())
    resp = client.post("/upload-sample", files={"file": ("sample.wav", b"RIFFxxxxWAVE", "audio/wav")})
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"].endswith(".wav")
    assert Path(data["path"]).exists()


def test_config_is_redacted_and_ui_served(tmp_path, monkeypatch):
    monkeypatch.setenv("BRITISHTTS_CONFIG_DIR", str(tmp_path / "config"))
    client = TestClient(create_app())
    assert client.get("/config").status_code == 200
    ui = client.get("/ui")
    assert ui.status_code == 200
    assert "Announcement TTS" in ui.text
    assert "Tone Generator" in ui.text
    assert "Fallback tone" not in ui.text


def test_synthesise_returns_503_when_provider_does_not_produce_audio(tmp_path, monkeypatch):
    monkeypatch.setenv("BRITISHTTS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BRITISHTTS_OUTPUT_DIR", str(tmp_path / "output"))

    class EmptyBundledClient:
        def __init__(self, *args, **kwargs):
            pass

        async def synthesise(self, *args, **kwargs):
            return None

    monkeypatch.setattr(main_module, "BundledRemoteTTSClient", EmptyBundledClient)
    client = TestClient(create_app())
    resp = client.post("/synthesise", json={"text": "No provider output"})

    assert resp.status_code == 503


def test_tone_endpoint_creates_configured_beep(tmp_path, monkeypatch):
    monkeypatch.setenv("BRITISHTTS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BRITISHTTS_OUTPUT_DIR", str(tmp_path / "output"))
    client = TestClient(create_app())

    resp = client.post(
        "/tone",
        json={
            "frequency_hz": 880,
            "beep_seconds": 0.2,
            "total_seconds": 1.0,
            "silence_before_seconds": 0.1,
            "silence_after_seconds": 0.7,
            "amplitude": 0.5,
            "output_format": "wav-pcm-16k",
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("audio/wav")
    assert len(resp.content) > 44


def test_bulk_synthesise_creates_zip_from_csv(tmp_path, monkeypatch):
    monkeypatch.setenv("BRITISHTTS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BRITISHTTS_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr(main_module, "BundledRemoteTTSClient", FakeBundledClient)
    client = TestClient(create_app())
    csv_body = '"Text","Filename"\n"First announcement, with comma","first"\n"Second announcement[pause:0.2]Done","second.wav"\n'

    resp = client.post(
        "/bulk-synthesise",
        data={"output_format": "wav-pcm-16k"},
        files={"file": ("announcements.csv", csv_body, "text/csv")},
    )

    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["total"] == 2
    status = client.get(f"/bulk-synthesise/{job['id']}/status").json()
    assert status["status"] == "complete"
    assert status["message"] == "Created 2 announcements"
    download = client.get(status["download_url"])
    assert download.status_code == 200, download.text
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        assert sorted(archive.namelist()) == ["first.wav", "second.wav"]
        assert all(archive.getinfo(name).file_size > 44 for name in archive.namelist())


def test_pause_marker_adds_silence_to_provider_audio(tmp_path, monkeypatch):
    monkeypatch.setenv("BRITISHTTS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BRITISHTTS_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr(main_module, "BundledRemoteTTSClient", FakeBundledClient)
    client = TestClient(create_app())

    plain = client.post("/synthesise", json={"text": "Hello world"})
    paused = client.post("/synthesise", json={"text": "Hello[pause:1.0]world"})

    assert plain.status_code == 200, plain.text
    assert paused.status_code == 200, paused.text
    assert len(paused.content) > len(plain.content)


def test_config_can_switch_provider_and_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("BRITISHTTS_CONFIG_DIR", str(tmp_path / "config"))
    client = TestClient(create_app())
    config = client.get("/config").json()
    config["engine"]["provider"] = "external"
    config["engine"]["external_provider"] = "openai"
    config["openai"]["enabled"] = True
    config["openai"]["api_key"] = "secret"

    resp = client.post("/config", json=config)

    assert resp.status_code == 200, resp.text
    assert resp.json()["engine"]["provider"] == "external"
    assert resp.json()["engine"]["external_provider"] == "openai"
    assert resp.json()["openai"]["api_key"] == "***redacted***"
    health = client.get("/health").json()["engine"]
    assert health["provider"] == "external"
    assert health["external_provider"] == "openai"
    assert (tmp_path / "config" / "config.json").exists()


def test_config_can_persist_default_voice_and_format(tmp_path, monkeypatch):
    monkeypatch.setenv("BRITISHTTS_CONFIG_DIR", str(tmp_path / "config"))
    client = TestClient(create_app())
    config = client.get("/config").json()
    config["defaults"]["voice_id"] = "uk-male-1"
    config["defaults"]["output_format"] = "mp3"

    resp = client.post("/config", json=config)

    assert resp.status_code == 200, resp.text
    assert resp.json()["defaults"]["voice_id"] == "uk-male-1"
    assert resp.json()["defaults"]["output_format"] == "mp3"
    saved = (tmp_path / "config" / "config.json").read_text()
    assert '"voice_id": "uk-male-1"' in saved
    assert '"output_format": "mp3"' in saved


def test_default_lmstudio_port_is_1234(tmp_path, monkeypatch):
    monkeypatch.setenv("BRITISHTTS_CONFIG_DIR", str(tmp_path / "config"))
    client = TestClient(create_app())
    config = client.get("/config").json()

    assert config["lmstudio"]["base_url"] == "http://host.docker.internal:1234/v1"
