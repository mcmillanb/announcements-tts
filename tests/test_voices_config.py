from pathlib import Path
from app.config import AppConfig, load_config
from app.voices import BUILTIN_VOICES, VoiceRegistry


def test_builtin_british_voices_are_registered():
    registry = VoiceRegistry(AppConfig())
    ids = {v.id: v for v in registry.list_voices()}
    assert set(BUILTIN_VOICES) == {"uk-male-1", "uk-male-2", "uk-female-1", "uk-female-2"}
    assert ids["uk-male-1"].speaker == "bm_george"
    assert ids["uk-female-2"].speaker == "bf_isabella"
    assert all(ids[v].type == "builtin" for v in BUILTIN_VOICES)


def test_custom_voice_paths_are_validated(tmp_path):
    sample = tmp_path / "voice.wav"
    sample.write_bytes(b"RIFFxxxxWAVE")
    cfg = AppConfig(custom_voices={
        "good": {"label": "Good", "sample_file": str(sample), "language": "en"},
        "missing": {"label": "Missing", "sample_file": str(tmp_path / "missing.wav"), "language": "en"},
    })
    registry = VoiceRegistry(cfg)
    ids = {v.id: v for v in registry.list_voices()}
    assert ids["good"].type == "clone"
    assert "missing" not in ids


def test_load_config_merges_defaults_and_redacts_secrets(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text('{"openwebui":{"api_key":"secret"},"defaults":{"voice_id":"uk-male-1"}}')
    cfg = load_config(config_file)
    assert cfg.defaults.voice_id == "uk-male-1"
    assert cfg.defaults.output_format == "wav-pcm-16k"
    assert cfg.redacted()["openwebui"]["api_key"] == "***redacted***"
