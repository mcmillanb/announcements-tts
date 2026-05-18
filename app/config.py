from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

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


class DefaultsConfig(BaseModel):
    voice_id: str = "uk-female-1"
    output_format: str = "wav-pcm-16k"
    amplitude: float = 1.0
    speed: float = 1.0


class AppConfig(BaseModel):
    custom_voices: Dict[str, VoiceConfig] = Field(default_factory=dict)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    openwebui: OpenWebUIConfig = Field(default_factory=OpenWebUIConfig)
    lmstudio: LMStudioConfig = Field(default_factory=LMStudioConfig)
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
