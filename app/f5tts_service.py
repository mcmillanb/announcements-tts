from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

logger = logging.getLogger(__name__)


class F5SynthesisRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    ref_audio: str
    speed: float = Field(1.0, ge=0.5, le=2.0)


def _resolve_device() -> str:
    d = os.getenv("ANNOUNCEMENTTTS_DEVICE", os.getenv("BRITISHTTS_DEVICE", "auto")).strip().lower()
    if d == "cpu":
        return "cpu"
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def create_app() -> FastAPI:
    app = FastAPI(title="Announcement TTS F5-TTS Service", version="0.1.0")
    synth_lock = asyncio.Lock()
    _state: dict = {}

    def _get_model():
        if "model" not in _state:
            from f5_tts.api import F5TTS
            device = _resolve_device()
            logger.info("Loading F5-TTS model on device=%s (first request — may download ~1.2 GB)", device)
            _state["model"] = F5TTS(device=device)
            _state["device"] = device
            logger.info("F5-TTS model ready")
        return _state["model"]

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "engine": {
                "device": _state.get("device", _resolve_device()),
                "model_loaded": "model" in _state,
            },
        }

    @app.post("/synthesise")
    async def synthesise(req: F5SynthesisRequest):
        ref_path = Path(req.ref_audio)
        if not ref_path.exists():
            raise HTTPException(400, f"Reference audio not found: {req.ref_audio}")

        async with synth_lock:
            td = tempfile.TemporaryDirectory()
            out = Path(td.name) / "output.wav"
            try:
                model = _get_model()
                wav, sr, _ = model.infer(
                    ref_file=str(ref_path),
                    ref_text="",
                    gen_text=req.text,
                    speed=req.speed,
                    show_info=logger.info,
                    file_wave=str(out),
                )
                if not out.exists() or out.stat().st_size <= 44:
                    # infer didn't write the file; write the returned array
                    import soundfile as sf
                    sf.write(str(out), wav, sr)
                if not out.exists() or out.stat().st_size <= 44:
                    td.cleanup()
                    raise HTTPException(503, "F5-TTS did not produce audio")
                return FileResponse(out, media_type="audio/wav", background=BackgroundTask(td.cleanup))
            except HTTPException:
                td.cleanup()
                raise
            except Exception as exc:
                td.cleanup()
                logger.exception("F5-TTS synthesis error")
                raise HTTPException(503, f"F5-TTS synthesis failed: {exc}")

    return app


app = create_app()
