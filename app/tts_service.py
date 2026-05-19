from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from fastapi import FastAPI
from starlette.background import BackgroundTask
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.adapters.kokoro_native import KokoroNativeTTSClient
from app.adapters.piper import PiperTTSClient
from app.audio import generate_fallback_wav
from app.config import load_config


class BundledSynthesisRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    voice: str = "bf_emma"
    speed: float = Field(1.0, ge=0.5, le=2.0)


def create_app() -> FastAPI:
    config = load_config()
    synth_lock = asyncio.Lock()
    kokoro = KokoroNativeTTSClient(enabled=True)
    piper = PiperTTSClient(config.piper.model_path)

    app = FastAPI(title="British TTS Bundled Models", version="0.1.0")

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "engine": {
                "kokoro_enabled": True,
                "piper_enabled": config.piper.enabled,
                "piper_model_path": config.piper.model_path,
                "piper_model_available": Path(config.piper.model_path).exists(),
                "fallback_available": True,
            },
        }

    @app.post("/synthesise")
    async def synthesise(req: BundledSynthesisRequest):
        async with synth_lock:
            td = tempfile.TemporaryDirectory()
            raw = Path(td.name) / "raw.wav"
            produced = kokoro.synthesise_sync(req.text, req.voice, raw, speed=req.speed)
            if produced is None and config.piper.enabled:
                produced = piper.synthesise(req.text, raw, speed=req.speed)
            if produced is None:
                generate_fallback_wav(req.text, raw)
            return FileResponse(raw, media_type="audio/wav", background=BackgroundTask(td.cleanup))

    return app


app = create_app()
