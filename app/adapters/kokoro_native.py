from __future__ import annotations

import logging
import os
import wave
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class KokoroNativeTTSClient:
    """Local Kokoro TTS adapter.

    The import is lazy so the app can still boot on systems where Kokoro is not
    installed. Built-in British voices use Kokoro's `b` language pipeline.
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._pipelines = {}
        self._available: Optional[bool] = None

    def _load_pipeline(self, lang_code: str):
        if lang_code in self._pipelines:
            return self._pipelines[lang_code]
        device = os.getenv("ANNOUNCEMENTTTS_DEVICE", os.getenv("BRITISHTTS_DEVICE", "auto")).strip().lower()
        if device == "cpu":
            os.environ["CUDA_VISIBLE_DEVICES"] = ""
        try:
            from kokoro import KPipeline  # type: ignore
        except Exception as exc:  # pragma: no cover - exact import failure varies by platform
            logger.info("Kokoro native TTS unavailable: %s", exc)
            self._available = False
            return None
        pipeline = KPipeline(lang_code=lang_code)
        self._pipelines[lang_code] = pipeline
        self._available = True
        return pipeline

    @staticmethod
    def _lang_code_for_voice(voice: str) -> str:
        # Kokoro voice prefixes: bf/bm = British English, af/am = American English.
        return "b" if voice.startswith(("bf_", "bm_")) else "a"

    @staticmethod
    def _write_wav(audio, output_path: Path, sample_rate: int = 24000) -> None:
        samples = audio.tolist() if hasattr(audio, "tolist") else list(audio)
        frames = []
        for sample in samples:
            try:
                value = float(sample)
            except (TypeError, ValueError):
                value = 0.0
            if value != value:  # NaN
                value = 0.0
            value = max(-1.0, min(1.0, value))
            frames.append(int(value * 32767.0).to_bytes(2, "little", signed=True))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(b"".join(frames))

    def synthesise_sync(self, text: str, voice: str, output_path: Path, speed: float = 1.0) -> Optional[Path]:
        if not self.enabled:
            return None
        pipeline = self._load_pipeline(self._lang_code_for_voice(voice))
        if pipeline is None:
            return None
        try:
            chunks = []
            for _graphemes, _phonemes, audio in pipeline(text, voice=voice, speed=speed):
                chunks.append(audio)
            if not chunks:
                return None
            if len(chunks) == 1:
                combined = chunks[0]
            else:
                combined = []
                for chunk in chunks:
                    combined.extend(chunk.tolist() if hasattr(chunk, "tolist") else list(chunk))
            self._write_wav(combined, output_path)
            return output_path
        except Exception as exc:
            logger.warning("Kokoro native synthesis failed, falling back: %s", exc)
            return None
