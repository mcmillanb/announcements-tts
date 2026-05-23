# British TTS System — Technical Specification

**Version 1.1 · Offline · Docker · NVIDIA CUDA · Voice Cloning · British English · Telephony Output**

---

## 1. Purpose & Scope

This document specifies the design, component selection, configuration, and API contract for a fully offline, containerised British English text-to-speech (TTS) service. The system must support built-in male and female British voices, real-time voice cloning from a short audio sample, and a set of user-controllable output parameters including telephony-grade formats.

The system runs on NVIDIA GPU hardware via Docker with the NVIDIA Container Toolkit. All inference occurs locally; no internet connection is required at runtime.

---

## 2. TTS Engine Selection

### 2.1 Evaluation Matrix

| Engine | Quality | Cloning | British EN | Min VRAM | CUDA | Notes |
|---|---|---|---|---|---|---|
| **F5-TTS** | ★★★★★ | ✅ 10 s | ✅ Excellent | 8 GB | ✅ | **Recommended primary** — SOTA flow-matching, best naturalness |
| **Kokoro TTS** | ★★★★½ | ❌ | ✅ Purpose-built | 4 GB | ✅ | **Recommended built-in voices** — bm_*/bf_* packs, very fast |
| Chatterbox (Resemble AI) | ★★★★½ | ✅ 5 s | ✅ Good | 8 GB | ✅ | Strong alternative — emotion control, Apache 2.0, Apr 2025 |
| StyleTTS 2 | ★★★★½ | ✅ Zero-shot | ⚠️ Needs tuning | 8 GB | ✅ | Excellent prosody; less natural British accent out-of-box |
| XTTS-v2 (Coqui) | ★★★★ | ✅ 6 s | ✅ Good | 4 GB | ✅ | Mature ecosystem; superseded by F5 on quality |
| Parler TTS | ★★★★ | ❌ | ✅ Excellent | 8 GB | ✅ | Description-prompted style; no cloning support |
| MeloTTS | ★★★ | ❌ | ✅ Fast | 2 GB | ✅ | Lightweight fallback only |

### 2.2 Recommended Architecture

A dual-engine approach gives the best combination of built-in voice quality and cloning capability:

**F5-TTS — Primary synthesis & cloning engine**
- Flow-matching diffusion model; state-of-the-art naturalness as of 2025
- Voice cloning from ~10 s reference audio with no fine-tuning required
- Repo: `SWivid/F5-TTS` · Licence: MIT
- Model size: ~3–4 GB · Docker image: ~6–7 GB with CUDA base

**Kokoro TTS — Built-in British voices**
- Purpose-built voice packs: `bm_george`, `bm_daniel` (male); `bf_emma`, `bf_isabella` (female)
- Extremely fast inference; ~300 MB model weight footprint
- Used when no sample file is provided and a built-in voice is selected
- Repo: `hexgrad/Kokoro-82M` · Licence: Apache 2.0

**Chatterbox (Resemble AI) — Secondary cloning engine (future)**
- Emotion-controllable, strong cloning, released April 2025; worth monitoring

**Note on LLM usage:** LLMs are not TTS engines. Ollama or Open WebUI is used only as an optional upstream text normalisation step (expanding abbreviations, numbers, dates) before the TTS engine receives the cleaned text.

### 2.3 Docker & NVIDIA Compatibility

Both engines are standard PyTorch/CUDA and fully compatible with containerised NVIDIA GPU deployment:

- Both use the standard `nvidia/cuda` base image (12.1+ recommended)
- GPU passthrough via NVIDIA Container Toolkit (`--gpus all` or Docker Compose `deploy.resources`)
- Fall back to CPU automatically if no GPU is detected at startup (degraded performance)
- Model weights cached in a named Docker volume to survive container rebuilds

---

## 3. System Architecture

### 3.1 Component Overview

| Component | Technology | Responsibility |
|---|---|---|
| API Server | FastAPI + Uvicorn | HTTP REST endpoints; request validation; file serving |
| F5-TTS Engine | F5-TTS (Python/PyTorch) | Primary synthesis; voice cloning from reference WAV |
| Kokoro Engine | kokoro (Python/PyTorch) | Built-in British voices; fast path when no clone needed |
| Audio Post-Processor | soundfile + FFmpeg + SoX | Amplitude scaling; resampling; format/codec conversion |
| Telephony Encoder | FFmpeg (libsox/alaw/ulaw) | G.711 A-law and µ-law encoding; 8 kHz / 16 kHz output |
| Text Pre-Processor | Ollama API client | Optional: abbreviation/number expansion via local LLM |
| Web UI | Vanilla HTML/JS | Browser-based synthesis interface; file upload; playback |
| Config Layer | config.json (volume) | Custom voice definitions; engine defaults; Ollama endpoint |

### 3.2 Request Flow

1. Client POSTs to `/synthesise` with text, voice_id, format, amplitude, speed, sample_rate, and use_ollama flags.
2. If `use_ollama = true`, API server calls the configured Ollama endpoint with a normalisation prompt; cleaned text is substituted.
3. Voice registry is checked: if `voice_id` maps to a `sample_file` path, F5-TTS cloning path is taken. Otherwise Kokoro is used with the mapped speaker name.
4. Engine synthesises to a temporary 24 kHz WAV buffer (internal working format).
5. Audio post-processor applies amplitude multiplier.
6. If a telephony format is requested, the pipeline resamples to 8 kHz or 16 kHz and encodes to the target codec (PCM, A-law, µ-law) via FFmpeg.
7. Final file is saved to `/app/output/` (mounted volume) and streamed back to the client.

---

## 4. Voice Model

### 4.1 Built-In British Voices (Kokoro)

| Voice ID | Label | Kokoro Speaker | Character |
|---|---|---|---|
| `uk-male-1` | British Male – Calm | `bm_george` | Deep, measured, RP accent — good for narration and IVR prompts |
| `uk-male-2` | British Male – Warm | `bm_daniel` | Warmer, slightly faster cadence — good for conversational content |
| `uk-female-1` | British Female – Clear | `bf_emma` | Clear, professional RP — good for UI read-back and hold messages |
| `uk-female-2` | British Female – Warm | `bf_isabella` | Warmer, slightly softer — good for assistive / ambient applications |

### 4.2 Custom / Cloned Voices (F5-TTS)

Any number of custom voices can be declared in `config.json`. Each entry maps a `voice_id` to a reference audio file. At startup the voice registry validates that sample files exist and logs warnings for any missing entries.

**Reference audio requirements:**
- Format: WAV (mono or stereo; 16 kHz or higher recommended — 22–44 kHz ideal)
- Duration: 6–30 seconds; F5-TTS performs best with 10–20 s of clean speech
- Content: Clear speech, minimal background noise, consistent volume
- The speaker in the reference clip is cloned — background voices or music degrade quality

**config.json example:**
```json
{
  "custom_voices": {
    "my-voice": {
      "label": "Custom Voice Sample",
      "sample_file": "/app/voices/samples/my_sample.wav",
      "language": "en"
    }
  }
}
```

Custom voices appear in the `/voices` endpoint and the web UI voice selector alongside built-in voices, marked with a **Clone** badge.

---

## 5. Output Formats

### 5.1 Format Matrix

All synthesis is performed internally at 24 kHz mono. The post-processor resamples and re-encodes to the requested output format.

| Format ID | Sample Rate | Bit Depth / Codec | Container | Primary Use Case |
|---|---|---|---|---|
| `wav-pcm-16k` | 16 kHz | PCM 16-bit signed LE | WAV (RIFF) | Wideband VoIP; SIP; modern IVR platforms |
| `wav-pcm-8k` | 8 kHz | PCM 16-bit signed LE | WAV (RIFF) | Narrowband telephony; legacy PSTN systems |
| `wav-alaw-8k` | 8 kHz | G.711 A-law (8-bit) | WAV | European/international PSTN; Cisco CUCM prompts |
| `wav-ulaw-8k` | 8 kHz | G.711 µ-law (8-bit) | WAV | North American PSTN; Cisco; Avaya |
| `wav-alaw-16k` | 16 kHz | G.711 A-law (8-bit) | WAV | Wideband A-law; some modern IVR / contact centre platforms |
| `wav-ulaw-16k` | 16 kHz | G.711 µ-law (8-bit) | WAV | Wideband µ-law; Cisco wideband prompts |
| `wav-pcm-24k` | 24 kHz | PCM 16-bit signed LE | WAV (RIFF) | High-quality archival; native synthesis rate |
| `mp3` | 44.1 kHz | MP3 (libmp3lame) | MP3 | General purpose; web playback |
| `flac` | 24 kHz | FLAC lossless | FLAC | Archival; quality-critical applications |
| `ogg` | 24 kHz | Vorbis | OGG | Web streaming |

### 5.2 Telephony Format Notes

**G.711 A-law (`wav-alaw-8k`, `wav-alaw-16k`)**
- Standard in European and international telephony
- Cisco CUCM uses A-law for prompt files in most EMEA deployments
- FFmpeg codec: `-c:a pcm_alaw`

**G.711 µ-law (`wav-ulaw-8k`, `wav-ulaw-16k`)**
- Standard in North American telephony (T1/DS0)
- Cisco CUCM uses µ-law in North American deployments
- FFmpeg codec: `-c:a pcm_mulaw`

**File naming convention for telephony output:**
```
{filename}_{sample_rate}_{codec}.wav
e.g.  hold_music_8k_alaw.wav
      welcome_prompt_16k_pcm.wav
```

**FFmpeg pipeline for telephony formats (internal implementation reference):**
```bash
# WAV PCM 8kHz
ffmpeg -i input.wav -ar 8000 -ac 1 -c:a pcm_s16le output_8k_pcm.wav

# WAV A-law 8kHz
ffmpeg -i input.wav -ar 8000 -ac 1 -c:a pcm_alaw output_8k_alaw.wav

# WAV µ-law 8kHz
ffmpeg -i input.wav -ar 8000 -ac 1 -c:a pcm_mulaw output_8k_ulaw.wav

# WAV PCM 16kHz
ffmpeg -i input.wav -ar 16000 -ac 1 -c:a pcm_s16le output_16k_pcm.wav

# WAV A-law 16kHz
ffmpeg -i input.wav -ar 16000 -ac 1 -c:a pcm_alaw output_16k_alaw.wav

# WAV µ-law 16kHz
ffmpeg -i input.wav -ar 16000 -ac 1 -c:a pcm_mulaw output_16k_ulaw.wav
```

> **Note:** All telephony outputs are forced to mono (`-ac 1`). Amplitude is applied before resampling to avoid clipping artefacts introduced by the resampler.

---

## 6. API Contract

### 6.1 Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness check — returns engine ready status |
| GET | `/voices` | List all available voices (built-in + custom) |
| POST | `/synthesise` | Synthesise text → audio file |
| POST | `/upload-sample` | Upload a WAV/MP3/FLAC reference file to `/voices/samples/` |
| GET | `/config` | Return current config (API keys redacted) |
| GET | `/docs` | Auto-generated OpenAPI docs (Swagger UI) |
| GET | `/ui` | Serve the built-in web interface |

### 6.2 POST /synthesise — Request Body

| Field | Type | Default | Description |
|---|---|---|---|
| `text` | string | Required | Text to synthesise (max 5,000 characters) |
| `voice_id` | string | `uk-female-1` | Voice identifier from `/voices` |
| `output_format` | enum | `wav-pcm-16k` | See format matrix in §5.1 |
| `amplitude` | float | `1.0` | Amplitude multiplier 0.1–3.0; clipped at ±1.0 before encode |
| `speed` | float | `1.0` | Speech rate multiplier 0.5–2.0 |
| `use_ollama` | bool | `false` | Pre-process text via Ollama normalisation |
| `filename` | string | auto | Base filename without extension; UUID generated if omitted |

**Response:** Binary audio stream with `Content-Type: audio/wav` (or appropriate MIME type) and `Content-Disposition: attachment`. File is also persisted to the `/app/output/` volume.

### 6.3 GET /voices — Response

```json
{
  "voices": [
    { "id": "uk-male-1",  "label": "British Male – Calm",    "type": "builtin", "language": "en" },
    { "id": "uk-female-1","label": "British Female – Clear",  "type": "builtin", "language": "en" },
    { "id": "my-voice",   "label": "Custom Voice Sample",     "type": "clone",   "language": "en" }
  ]
}
```

---

## 7. Configuration

### 7.1 config.json Schema

| Key | Type | Purpose |
|---|---|---|
| `custom_voices.*` | object | Map of `voice_id → {label, sample_file, language}` |
| `engine.provider` | string | `bundled` or `external` synthesis provider |
| `engine.external_provider` | string | External API selection: `lmstudio`, `openai`, `ollama`, `openwebui`, or `custom` |
| `ollama.enabled` | bool | Enable/disable Ollama pre-processing globally (default `false`) |
| `ollama.base_url` | string | Ollama base URL, e.g. `http://host.docker.internal:11434` |
| `ollama.model` | string | Model for text normalisation, e.g. `llama3.2`, `mistral` |
| `openwebui.enabled` | bool | Use Open WebUI API instead of Ollama directly |
| `openwebui.base_url` | string | Open WebUI endpoint |
| `openwebui.api_key` | string | Open WebUI API key if auth is enabled |
| `lmstudio.base_url` | string | LM Studio OpenAI-compatible endpoint, default `http://host.docker.internal:1234/v1` |
| `openai.base_url` | string | OpenAI API endpoint, default `https://api.openai.com/v1` |
| `openai.api_key` | string | OpenAI API key |
| `defaults.voice_id` | string | Default voice for web UI and omitted requests |
| `defaults.output_format` | string | Default output format (recommended: `wav-alaw-8k` for telephony) |
| `defaults.amplitude` | float | Default amplitude multiplier (`1.0`) |
| `defaults.speed` | float | Default speech rate (`1.0`) |

### 7.2 Full config.json Example

```json
{
  "custom_voices": {
    "my-voice": {
      "label": "Custom Voice Sample",
      "sample_file": "/app/voices/samples/my_sample.wav",
      "language": "en"
    }
  },
  "engine": {
    "provider": "bundled",
    "external_provider": "lmstudio"
  },
  "ollama": {
    "enabled": false,
    "base_url": "http://host.docker.internal:11434",
    "model": "llama3.2",
    "timeout_seconds": 8.0
  },
  "openwebui": {
    "enabled": false,
    "base_url": "http://host.docker.internal:3000",
    "api_key": "",
    "model": "tts-1",
    "timeout_seconds": 8.0
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
    "speed": 1.0
  }
}
```

### 7.3 Docker Volume Mounts

| Host Path | Container Path | Purpose |
|---|---|---|
| `./config` | `/app/config` | `config.json` — edit without rebuilding |
| `./voices/samples` | `/app/voices/samples` | Voice sample WAV files |
| `./output` | `/app/output` | Persisted synthesised audio files |
| `tts_model_cache` | `/root/.local` | Named volume — caches F5 and Kokoro model weights |

---

## 8. Docker Deployment

### 8.1 Base Image & GPU

```dockerfile
FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04
```

- Requires **NVIDIA Container Toolkit** on the Docker host
- GPU passthrough via `deploy.resources.reservations.devices` in Compose
- Falls back to CPU automatically if no GPU is detected (degraded speed only)

### 8.2 docker-compose.yml (outline)

```yaml
services:
  tts:
    build: .
    ports:
      - "8765:8000"
    volumes:
      - ./config:/app/config
      - ./voices/samples:/app/voices/samples
      - ./output:/app/output
      - tts_model_cache:/root/.local
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    extra_hosts:
      - "host.docker.internal:host-gateway"   # reach host Ollama / Open WebUI

volumes:
  tts_model_cache:
```

### 8.3 Approximate Image Sizes

| Layer | Size |
|---|---|
| CUDA 12.1 runtime base | ~3.5 GB |
| Python + FFmpeg + system deps | ~400 MB |
| Python packages (PyTorch, F5-TTS, Kokoro, FastAPI) | ~4 GB |
| F5-TTS model weights (cached volume, not image) | ~3.5 GB |
| Kokoro model weights (cached volume, not image) | ~300 MB |
| **Total image (excl. model cache)** | **~8 GB** |

> Model weights are downloaded on first run and cached in the named volume `tts_model_cache`. Subsequent container restarts do not re-download.

---

## 9. Hardware Targets & Performance

| Platform | Backend | Expected RTF* | Notes |
|---|---|---|---|
| NVIDIA RTX 4090 24 GB | CUDA | ~0.1× (10× RT) | High-throughput production |
| NVIDIA A10G 24 GB | CUDA | ~0.15× (6–7× RT) | Cloud/datacenter production |
| NVIDIA RTX 3060 12 GB | CUDA | ~0.2–0.4× (2.5–5× RT) | Light production / dev |
| Mac Studio M1 Max 32 GB | Apple MPS | ~0.3–0.5× (2–3× RT) | Dev/test only (no Docker GPU) |
| CPU only | PyTorch CPU | ~3–8× RT | Fallback; not suitable for production |

*RTF = Real-Time Factor. 0.1× = 10 seconds of audio generated per 1 second of processing.*

---

## 10. Web UI Requirements

### 10.1 Synthesis Panel
- Large text input area (min 200 px; 5,000 character limit with live counter)
- Voice selector grid — all registered voices with type badge (Built-in / Clone)
- Synthesise button with loading spinner
- Audio player on successful response
- Download button
- Synthesis history list with re-download links

### 10.2 Settings Panel
- Output format selector — full list from §5.1 with telephony formats grouped
- Amplitude slider: 0.1–3.0 with live numeric readout
- Speed slider: 0.5–2.0 with live numeric readout
- Ollama pre-processing toggle
- Voice sample upload zone (drag-and-drop + click)

### 10.3 Status
- Engine readiness indicator (polls `/health` on load)
- Error display for failed synthesis

---

## 11. Implementation Notes & Constraints

- **Single Uvicorn worker** — TTS model inference is not thread-safe; concurrent requests must be queued via `asyncio.Lock`
- **Model warm-up** — F5-TTS has a ~5–15 s cold-start on first inference; fire a warm-up call at container startup using a short fixed phrase
- **Model caching** — mount weights as a named Docker volume to avoid re-downloading on rebuild
- **FFmpeg required** — must be installed in the container image; needed for all telephony format conversions
- **Mono enforcement** — all telephony outputs forced to mono; stereo inputs from voice samples are mixed down before cloning
- **Amplitude before resample** — apply amplitude scaling on the 24 kHz buffer before resampling to avoid codec clipping artefacts
- **Ollama fallback** — if the Ollama call times out or fails, log a warning and proceed with raw input text
- **Long text chunking** — for inputs exceeding ~400 characters, split on sentence boundaries and concatenate audio buffers before format conversion
- **NVIDIA Container Toolkit** — must be installed on the Docker host; the container detects GPU availability at startup and logs the active backend

---

## 12. Future Considerations

- **Streaming output** — chunked transfer for long-form synthesis without waiting for the full file
- **SSML support** — pause, emphasis, and phoneme control for telephony prompt tuning
- **Batch synthesis API** — accept a list of texts and return a ZIP of telephony-formatted files; useful for bulk IVR prompt generation
- **Chatterbox integration** — emotion control once ecosystem matures
- **OpenClaw integration** — expose TTS as a callable tool from the OpenClaw agent pipeline
- **Vibe Wanderer integration** — TTS output playback within the Flutter chat UI

---

*End of specification — v1.1*
