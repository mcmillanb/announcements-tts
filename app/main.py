from __future__ import annotations

import asyncio
import csv
import io
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Optional

import httpx
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from app.adapters.bundled_remote import BundledRemoteTTSClient
from app.adapters.f5tts import F5TTSClient
from app.adapters.lmstudio import LMStudioTTSClient
from app.audio import (
    OUTPUT_FORMATS,
    concatenate_wavs,
    convert_audio,
    extension_for,
    generate_silence_wav,
    generate_tone_wav,
    mime_for,
)
from app.config import AppConfig, VoiceConfig, load_config, save_config
from app.voices import VoiceRegistry


class SynthesisRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    voice_id: Optional[str] = None
    output_format: Optional[str] = None
    amplitude: float = Field(1.0, ge=0.1, le=3.0)
    speed: float = Field(1.0, ge=0.5, le=2.0)
    pitch: float = Field(0.0, ge=-12.0, le=12.0)
    use_ollama: bool = False
    filename: Optional[str] = None


class ToneRequest(BaseModel):
    frequency_hz: float = Field(440.0, ge=20.0, le=20000.0)
    beep_seconds: float = Field(0.25, ge=0.01, le=60.0)
    total_seconds: float = Field(1.0, ge=0.01, le=300.0)
    silence_before_seconds: float = Field(0.0, ge=0.0, le=300.0)
    silence_after_seconds: float = Field(0.0, ge=0.0, le=300.0)
    amplitude: float = Field(0.8, ge=0.0, le=1.0)
    output_format: Optional[str] = None
    filename: Optional[str] = None


class BulkJob(BaseModel):
    id: str
    total: int
    current: int = 0
    status: str = "queued"
    message: str = "Queued"
    download_url: Optional[str] = None
    error: Optional[str] = None


PAUSE_MARKER_RE = re.compile(r"\[(?:pause|silence)(?::\s*(\d+(?:\.\d+)?))?\]", re.IGNORECASE)


def _dir(name: str, default: str) -> Path:
    generic_name = name.replace("BRITISHTTS_", "ANNOUNCEMENTTTS_", 1)
    return Path(os.getenv(generic_name, os.getenv(name, default)))


def _safe_base(name: Optional[str]) -> str:
    if not name:
        return uuid.uuid4().hex
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip(".-")
    return cleaned or uuid.uuid4().hex


def _archive_filename(name: Optional[str], output_format: str) -> str:
    base = _safe_base(name)
    suffix = extension_for(output_format)
    if not base.lower().endswith(suffix):
        base = f"{base}{suffix}"
    return base


def _csv_rows(raw: bytes) -> list[dict[str, str]]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "CSV must be UTF-8 encoded") from exc
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "CSV must include Text and Filename columns")
    columns = {name.strip().lower(): name for name in reader.fieldnames if name}
    if "text" not in columns or "filename" not in columns:
        raise HTTPException(400, "CSV must include Text and Filename columns")
    rows = []
    for index, row in enumerate(reader, start=2):
        item_text = (row.get(columns["text"]) or "").strip()
        filename = (row.get(columns["filename"]) or "").strip()
        if not item_text and not filename:
            continue
        if not item_text:
            raise HTTPException(400, f"Missing Text value on CSV row {index}")
        if not filename:
            raise HTTPException(400, f"Missing Filename value on CSV row {index}")
        rows.append({"text": item_text, "filename": filename})
    if not rows:
        raise HTTPException(400, "CSV does not contain any announcement rows")
    return rows


def _speech_parts(text: str) -> list[str | float]:
    parts: list[str | float] = []
    cursor = 0
    for match in PAUSE_MARKER_RE.finditer(text):
        before = text[cursor : match.start()].strip()
        if before:
            parts.append(before)
        seconds = float(match.group(1) or 1.0)
        parts.append(min(10.0, max(0.1, seconds)))
        cursor = match.end()
    after = text[cursor:].strip()
    if after:
        parts.append(after)
    return parts or [text]


async def _render_speech(
    config: AppConfig,
    registry: VoiceRegistry,
    req: SynthesisRequest,
    final_path: Path,
    synth_lock: asyncio.Lock,
) -> None:
    voice_id = req.voice_id or config.defaults.voice_id
    out_fmt = req.output_format or config.defaults.output_format
    if out_fmt not in OUTPUT_FORMATS:
        raise HTTPException(422, f"Unsupported output_format: {out_fmt}")
    voice = registry.get(voice_id)
    if not voice:
        raise HTTPException(404, f"Unknown voice_id: {voice_id}")

    async with synth_lock:
        with tempfile.TemporaryDirectory() as td:
            async def render_segment(text: str, path: Path) -> None:
                produced = None
                if voice.type == "clone" and voice.sample_file:
                    if not config.f5tts.enabled:
                        raise HTTPException(503, "F5-TTS is not enabled; cannot use clone voice")
                    f5 = F5TTSClient(config.f5tts.base_url, timeout=config.f5tts.timeout_seconds)
                    produced = await f5.synthesise(text, voice.sample_file, path, speed=req.speed)
                    if produced is None:
                        raise HTTPException(503, "F5-TTS service unavailable — is the f5-tts container running?")
                else:
                    speaker = voice.speaker or voice.id
                    if config.engine.provider == "bundled" and config.bundled_tts.enabled:
                        bundled = BundledRemoteTTSClient(
                            config.bundled_tts.base_url,
                            timeout=config.bundled_tts.timeout_seconds,
                        )
                        produced = await bundled.synthesise(text, speaker, path, speed=req.speed)
                    external = config.external_tts_settings()
                    if produced is None and config.engine.provider == "external" and external["enabled"]:
                        lm = LMStudioTTSClient(
                            external["base_url"],
                            timeout=external["timeout_seconds"],
                            api_key=external["api_key"],
                            model=external["model"],
                        )
                        produced = await lm.synthesise(text, speaker, path, speed=req.speed)
                    if produced is None:
                        raise HTTPException(503, "TTS provider did not produce audio")

            raw = Path(td) / "raw.wav"
            rendered_parts = []
            for index, part in enumerate(_speech_parts(req.text)):
                part_path = Path(td) / f"part-{index}.wav"
                if isinstance(part, float):
                    generate_silence_wav(part_path, part)
                else:
                    await render_segment(part, part_path)
                rendered_parts.append(part_path)
            if len(rendered_parts) == 1:
                raw = rendered_parts[0]
            else:
                concatenate_wavs(rendered_parts, raw)
            convert_audio(raw, final_path, out_fmt, amplitude=req.amplitude, pitch_semitones=req.pitch)


def create_app() -> FastAPI:
    config_state = {"config": load_config()}
    registry_state = {"registry": VoiceRegistry(config_state["config"])}
    output_dir = _dir("BRITISHTTS_OUTPUT_DIR", "output")
    sample_dir = _dir("BRITISHTTS_SAMPLE_DIR", "voices/samples")
    synth_lock = asyncio.Lock()
    bulk_jobs: dict[str, BulkJob] = {}

    app = FastAPI(title="Announcement TTS", version="0.1.0")

    @app.get("/health")
    async def health():
        config = config_state["config"]
        external = config.external_tts_settings()
        provider_status = "unknown"
        provider_message = ""
        if config.engine.provider == "bundled":
            if not config.bundled_tts.enabled:
                provider_status = "disabled"
                provider_message = "Bundled provider is disabled"
            else:
                try:
                    async with httpx.AsyncClient(base_url=config.bundled_tts.base_url.rstrip("/"), timeout=2.0) as client:
                        resp = await client.get("/health")
                    provider_status = "ready" if resp.status_code < 400 else "unavailable"
                    provider_message = "" if resp.status_code < 400 else f"Bundled provider returned HTTP {resp.status_code}"
                except Exception as exc:
                    provider_status = "unavailable"
                    provider_message = f"Bundled provider is unreachable at {config.bundled_tts.base_url}: {exc}"
        elif external["enabled"]:
            provider_status = "configured"
            provider_message = f"External provider configured at {external['base_url']}"
        else:
            provider_status = "disabled"
            provider_message = "Selected external provider is disabled"
        return {
            "status": "ok",
            "engine": {
                "provider": config.engine.provider,
                "external_provider": external["provider"],
                "bundled_tts_enabled": config.bundled_tts.enabled,
                "bundled_tts_base_url": config.bundled_tts.base_url,
                "external_tts_enabled": external["enabled"],
                "external_tts_base_url": external["base_url"],
                "tts_status": provider_status,
                "tts_status_message": provider_message,
            },
            "formats": list(OUTPUT_FORMATS),
        }

    @app.get("/voices")
    async def voices():
        registry = registry_state["registry"]
        return {"voices": [v.as_dict() for v in registry.list_voices()]}

    @app.get("/config")
    async def get_config():
        config = config_state["config"]
        return config.redacted()

    @app.post("/config")
    async def update_config(next_config: AppConfig):
        current = config_state["config"]
        if next_config.openwebui.api_key == "***redacted***":
            next_config.openwebui.api_key = current.openwebui.api_key
        if next_config.openai.api_key == "***redacted***":
            next_config.openai.api_key = current.openai.api_key
        if next_config.custom_external.api_key == "***redacted***":
            next_config.custom_external.api_key = current.custom_external.api_key
        save_config(next_config)
        config_state["config"] = next_config
        registry_state["registry"] = VoiceRegistry(next_config)
        return next_config.redacted()

    @app.get("/ui", response_class=HTMLResponse)
    async def ui():
        html_path = Path(__file__).parent / "static" / "ui.html"
        return HTMLResponse(html_path.read_text())

    @app.post("/upload-sample")
    async def upload_sample(file: UploadFile = File(...), label: str = Form("")):
        suffix = Path(file.filename or "sample.wav").suffix.lower()
        if suffix not in {".wav", ".mp3", ".flac"}:
            raise HTTPException(400, "Only WAV, MP3, and FLAC samples are accepted")
        sample_dir.mkdir(parents=True, exist_ok=True)
        dest = sample_dir / f"{uuid.uuid4().hex}{suffix}"
        with dest.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)

        effective_label = label.strip() or Path(file.filename or "My Voice").stem
        base_id = re.sub(r"[^a-z0-9]+", "-", effective_label.lower()).strip("-") or uuid.uuid4().hex[:8]
        config = config_state["config"]
        voice_id = base_id
        counter = 1
        while voice_id in config.custom_voices:
            voice_id = f"{base_id}-{counter}"
            counter += 1
        config.custom_voices[voice_id] = VoiceConfig(label=effective_label, sample_file=str(dest))
        save_config(config)
        registry_state["registry"] = VoiceRegistry(config)

        return {"voice_id": voice_id, "label": effective_label}

    @app.post("/synthesise")
    async def synthesise(req: SynthesisRequest):
        config = config_state["config"]
        registry = registry_state["registry"]
        out_fmt = req.output_format or config.defaults.output_format
        if out_fmt not in OUTPUT_FORMATS:
            raise HTTPException(422, f"Unsupported output_format: {out_fmt}")
        output_dir.mkdir(parents=True, exist_ok=True)
        # Always write to a unique filename. FileResponse streams after this handler
        # returns, so concurrent requests using the same requested filename can
        # otherwise overwrite/truncate the file while it is being sent.
        final_path = output_dir / f"{_safe_base(req.filename)}_{uuid.uuid4().hex[:8]}{extension_for(out_fmt)}"

        await _render_speech(config, registry, req, final_path, synth_lock)

        return FileResponse(
            final_path,
            media_type=mime_for(out_fmt),
            filename=final_path.name,
            headers={"Content-Disposition": f'attachment; filename="{final_path.name}"'},
        )

    @app.post("/tone")
    async def tone(req: ToneRequest):
        out_fmt = req.output_format or config_state["config"].defaults.output_format
        if out_fmt not in OUTPUT_FORMATS:
            raise HTTPException(422, f"Unsupported output_format: {out_fmt}")
        output_dir.mkdir(parents=True, exist_ok=True)
        final_path = output_dir / f"{_safe_base(req.filename or 'tone')}_{uuid.uuid4().hex[:8]}{extension_for(out_fmt)}"
        with tempfile.TemporaryDirectory() as td:
            raw = Path(td) / "tone.wav"
            generate_tone_wav(
                raw,
                frequency_hz=req.frequency_hz,
                beep_seconds=req.beep_seconds,
                total_seconds=req.total_seconds,
                silence_before_seconds=req.silence_before_seconds,
                silence_after_seconds=req.silence_after_seconds,
                amplitude=req.amplitude,
            )
            convert_audio(raw, final_path, out_fmt)
        return FileResponse(
            final_path,
            media_type=mime_for(out_fmt),
            filename=final_path.name,
            headers={"Content-Disposition": f'attachment; filename="{final_path.name}"'},
        )

    async def run_bulk_job(job_id: str, rows: list[dict[str, str]], req: SynthesisRequest) -> None:
        job = bulk_jobs[job_id]
        config = config_state["config"]
        registry = registry_state["registry"]
        out_fmt = req.output_format or config.defaults.output_format
        work_dir = output_dir / f"bulk_{job_id}"
        zip_path = output_dir / f"announcement-tts-bulk-{job_id}.zip"
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            work_dir.mkdir(parents=True, exist_ok=True)
            job.status = "running"
            used_names: set[str] = set()
            audio_paths: list[tuple[Path, str]] = []
            for index, row in enumerate(rows, start=1):
                archive_name = _archive_filename(row["filename"], out_fmt)
                if archive_name in used_names:
                    stem = Path(archive_name).stem
                    suffix = Path(archive_name).suffix
                    archive_name = f"{stem}-{index}{suffix}"
                used_names.add(archive_name)
                job.current = index
                job.message = f"Creating announcement {index} of {job.total}"
                item_req = req.model_copy(update={"text": row["text"], "filename": row["filename"]})
                item_path = work_dir / f"{uuid.uuid4().hex}{extension_for(out_fmt)}"
                await _render_speech(config, registry, item_req, item_path, synth_lock)
                audio_paths.append((item_path, archive_name))

            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for audio_path, archive_name in audio_paths:
                    archive.write(audio_path, archive_name)
            shutil.rmtree(work_dir, ignore_errors=True)
            job.status = "complete"
            job.current = job.total
            job.message = f"Created {job.total} announcements"
            job.download_url = f"/bulk-synthesise/{job_id}/download"
        except Exception as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            job.status = "failed"
            job.error = str(exc)
            job.message = "Bulk synthesis failed"

    @app.post("/bulk-synthesise")
    async def bulk_synthesise(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        voice_id: Optional[str] = Form(None),
        output_format: Optional[str] = Form(None),
        amplitude: float = Form(1.0),
        speed: float = Form(1.0),
        pitch: float = Form(0.0),
    ):
        suffix = Path(file.filename or "").suffix.lower()
        if suffix != ".csv":
            raise HTTPException(400, "Bulk synthesis requires a .csv file")
        rows = _csv_rows(await file.read())
        req = SynthesisRequest(
            text=rows[0]["text"],
            voice_id=voice_id,
            output_format=output_format,
            amplitude=amplitude,
            speed=speed,
            pitch=pitch,
        )
        out_fmt = req.output_format or config_state["config"].defaults.output_format
        if out_fmt not in OUTPUT_FORMATS:
            raise HTTPException(422, f"Unsupported output_format: {out_fmt}")
        if not registry_state["registry"].get(req.voice_id or config_state["config"].defaults.voice_id):
            raise HTTPException(404, f"Unknown voice_id: {req.voice_id}")
        job_id = uuid.uuid4().hex
        bulk_jobs[job_id] = BulkJob(id=job_id, total=len(rows))
        background_tasks.add_task(run_bulk_job, job_id, rows, req)
        return bulk_jobs[job_id].model_dump()

    @app.get("/bulk-synthesise/{job_id}/status")
    async def bulk_status(job_id: str):
        job = bulk_jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Unknown bulk synthesis job")
        return job.model_dump()

    @app.get("/bulk-synthesise/{job_id}/download")
    async def bulk_download(job_id: str):
        job = bulk_jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Unknown bulk synthesis job")
        if job.status != "complete":
            raise HTTPException(409, "Bulk synthesis job is not complete")
        zip_path = output_dir / f"announcement-tts-bulk-{job_id}.zip"
        if not zip_path.exists():
            raise HTTPException(404, "Bulk synthesis zip is no longer available")
        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename="announcement-tts-bulk.zip",
            headers={"Content-Disposition": 'attachment; filename="announcement-tts-bulk.zip"'},
        )

    return app


app = create_app()
