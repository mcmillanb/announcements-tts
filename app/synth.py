import asyncio
import uuid
from pathlib import Path

from app.adapters.kokoro_native import KokoroNativeTTSClient
from app.adapters.lmstudio import LMStudioTTSClient
from app.adapters.piper import PiperTTSClient
from fastapi import HTTPException

from app.audio import OUTPUT_FORMATS, convert_audio
from app.config import AppConfig
from app.schemas import SynthesiseRequest
from app.voices import Voice


class Synthesiser:
    def __init__(self, config: AppConfig, output_dir: Path):
        self.config = config
        self.output_dir = output_dir
        self.lock = asyncio.Lock()
        external = config.external_tts_settings()
        self.adapter = LMStudioTTSClient(
            external["base_url"],
            external["timeout_seconds"],
            api_key=external["api_key"],
            model=external["model"],
        )
        self.kokoro = KokoroNativeTTSClient(enabled=True)
        self.piper = PiperTTSClient(config.piper.model_path)
        self.last_engine = "none"

    async def synthesise(self, request: SynthesiseRequest, voice: Voice) -> Path:
        async with self.lock:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            fmt = OUTPUT_FORMATS[request.output_format]
            base = request.filename or f"tts_{uuid.uuid4().hex}"
            base = base.rsplit('.', 1)[0]
            tmp = self.output_dir / f".{base}_{uuid.uuid4().hex}_24k.wav"
            ext = str(fmt["ext"]).lstrip(".")
            final = self.output_dir / f"{base}.{ext}"
            if final.exists():
                final = self.output_dir / f"{base}_{uuid.uuid4().hex[:8]}.{ext}"

            produced = None
            speaker = voice.speaker or voice.id
            produced = self.kokoro.synthesise_sync(request.text, speaker, tmp, request.speed)
            if produced is not None:
                self.last_engine = "kokoro-native"
            if produced is None and self.config.piper.enabled:
                produced = self.piper.synthesise(request.text, tmp, request.speed)
                if produced is not None:
                    self.last_engine = "piper"
            external = self.config.external_tts_settings()
            if produced is None and external["enabled"]:
                produced = await self.adapter.synthesise(request.text, speaker, tmp, request.speed)
                if produced is not None:
                    self.last_engine = external["provider"]
            if produced is None:
                self.last_engine = "none"
                raise HTTPException(503, "TTS provider did not produce audio")

            convert_audio(tmp, final, request.output_format, amplitude=request.amplitude)
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
            return final
