from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def test_health_and_voices(tmp_path, monkeypatch):
    monkeypatch.setenv("BRITISHTTS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BRITISHTTS_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("BRITISHTTS_SAMPLE_DIR", str(tmp_path / "samples"))
    client = TestClient(create_app())
    health = client.get("/health").json()
    assert health["status"] == "ok"
    assert health["engine"]["fallback_available"] is True
    voices = client.get("/voices").json()["voices"]
    assert any(v["id"] == "uk-female-1" and v["type"] == "builtin" for v in voices)


def test_synthesise_returns_audio_and_persists_file(tmp_path, monkeypatch):
    monkeypatch.setenv("BRITISHTTS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BRITISHTTS_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("BRITISHTTS_SAMPLE_DIR", str(tmp_path / "samples"))
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
    assert "British TTS" in ui.text


def test_config_can_switch_provider_and_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("BRITISHTTS_CONFIG_DIR", str(tmp_path / "config"))
    client = TestClient(create_app())
    config = client.get("/config").json()
    config["engine"]["provider"] = "external"
    config["lmstudio"]["base_url"] = "http://host.docker.internal:8888/v1"

    resp = client.post("/config", json=config)

    assert resp.status_code == 200, resp.text
    assert resp.json()["engine"]["provider"] == "external"
    assert client.get("/health").json()["engine"]["provider"] == "external"
    assert (tmp_path / "config" / "config.json").exists()
