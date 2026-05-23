# Announcement TTS System — Technical Specification

**Version 1.2 · Offline · Docker · NVIDIA CUDA · Voice Cloning · British English · Telephony Output**

---

## 1. Purpose & Scope

This document specifies the design, component selection, configuration, and API contract for a fully offline, containerised British English text-to-speech (TTS) service. The system supports built-in male and female British voices, zero-shot voice cloning from a short audio sample, telephony-grade output formats, tone generation, bulk synthesis, and pitch control.

The system runs on NVIDIA GPU hardware via Docker with the NVIDIA Container Toolkit. All inference occurs locally; no internet connection is required at runtime (model weights are cached in Docker volumes after first download).

---

## 2. TTS Engine Selection

### 2.1 Evaluation Matrix

| Engine | Quality | Cloning | British EN | Min VRAM | CUDA | Notes |
|---|---|---|---|---|---|---|
| **F5-TTS** | ★★★★★ | ✅ 10 s | ✅ Excellent | 8 GB | ✅ | **Voice cloning** — SOTA flow-matching, best naturalness |
| **Kokoro TTS** | ★★★★½ | ❌ | ✅ Purpose-built | 4 GB | ✅ | **Built-in voices** — bm_*/bf_* packs, very fast |
| Chatterbox (Resemble AI) | ★★★★½ | ✅ 5 s | ✅ Good | 8 GB | ✅ | Strong alternative — emotion control, Apache 2.0 |
| StyleTTS 2 | ★★★★½ | ✅ Zero-shot | ⚠️ Needs tuning | 8 GB | ✅ | Excellent prosody; less natural British accent out-of-box |
| XTTS-v2 (Coqui) | ★★★★ | ✅ 6 s | ✅ Good | 4 GB | ✅ | Mature ecosystem; superseded by F5 on quality |
| Parler TTS | ★★★★ | ❌ | ✅ Excellent | 8 GB | ✅ | Description-prompted style; no cloning support |
| MeloTTS | ★★★ | ❌ | ✅ Fast | 2 GB | ✅ | Lightweight fallback only |

### 2.2 Implemented Architecture

A dual-engine approach gives the best combination of built-in voice quality and cloning capability:

**Kokoro TTS — Built-in British voices**
- Purpose-built voice packs: `bm_george`, `bm_daniel` (male); `bf_emma`, `bf_isabella` (female)
- Extremely fast inference; ~300 MB model weight footprint
- Used for all `type: builtin` voices
- Repo: `hexgrad/Kokoro-82M` · Licence: Apache 2.0

**F5-TTS — Voice cloning engine**
- Flow-matching diffusion model; state-of-the-art naturalness
- Zero-shot voice cloning from ~10 s reference audio with no fine-tuning required
- Used when a `type: clone` voice (with a `sample_file`) is selected
- Repo: `SWivid/F5-TTS` · Licence: MIT · Model: ~1.2 GB

**Piper TTS — Offline fallback**
- Single-voice neural TTS (`en_GB-alan-medium`)
- No speaker selection; used only if Kokoro is unavailable in the bundled service

**Note on LLM usage:** Ollama / Open WebUI / LM Studio are optional external providers for OpenAI-compatible TTS APIs, not text normalisation. The main API can route synthesis to an external provider instead of the bundled service.

### 2.3 Docker & NVIDIA Compatibility

All engines are standard PyTorch/CUDA and fully compatible with containerised NVIDIA GPU deployment:

- Use the standard `python:3.12-slim` base image; PyTorch bundles its own CUDA runtime
- GPU passthrough via NVIDIA Container Toolkit and Docker Compose `deploy.resources`
- Falls back to CPU if `ANNOUNCEMENTTTS_DEVICE=cpu` or no GPU is detected
- Model weights cached in named Docker volumes to survive container rebuilds

---

## 3. System Architecture

### 3.1 Component Overview

| Component | Technology | Responsibility |
|---|---|---|
| API Server | FastAPI + Uvicorn | HTTP REST endpoints; request validation; file serving; bulk job queue |
| Bundled TTS Service | FastAPI + Kokoro + Piper | Built-in British voices; internal HTTP service on port 8001 |
| F5-TTS Service | FastAPI + F5-TTS | Voice cloning from reference audio; internal HTTP service on port 8002 |
| Audio Post-Processor | soundfile + FFmpeg | Amplitude scaling; pitch shifting; resampling; format/codec conversion |
| Telephony Encoder | FFmpeg (alaw/ulaw) | G.711 A-law and µ-law encoding; 8 kHz / 16 kHz output |
| Voice Registry | Python (voices.py) | Maps voice IDs to engine path (builtin → Kokoro, clone → F5-TTS) |
| Web UI | Vanilla HTML/JS | Synthesis, tone generation, voice upload, bulk jobs, configuration |
| Config Layer | config.json (volume) | Custom voice definitions; engine defaults; provider endpoints |

### 3.2 Request Flow

1. Client POSTs to `/synthesise` with text, voice_id, format, amplitude, speed, and pitch.
2. Voice registry resolves `voice_id`:
   - `type: builtin` → routes to bundled TTS service (Kokoro)
   - `type: clone` (has `sample_file`) → routes to F5-TTS service with the reference audio path
3. Text is split on `[pause:N]` / `[silence:N]` markers; each segment rendered separately.
4. Audio segments are concatenated into a single WAV buffer.
5. Audio post-processor applies amplitude multiplier and pitch shift.
6. FFmpeg resamples and re-encodes to the requested output format.
7. Final file is saved to `/app/output/` and streamed back to the client.

### 3.3 Multi-Container Layout

```
┌─────────────────────────────────────────────────────┐
│  Docker Compose stack                               │
│                                                     │
│  ┌──────────────────┐   :8001   ┌───────────────┐  │
│  │  tts (API)       │ ────────► │  bundled-tts  │  │
│  │  port 8765       │           │  Kokoro+Piper │  │
│  │                  │   :8002   └───────────────┘  │
│  │                  │ ────────► ┌───────────────┐  │
│  └──────────────────┘           │  f5-tts       │  │
│                                 │  F5-TTS clone │  │
│  voices/samples/ ───────────────►  (read-only)  │  │
│  (shared volume)                └───────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## 4. Voice Model

### 4.1 Built-In British Voices (Kokoro)

| Voice ID | Label | Kokoro Speaker | Character |
|---|---|---|---|
| `uk-male-1` | British Male – Calm | `bm_george` | Deep, measured, RP accent |
| `uk-male-2` | British Male – Warm | `bm_daniel` | Warmer, slightly faster cadence |
| `uk-female-1` | British Female – Clear | `bf_emma` | Clear, professional RP |
| `uk-female-2` | British Female – Warm | `bf_isabella` | Warmer, slightly softer |

### 4.2 Custom / Cloned Voices (F5-TTS)

Custom voices are registered via the web UI upload form or directly in `config.json`. Each entry maps a `voice_id` to a reference audio file accessible inside the container.

**Upload flow (web UI):**
1. Enter a voice name and select an audio file in the Voice Samples panel
2. Click **Upload & register** — the file is saved, the voice is registered in `config.json`, the registry reloads, and the voice appears in the dropdown immediately

**Reference audio requirements:**
- Format: WAV, MP3, or FLAC (WAV at 16–44 kHz mono preferred)
- Duration: 6–30 seconds; 10–20 s of clean speech optimal
- Minimal background noise; consistent volume; single speaker

**config.json example:**
```json
{
  "custom_voices": {
    "my-voice": {
      "label": "My Voice",
      "sample_file": "/app/voices/samples/abc123.wav",
      "language": "en"
    }
  }
}
```

Custom voices appear in `/voices` and the web UI voice selector with `type: clone`.

---

## 5. Output Formats

All synthesis is performed internally at 24 kHz mono. The post-processor resamples and re-encodes to the requested output format.

### 5.1 Format Matrix

| Format ID | Sample Rate | Codec | Container | Primary Use Case |
|---|---|---|---|---|
| `wav-alaw-8k` | 8 kHz | G.711 A-law | WAV | European/international PSTN; Cisco CUCM EMEA |
| `wav-ulaw-8k` | 8 kHz | G.711 µ-law | WAV | North American PSTN; Cisco CUCM NA |
| `wav-alaw-16k` | 16 kHz | G.711 A-law | WAV | Wideband A-law; modern IVR / contact centre |
| `wav-ulaw-16k` | 16 kHz | G.711 µ-law | WAV | Wideband µ-law; Cisco wideband prompts |
| `wav-pcm-16k` | 16 kHz | PCM 16-bit LE | WAV | Wideband VoIP; SIP; modern IVR |
| `wav-pcm-8k` | 8 kHz | PCM 16-bit LE | WAV | Narrowband telephony; legacy PSTN |
| `wav-pcm-24k` | 24 kHz | PCM 16-bit LE | WAV | Native synthesis rate; archival |
| `mp3` | 44.1 kHz | MP3 | MP3 | General purpose; web playback |
| `flac` | 24 kHz | FLAC lossless | FLAC | Lossless archival |
| `ogg` | 24 kHz | Vorbis | OGG | Web streaming |

### 5.2 Telephony Notes

All telephony outputs are forced to mono (`-ac 1`). Amplitude and pitch are applied on the 24 kHz buffer before resampling to avoid codec clipping artefacts.

---

## 6. API Contract

### 6.1 Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Engine status and provider readiness |
| GET | `/voices` | List all voices (built-in + custom) |
| POST | `/synthesise` | Text → audio file |
| POST | `/tone` | Generate beep/silence audio clip |
| POST | `/bulk-synthesise` | Submit CSV for background bulk synthesis |
| GET | `/bulk-job/{id}` | Poll bulk job status; returns download URL on completion |
| POST | `/upload-sample` | Upload a reference audio file and register a custom voice |
| GET | `/config` | Return current config (API keys redacted) |
| POST | `/config` | Update configuration |
| GET | `/ui` | Web interface |
| GET | `/docs` | Swagger UI |

### 6.2 POST /synthesise — Request Body

| Field | Type | Default | Description |
|---|---|---|---|
| `text` | string | required | Text to synthesise (max 5,000 chars); supports `[pause:N]` / `[silence:N]` markers |
| `voice_id` | string | config default | Voice identifier from `/voices` |
| `output_format` | enum | config default | Format ID from §5.1 |
| `amplitude` | float | `1.0` | Amplitude multiplier 0.1–3.0 |
| `speed` | float | `1.0` | Speech rate multiplier 0.5–2.0 |
| `pitch` | float | `0.0` | Pitch shift in semitones −12 to +12 |
| `filename` | string | auto UUID | Output filename base (no extension) |

**Response:** Binary audio stream with appropriate `Content-Type` and `Content-Disposition: attachment`. File also persisted to `/app/output/`.

### 6.3 POST /tone — Request Body

| Field | Type | Default | Description |
|---|---|---|---|
| `frequency_hz` | float | `440.0` | Tone frequency in Hz (20–20,000) |
| `beep_seconds` | float | `0.25` | Duration of the beep tone |
| `total_seconds` | float | `1.0` | Total clip duration including silence |
| `silence_before_seconds` | float | `0.0` | Leading silence |
| `silence_after_seconds` | float | `0.0` | Trailing silence |
| `amplitude` | float | `0.8` | Tone amplitude 0.0–1.0 |
| `output_format` | enum | config default | Format ID from §5.1 |
| `filename` | string | `tone` | Output filename base |

### 6.4 POST /upload-sample

Accepts `multipart/form-data` with:
- `file` — WAV, MP3, or FLAC audio file
- `label` — human-readable voice name (optional; defaults to filename stem)

Returns `{ "voice_id": "my-voice", "label": "My Voice" }`. The voice is registered in `config.json` and available for synthesis immediately.

### 6.5 GET /voices — Response

```json
{
  "voices": [
    { "id": "uk-male-1",   "label": "British Male – Calm",   "type": "builtin", "language": "en" },
    { "id": "uk-female-1", "label": "British Female – Clear", "type": "builtin", "language": "en" },
    { "id": "my-voice",    "label": "My Voice",               "type": "clone",   "language": "en" }
  ]
}
```

---

## 7. Configuration

### 7.1 config.json Schema

| Key | Type | Purpose |
|---|---|---|
| `custom_voices.*` | object | Map of `voice_id → {label, sample_file, language}` |
| `engine.provider` | string | `bundled` or `external` |
| `engine.external_provider` | string | `lmstudio`, `openai`, `ollama`, `openwebui`, or `custom` |
| `bundled_tts.base_url` | string | Internal bundled model service URL |
| `bundled_tts.timeout_seconds` | float | Synthesis timeout for built-in voices (default 60 s) |
| `f5tts.enabled` | bool | Enable/disable F5-TTS service (default `true`) |
| `f5tts.base_url` | string | Internal F5-TTS service URL (default `http://f5-tts:8002`) |
| `f5tts.timeout_seconds` | float | Synthesis timeout for cloned voices (default 300 s; CPU can take minutes) |
| `lmstudio.base_url` | string | LM Studio OpenAI-compatible endpoint |
| `openai.base_url` / `api_key` | string | OpenAI API endpoint and key |
| `defaults.voice_id` | string | Default voice |
| `defaults.output_format` | string | Default output format (e.g. `wav-alaw-8k` for telephony) |
| `defaults.amplitude` | float | Default amplitude (1.0) |
| `defaults.speed` | float | Default speech rate (1.0) |
| `defaults.pitch` | float | Default pitch shift in semitones (0.0) |

### 7.2 Full config.json Example

```json
{
  "custom_voices": {
    "my-voice": {
      "label": "My Voice",
      "sample_file": "/app/voices/samples/abc123.wav",
      "language": "en"
    }
  },
  "engine": {
    "provider": "bundled",
    "external_provider": "lmstudio"
  },
  "bundled_tts": {
    "enabled": true,
    "base_url": "http://bundled-tts:8001",
    "timeout_seconds": 60.0
  },
  "f5tts": {
    "enabled": true,
    "base_url": "http://f5-tts:8002",
    "timeout_seconds": 300.0
  },
  "lmstudio": {
    "enabled": true,
    "base_url": "http://host.docker.internal:1234/v1",
    "model": "",
    "timeout_seconds": 8.0
  },
  "openai": {
    "enabled": false,
    "base_url": "https://api.openai.com/v1",
    "api_key": "",
    "model": "tts-1",
    "timeout_seconds": 30.0
  },
  "defaults": {
    "voice_id": "uk-female-1",
    "output_format": "wav-alaw-8k",
    "amplitude": 1.0,
    "speed": 1.0,
    "pitch": 0.0
  }
}
```

### 7.3 Docker Volume Mounts

| Host Path | Container Path | Purpose |
|---|---|---|
| `./config` | `/app/config` | `config.json` — edit without rebuilding |
| `./voices/samples` | `/app/voices/samples` | Voice sample files (tts + f5-tts containers) |
| `./output` | `/app/output` | Persisted synthesised audio files |
| `tts_hf_cache` | `/root/.cache` | Kokoro/Piper HuggingFace model cache |
| `tts_model_cache` | `/root/.local` | Model weight cache |
| `f5tts_hf_cache` | `/root/.cache/huggingface` | F5-TTS model cache (~1.2 GB on first run) |

---

## 8. Docker Deployment

### 8.1 Build Strategy

The Dockerfile uses multi-stage builds with four targets:

| Target | Purpose |
|---|---|
| `base` | Shared base (Python 3.12 slim + FFmpeg + espeak) |
| `api` | Main FastAPI application only |
| `bundled-tts` | Kokoro + Piper model service (port 8001) |
| `f5-tts-service` | F5-TTS cloning service (port 8002) |
| `final` | Production image (extends `api`) |

### 8.2 docker-compose.yml Structure

```yaml
services:
  tts:                    # always starts — main API on :8765
  bundled-tts-cpu:        # profile: cpu — Kokoro/Piper on :8766
  bundled-tts-gpu:        # profile: gpu — Kokoro/Piper on :8766 (GPU)
  f5-tts-cpu:             # profile: cpu — F5-TTS on :8767
  f5-tts-gpu:             # profile: gpu — F5-TTS on :8767 (GPU)

volumes:
  tts_hf_cache:
  tts_model_cache:
  f5tts_hf_cache:
```

Start the full stack:
```bash
docker compose --profile gpu up --build -d    # GPU
docker compose --profile cpu up --build -d    # CPU
```

### 8.3 Approximate Image Sizes

| Layer | Size |
|---|---|
| Python 3.12 slim base + system deps | ~500 MB |
| API image (FastAPI, httpx, pydantic) | ~600 MB |
| Bundled TTS image (+Kokoro, Piper, PyTorch) | ~4 GB |
| F5-TTS image (+F5-TTS, PyTorch, CUDA libs) | ~6 GB |
| F5-TTS model weights (volume, not image) | ~1.2 GB |
| Kokoro model weights (volume, not image) | ~300 MB |

---

## 9. Hardware Targets & Performance

| Platform | F5-TTS (clone) | Kokoro (builtin) | Notes |
|---|---|---|---|
| NVIDIA RTX 4090 24 GB | ~2–5 s/clip | <1 s/clip | Production |
| NVIDIA RTX 3080 10 GB | ~5–10 s/clip | <1 s/clip | Production |
| NVIDIA RTX 3050 8 GB | ~8–15 s/clip | <1 s/clip | Development / light production |
| CPU only | 1–5 min/clip | 2–5 s/clip | Functional; not real-time |

---

## 10. Web UI

### 10.1 Synthesis Panel
- Text area with character counter (5,000 character limit)
- Voice selector (built-in and clone voices)
- Output format, amplitude, speed, and pitch controls
- Synthesise button with loading state
- Audio player and download link on success

### 10.2 Tone Generator Panel
- Frequency, beep duration, total duration, leading/trailing silence, amplitude controls
- Output format selector
- Generate and download

### 10.3 Bulk Synthesis Panel
- CSV upload (columns: `filename`, `text`)
- Progress polling with job status
- ZIP download on completion

### 10.4 Voice Samples Panel
- Voice name input + audio file picker
- Upload & register button — registers immediately, updates dropdown
- Inline success/error feedback

### 10.5 Configuration Panel
- Default voice, format, provider, amplitude, speed, pitch
- Provider endpoint and API key fields

---

## 11. Implementation Notes & Constraints

- **Single Uvicorn worker** — TTS inference is not thread-safe; concurrent requests are serialised via `asyncio.Lock`
- **F5-TTS cold start** — the model loads on the first synthesis request (~5–15 s on GPU); check `GET http://<host>:8767/health` for `model_loaded: true`
- **F5-TTS timeout** — CPU synthesis can take several minutes; `f5tts.timeout_seconds` defaults to 300 s; increase for very long texts
- **Volume sharing** — `voices/samples/` is mounted read-only into the f5-tts container; uploaded sample paths resolve identically in both containers
- **Model caching** — `f5tts_hf_cache` volume persists the ~1.2 GB F5-TTS model across rebuilds; first run only requires internet
- **FFmpeg required** — installed in all container images; required for all format conversions and pitch shifting
- **Mono enforcement** — all telephony outputs forced to mono; amplitude and pitch applied before resampling
- **Pause markers** — `[pause:N]` / `[silence:N]` inline in text are expanded to silence WAV segments before concatenation
- **NVIDIA Container Toolkit** — must be installed on the Docker host for GPU profiles

---

## 12. Future Considerations

- **Streaming output** — chunked transfer for long-form synthesis without waiting for the full file
- **SSML support** — pause, emphasis, and phoneme control beyond the current `[pause:N]` marker syntax
- **Chatterbox integration** — emotion-controllable cloning once ecosystem matures
- **Warm-up call** — fire a silent synthesis request at container startup to pre-load F5-TTS model before first user request
- **OpenClaw integration** — expose TTS as a callable tool from the OpenClaw agent pipeline
- **Vibe Wanderer integration** — TTS output playback within the Flutter chat UI

---

*End of specification — v1.2*
