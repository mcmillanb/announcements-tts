import asyncio
import uuid
from pathlib import Path

from app.adapters.kokoro_native import KokoroNativeTTSClient
from app.adapters.lmstudio import LMStudioTTSClient
from app.adapters.piper import PiperTTSClient
from app.audio import OUTPUT_FORMATS, convert_audio, generate_fallback_wav
from app.config import AppConfig
from app.schemas import SynthesiseRequest
from app.voices import Voice


class Synthesiser:
    def __init__(self, config: AppConfig, output_dir: Path):
        self.config = config
        self.output_dir = output_dir
        self.lock = asyncio.Lock()
        self.adapter = LMStudioTTSClient(config.lmstudio.base_url, config.lmstudio.timeout_seconds)
        self.kokoro = KokoroNativeTTSClient(enabled=True)
        self.piper = PiperTTSClient(config.piper.model_path)
        self.last_engine = "fallback"

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
            if produced is None and self.config.lmstudio.enabled:
                produced = await self.adapter.synthesise(request.text, speaker, tmp, request.speed)
                if produced is not None:
                    self.last_engine = "lmstudio"
            if produced is None:
                self.last_engine = "deterministic-fallback"
                generate_fallback_wav(request.text, tmp)

            convert_audio(tmp, final, request.output_format, amplitude=request.amplitude)
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
            return final
