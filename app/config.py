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
    timeout_seconds: float = 8.0


class OpenWebUIConfig(BaseModel):
    enabled: bool = False
    base_url: str = "http://host.docker.internal:3000"
    api_key: str = ""
    model: str = "tts-1"
    timeout_seconds: float = 8.0


class LMStudioConfig(BaseModel):
    enabled: bool = True
    base_url: str = Field(default_factory=lambda: os.getenv("LMSTUDIO_BASE_URL", "http://host.docker.internal:1234/v1"))
    model: str = ""
    timeout_seconds: float = 8.0


class OpenAIConfig(BaseModel):
    enabled: bool = False
    base_url: str = Field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    model: str = "tts-1"
    timeout_seconds: float = 30.0


class CustomExternalConfig(BaseModel):
    enabled: bool = False
    base_url: str = "http://host.docker.internal:1234/v1"
    api_key: str = ""
    model: str = "tts-1"
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


class F5TTSConfig(BaseModel):
    enabled: bool = True
    base_url: str = Field(default_factory=lambda: os.getenv("F5TTS_BASE_URL", "http://f5-tts:8002"))
    timeout_seconds: float = 300.0


class EngineConfig(BaseModel):
    provider: Literal["bundled", "external"] = Field(default_factory=lambda: os.getenv("TTS_PROVIDER", "bundled"))
    external_provider: Literal["lmstudio", "openai", "ollama", "openwebui", "custom"] = Field(
        default_factory=lambda: os.getenv("TTS_EXTERNAL_PROVIDER", "lmstudio")
    )


class DefaultsConfig(BaseModel):
    voice_id: str = "uk-female-1"
    output_format: str = "wav-pcm-16k"
    amplitude: float = 1.0
    speed: float = 1.0
    pitch: float = 0.0


class AppConfig(BaseModel):
    custom_voices: Dict[str, VoiceConfig] = Field(default_factory=dict)
    engine: EngineConfig = Field(default_factory=EngineConfig)
    bundled_tts: BundledTTSConfig = Field(default_factory=BundledTTSConfig)
    f5tts: F5TTSConfig = Field(default_factory=F5TTSConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    openwebui: OpenWebUIConfig = Field(default_factory=OpenWebUIConfig)
    lmstudio: LMStudioConfig = Field(default_factory=LMStudioConfig)
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    custom_external: CustomExternalConfig = Field(default_factory=CustomExternalConfig)
    piper: PiperConfig = Field(default_factory=PiperConfig)
    kokoro_voices: KokoroVoicesConfig = Field(default_factory=KokoroVoicesConfig)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)

    def redacted(self) -> Dict[str, Any]:
        data = self.model_dump()
        if data.get("openwebui", {}).get("api_key"):
            data["openwebui"]["api_key"] = "***redacted***"
        if data.get("openai", {}).get("api_key"):
            data["openai"]["api_key"] = "***redacted***"
        if data.get("custom_external", {}).get("api_key"):
            data["custom_external"]["api_key"] = "***redacted***"
        return data

    def external_tts_settings(self) -> Dict[str, Any]:
        provider = self.engine.external_provider
        if provider == "openai":
            return {
                "provider": provider,
                "enabled": self.openai.enabled,
                "base_url": self.openai.base_url,
                "api_key": self.openai.api_key,
                "model": self.openai.model,
                "timeout_seconds": self.openai.timeout_seconds,
            }
        if provider == "ollama":
            return {
                "provider": provider,
                "enabled": self.ollama.enabled,
                "base_url": self.ollama.base_url.rstrip("/") + "/v1",
                "api_key": "",
                "model": self.ollama.model,
                "timeout_seconds": self.ollama.timeout_seconds,
            }
        if provider == "openwebui":
            return {
                "provider": provider,
                "enabled": self.openwebui.enabled,
                "base_url": self.openwebui.base_url,
                "api_key": self.openwebui.api_key,
                "model": self.openwebui.model,
                "timeout_seconds": self.openwebui.timeout_seconds,
            }
        if provider == "custom":
            return {
                "provider": provider,
                "enabled": self.custom_external.enabled,
                "base_url": self.custom_external.base_url,
                "api_key": self.custom_external.api_key,
                "model": self.custom_external.model,
                "timeout_seconds": self.custom_external.timeout_seconds,
            }
        return {
            "provider": "lmstudio",
            "enabled": self.lmstudio.enabled,
            "base_url": self.lmstudio.base_url,
            "api_key": "",
            "model": self.lmstudio.model,
            "timeout_seconds": self.lmstudio.timeout_seconds,
        }


def _env_path(generic_name: str, legacy_name: str, default: str) -> Path:
    return Path(os.getenv(generic_name, os.getenv(legacy_name, default)))


def config_dir() -> Path:
    return _env_path("ANNOUNCEMENTTTS_CONFIG_DIR", "BRITISHTTS_CONFIG_DIR", "/app/config")


def output_dir() -> Path:
    return _env_path("ANNOUNCEMENTTTS_OUTPUT_DIR", "BRITISHTTS_OUTPUT_DIR", "/app/output")


def sample_dir() -> Path:
    return _env_path("ANNOUNCEMENTTTS_SAMPLE_DIR", "BRITISHTTS_SAMPLE_DIR", "/app/voices/samples")


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
