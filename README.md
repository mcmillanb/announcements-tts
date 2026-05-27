# Announcement TTS System

FastAPI-based text-to-speech service for IVR announcement generation, telephony format conversion, Docker deployment, and voice cloning.

## Features

- **4 built-in British voices** via Kokoro TTS (`bm_george`, `bm_daniel`, `bf_emma`, `bf_isabella`)
- **Zero-shot voice cloning** via F5-TTS — upload ~10 s of reference audio and clone any voice
- **Telephony output formats** — G.711 A-law/µ-law at 8 kHz and 16 kHz, PCM, MP3, FLAC, OGG
- **Tone generator** — configurable beep files with frequency, duration, silence padding and amplitude
- **Bulk synthesis** — upload a CSV, get back a ZIP of named audio files
- **Pitch control** — shift pitch ±12 semitones independent of speed
- **Pause markers** — embed `[pause:1.5]` or `[silence:0.5]` inline in text
- **Web UI** — browser interface for synthesis, tone generation, voice upload, bulk jobs, and config
- **Multi-container architecture** — separate API, bundled model service, and F5-TTS cloning service

---

## Quickstart (local dev)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Open:
- UI: http://127.0.0.1:8000/ui
- API health: http://127.0.0.1:8000/health
- Swagger docs: http://127.0.0.1:8000/docs

Example synthesis:

```bash
curl -fsS http://127.0.0.1:8000/synthesise \
  -H 'Content-Type: application/json' \
  -d '{"text":"Your call is important to us.","voice_id":"uk-female-1","output_format":"wav-alaw-8k","filename":"hold"}' \
  -o hold.wav
```

---

## Docker Compose

The stack runs three services:

| Service | Port | Purpose |
|---|---|---|
| `tts` | 8765 | Main FastAPI application |
| `bundled-tts` | 8766 | Kokoro + Piper built-in voice models |
| `f5-tts` | 8767 | F5-TTS voice cloning service |

Select CPU or GPU mode with `--profile`:

```bash
# CPU (slower, no GPU required)
docker compose --profile cpu up --build -d

# GPU (requires NVIDIA Container Toolkit)
docker compose --profile gpu up --build -d
```

Both profiles start all three services. GPU mode passes the NVIDIA device through to the bundled-tts and f5-tts containers. Switch between them with:

```bash
docker compose --profile cpu down && docker compose --profile gpu up -d
```

### First run

Create the required directories and optionally copy the example config:

```bash
mkdir -p config voices/samples output
cp config/config.example.json config/config.json
```

### Required volumes

| Host path | Purpose |
|---|---|
| `./config` | `config.json` — edit without rebuilding |
| `./voices/samples` | Voice reference audio files (shared with f5-tts container) |
| `./output` | Persisted synthesised audio |
| `tts_hf_cache` | Kokoro/Piper HuggingFace model cache |
| `tts_model_cache` | Model weight cache |
| `f5tts_hf_cache` | F5-TTS HuggingFace model cache (~1.2 GB, downloaded on first use) |

### Internet-isolated builds

For builds where HuggingFace and GitHub are unavailable, pre-stage model assets on a machine with internet access:

```bash
./scripts/predownload-build-assets.sh
```

This writes assets under `vendor/model-assets/` (Piper voice, Kokoro cache, F5-TTS cache, spaCy wheel). Copy the full repo including `vendor/model-assets/` to the isolated host; the Dockerfile uses local files when present.

### NVIDIA CUDA checklist

- Install [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) on the Docker host
- Verify GPU is visible to Docker: `docker run --rm nvidia/cuda:12.1.0-cudnn8-runtime nvidia-smi`
- Use `--profile gpu` when starting the stack

---

## Voice Cloning

1. Open the web UI at `http://<host>:8765/ui`
2. In the **Voice Samples** panel, enter a name and select a WAV/MP3/FLAC file (6–30 seconds of clean speech works best)
3. Click **Upload & register** — the voice is registered immediately and appears in the voice dropdown
4. Select the cloned voice and synthesise — the F5-TTS service uses your sample as the reference

The first synthesis with a cloned voice triggers the F5-TTS model download (~1.2 GB) if not already cached. Subsequent runs load from the `f5tts_hf_cache` volume.

**Reference audio tips:**
- 10–20 seconds of clean, consistent speech gives the best results
- Minimal background noise and music
- The speaker in the clip is the voice that gets cloned

---

## Pause Markers

Embed silence directly in synthesis text:

```
Welcome to the service. [pause:1.5] Press 1 for sales. [pause:0.5] Press 2 for support.
```

`[pause:N]` and `[silence:N]` are interchangeable. The number is seconds (decimals supported).

---

## Tone Generator

```bash
curl -fsS http://127.0.0.1:8765/tone \
  -H 'Content-Type: application/json' \
  -d '{"frequency_hz":1000,"beep_seconds":0.25,"total_seconds":1.0,"output_format":"wav-alaw-8k","filename":"beep"}' \
  -o beep.wav
```

---

## Bulk Synthesis

POST a CSV with `filename` and `text` columns to `/bulk-synthesise`. Poll `/bulk-job/{id}` for status. Download a ZIP of all files when complete. The web UI has a built-in bulk job panel.

---

## Configuration

Edit `config/config.json` (or use the Configuration button in the web UI).

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
  "defaults": {
    "voice_id": "uk-female-1",
    "output_format": "wav-alaw-8k",
    "amplitude": 1.0,
    "speed": 1.0,
    "pitch": 0.0
  }
}
```

Custom voices registered via the UI are written to `config.json` automatically. Missing sample files are skipped at startup without stopping the service.

---

## API Reference

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Engine status |
| GET | `/voices` | List built-in and custom voices |
| POST | `/synthesise` | Text → audio file |
| POST | `/tone` | Generate beep/silence audio |
| POST | `/bulk-synthesise` | CSV → background bulk job |
| GET | `/bulk-job/{id}` | Poll bulk job status |
| POST | `/upload-sample` | Upload and register a voice sample |
| GET/POST | `/config` | Read / update configuration |
| GET | `/ui` | Web interface |
| GET | `/docs` | Swagger UI |

### POST /synthesise

| Field | Type | Default | Description |
|---|---|---|---|
| `text` | string | required | Text to synthesise (max 5,000 chars); supports `[pause:N]` markers |
| `voice_id` | string | config default | Voice from `/voices` |
| `output_format` | enum | config default | See output formats below |
| `amplitude` | float | `1.0` | Multiplier 0.1–3.0 |
| `speed` | float | `1.0` | Rate multiplier 0.5–2.0 |
| `pitch` | float | `0.0` | Pitch shift in semitones −12 to +12 |
| `filename` | string | auto UUID | Output filename base (no extension) |

### Output formats

| ID | Rate | Codec | Use case |
|---|---|---|---|
| `wav-alaw-8k` | 8 kHz | G.711 A-law | European/international PSTN, Cisco CUCM EMEA |
| `wav-ulaw-8k` | 8 kHz | G.711 µ-law | North American PSTN, Cisco CUCM NA |
| `wav-alaw-16k` | 16 kHz | G.711 A-law | Wideband A-law IVR |
| `wav-ulaw-16k` | 16 kHz | G.711 µ-law | Wideband µ-law IVR |
| `wav-pcm-16k` | 16 kHz | PCM 16-bit | Wideband VoIP / SIP |
| `wav-pcm-8k` | 8 kHz | PCM 16-bit | Narrowband telephony |
| `wav-pcm-24k` | 24 kHz | PCM 16-bit | Native synthesis rate / archival |
| `mp3` | 44.1 kHz | MP3 | Web / general purpose |
| `flac` | 24 kHz | FLAC | Lossless archival |
| `ogg` | 24 kHz | Vorbis | Web streaming |

---

## Tests

```bash
pytest -q
```

The audio conversion test requires `ffmpeg` and `ffprobe` and is skipped if unavailable.
