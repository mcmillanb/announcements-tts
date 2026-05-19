from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Literal

from pydantic import BaseModel, Field


class VoiceConfig(BaseModel):
    label: str
    sample_file: str
    language: str = "en"


class OllamaConfig(BaseModel):
    enabled: bool = False
    base_url: str = "http://host.docker.internal:11434"
    model: str = "llama3.2"


class OpenWebUIConfig(BaseModel):
    enabled: bool = False
    base_url: str = "http://host.docker.internal:3000"
    api_key: str = ""


class LMStudioConfig(BaseModel):
    enabled: bool = True
    base_url: str = Field(default_factory=lambda: os.getenv("LMSTUDIO_BASE_URL", "http://192.168.122.54:8888/v1"))
    timeout_seconds: float = 8.0


class PiperConfig(BaseModel):
    enabled: bool = True
    model_path: str = Field(default_factory=lambda: os.getenv("PIPER_MODEL_PATH", "/app/voices/piper/en_GB-alan-medium.onnx"))


class KokoroVoicesConfig(BaseModel):
    bm_george: str = Field(default="/app/voices/kokoro/bm_george/model")
    bm_daniel: str = Field(default="/app/voices/kokoro/bm_daniel/model")
    bf_emma: str = Field(default="/app/voices/kokoro/bf_emma/model")
    bf_isabella: str = Field(default="/app/voices/kokoro/bf_isabella/model")


class BundledTTSConfig(BaseModel):
    enabled: bool = True
    base_url: str = Field(default_factory=lambda: os.getenv("BUNDLED_TTS_BASE_URL", "http://bundled-tts:8001"))
    timeout_seconds: float = 60.0


class EngineConfig(BaseModel):
    provider: Literal["bundled", "external"] = Field(default_factory=lambda: os.getenv("TTS_PROVIDER", "bundled"))


class DefaultsConfig(BaseModel):
    voice_id: str = "uk-female-1"
    output_format: str = "wav-pcm-16k"
    amplitude: float = 1.0
    speed: float = 1.0


class AppConfig(BaseModel):
    custom_voices: Dict[str, VoiceConfig] = Field(default_factory=dict)
    engine: EngineConfig = Field(default_factory=EngineConfig)
    bundled_tts: BundledTTSConfig = Field(default_factory=BundledTTSConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    openwebui: OpenWebUIConfig = Field(default_factory=OpenWebUIConfig)
    lmstudio: LMStudioConfig = Field(default_factory=LMStudioConfig)
    piper: PiperConfig = Field(default_factory=PiperConfig)
    kokoro_voices: KokoroVoicesConfig = Field(default_factory=KokoroVoicesConfig)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)

    def redacted(self) -> Dict[str, Any]:
        data = self.model_dump()
        if data.get("openwebui", {}).get("api_key"):
            data["openwebui"]["api_key"] = "***redacted***"
        return data


def config_dir() -> Path:
    return Path(os.getenv("BRITISHTTS_CONFIG_DIR", "/app/config"))


def output_dir() -> Path:
    return Path(os.getenv("BRITISHTTS_OUTPUT_DIR", "/app/output"))


def sample_dir() -> Path:
    return Path(os.getenv("BRITISHTTS_SAMPLE_DIR", "/app/voices/samples"))


def load_config(path: Path | None = None) -> AppConfig:
    if path is None:
        path = config_dir() / "config.json"
    if not path.exists():
        return AppConfig()
    raw = json.loads(path.read_text())
    return AppConfig.model_validate(raw)


def save_config(config: AppConfig, path: Path | None = None) -> None:
    if path is None:
        path = config_dir() / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.model_dump(), indent=2) + "\n")
