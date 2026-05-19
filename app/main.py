from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from app.adapters.kokoro_native import KokoroNativeTTSClient
from app.adapters.lmstudio import LMStudioTTSClient
from app.adapters.piper import PiperTTSClient
from app.audio import OUTPUT_FORMATS, convert_audio, extension_for, generate_fallback_wav, mime_for
from app.config import load_config
from app.voices import VoiceRegistry


class SynthesisRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    voice_id: Optional[str] = None
    output_format: Optional[str] = None
    amplitude: float = Field(1.0, ge=0.1, le=3.0)
    speed: float = Field(1.0, ge=0.5, le=2.0)
    use_ollama: bool = False
    filename: Optional[str] = None


def _dir(name: str, default: str) -> Path:
    return Path(os.getenv(name, default))


def _safe_base(name: Optional[str]) -> str:
    if not name:
        return uuid.uuid4().hex
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip(".-")
    return cleaned or uuid.uuid4().hex


def create_app() -> FastAPI:
    config = load_config()
    registry = VoiceRegistry(config)
    output_dir = _dir("BRITISHTTS_OUTPUT_DIR", "output")
    sample_dir = _dir("BRITISHTTS_SAMPLE_DIR", "voices/samples")
    synth_lock = asyncio.Lock()

    app = FastAPI(title="British TTS", version="0.1.0")

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "engine": {
                "piper_enabled": config.piper.enabled,
                "piper_model_path": config.piper.model_path,
                "piper_model_available": Path(config.piper.model_path).exists(),
                "lmstudio_enabled": config.lmstudio.enabled,
                "lmstudio_base_url": config.lmstudio.base_url,
                "fallback_available": True,
            },
            "formats": list(OUTPUT_FORMATS),
        }

    @app.get("/voices")
    async def voices():
        return {"voices": [v.as_dict() for v in registry.list_voices()]}

    @app.get("/config")
    async def get_config():
        return config.redacted()

    @app.get("/ui", response_class=HTMLResponse)
    async def ui():
        html_path = Path(__file__).parent / "static" / "ui.html"
        return HTMLResponse(html_path.read_text())

    @app.post("/upload-sample")
    async def upload_sample(file: UploadFile = File(...)):
        suffix = Path(file.filename or "sample.wav").suffix.lower()
        if suffix not in {".wav", ".mp3", ".flac"}:
            raise HTTPException(400, "Only WAV, MP3, and FLAC samples are accepted")
        sample_dir.mkdir(parents=True, exist_ok=True)
        dest = sample_dir / f"{uuid.uuid4().hex}{suffix}"
        with dest.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)
        return {"filename": dest.name, "path": str(dest)}

    @app.post("/synthesise")
    async def synthesise(req: SynthesisRequest):
        voice_id = req.voice_id or config.defaults.voice_id
        out_fmt = req.output_format or config.defaults.output_format
        if out_fmt not in OUTPUT_FORMATS:
            raise HTTPException(422, f"Unsupported output_format: {out_fmt}")
        voice = registry.get(voice_id)
        if not voice:
            raise HTTPException(404, f"Unknown voice_id: {voice_id}")
        output_dir.mkdir(parents=True, exist_ok=True)
        # Always write to a unique filename. FileResponse streams after this handler
        # returns, so concurrent requests using the same requested filename can
        # otherwise overwrite/truncate the file while it is being sent.
        final_path = output_dir / f"{_safe_base(req.filename)}_{uuid.uuid4().hex[:8]}{extension_for(out_fmt)}"

        async with synth_lock:
            with tempfile.TemporaryDirectory() as td:
                raw = Path(td) / "raw.wav"
                produced = None
                speaker = voice.speaker or voice.id
                kokoro = KokoroNativeTTSClient(enabled=True)
                produced = kokoro.synthesise_sync(req.text, speaker, raw, speed=req.speed)
                if produced is None and config.piper.enabled:
                    piper = PiperTTSClient(config.piper.model_path)
                    produced = piper.synthesise(req.text, raw, speed=req.speed)
                if produced is None and config.lmstudio.enabled:
                    lm = LMStudioTTSClient(config.lmstudio.base_url, timeout=config.lmstudio.timeout_seconds)
                    produced = await lm.synthesise(req.text, speaker, raw, speed=req.speed)
                if produced is None:
                    generate_fallback_wav(req.text, raw)
                convert_audio(raw, final_path, out_fmt, amplitude=req.amplitude)

        return FileResponse(
            final_path,
            media_type=mime_for(out_fmt),
            filename=final_path.name,
            headers={"Content-Disposition": f'attachment; filename="{final_path.name}"'},
        )

    return app


app = create_app()
