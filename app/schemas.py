from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator

OutputFormat = Literal["wav-pcm-16k","wav-pcm-8k","wav-alaw-8k","wav-ulaw-8k","wav-alaw-16k","wav-ulaw-16k","wav-pcm-24k","mp3","flac","ogg"]


class SynthesiseRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    voice_id: str = "uk-female-1"
    output_format: OutputFormat = "wav-pcm-16k"
    amplitude: float = Field(1.0, ge=0.1, le=3.0)
    speed: float = Field(1.0, ge=0.5, le=2.0)
    pitch: float = Field(0.0, ge=-12.0, le=12.0)
    use_ollama: bool = False
    filename: Optional[str] = None

    @field_validator("filename")
    @classmethod
    def safe_filename(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return v
        cleaned = "".join(ch for ch in v if ch.isalnum() or ch in ("-", "_", "."))
        if not cleaned or cleaned in {".", ".."}:
            raise ValueError("filename must contain safe characters")
        return cleaned[:80]
