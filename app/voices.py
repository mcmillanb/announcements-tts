from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.config import AppConfig


@dataclass(frozen=True)
class Voice:
    id: str
    label: str
    type: str
    language: str = "en"
    speaker: Optional[str] = None
    sample_file: Optional[str] = None

    def as_dict(self) -> dict:
        data = {"id": self.id, "label": self.label, "type": self.type, "language": self.language}
        if self.speaker:
            data["speaker"] = self.speaker
        if self.sample_file:
            data["sample_file"] = self.sample_file
        return data


BUILTIN_VOICES = {
    "uk-male-1": Voice("uk-male-1", "British Male – Calm", "builtin", speaker="bm_george"),
    "uk-male-2": Voice("uk-male-2", "British Male – Warm", "builtin", speaker="bm_daniel"),
    "uk-female-1": Voice("uk-female-1", "British Female – Clear", "builtin", speaker="bf_emma"),
    "uk-female-2": Voice("uk-female-2", "British Female – Warm", "builtin", speaker="bf_isabella"),
}


class VoiceRegistry:
    def __init__(self, config: AppConfig):
        self._voices = dict(BUILTIN_VOICES)
        for voice_id, spec in config.custom_voices.items():
            sample_file = spec.sample_file
            if not sample_file or not Path(sample_file).exists():
                continue
            self._voices[voice_id] = Voice(
                id=voice_id,
                label=spec.label or voice_id,
                type="clone",
                language=spec.language or "en",
                sample_file=sample_file,
            )

    def list_voices(self) -> list[Voice]:
        return list(self._voices.values())

    def get(self, voice_id: str) -> Optional[Voice]:
        return self._voices.get(voice_id)
