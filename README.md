# British TTS System

FastAPI implementation of `BritishTTS_Specification.md` for British English prompt generation, telephony conversion, Docker deployment and LM Studio integration.

Current engine behaviour:

- Built-in voice registry for Kokoro British speakers: `bm_george`, `bm_daniel`, `bf_emma`, `bf_isabella`.
- LM Studio adapter probes an OpenAI-compatible local endpoint and only accepts binary `audio/*` responses.
- If LM Studio does not expose a usable TTS route, synthesis falls back to a deterministic local 24 kHz WAV tone. This keeps API, Docker and telephony conversion usable while the exact F5/Kokoro route is discovered. It is labelled fallback, not production speech.
- Output conversion is via FFmpeg with mono output and amplitude applied before encode/resample.

## Quickstart

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Then open:

- API health: http://127.0.0.1:8000/health
- Voices: http://127.0.0.1:8000/voices
- UI: http://127.0.0.1:8000/ui
- Swagger docs: http://127.0.0.1:8000/docs

Example synthesis:

```bash
curl -fsS http://127.0.0.1:8000/synthesise \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello Billy","voice_id":"uk-female-1","output_format":"wav-alaw-8k","filename":"hello"}' \
  -o hello.wav
```

## Docker Compose

```bash
mkdir -p config voices/samples output
cp config/config.example.json config/config.json   # optional
LMSTUDIO_BASE_URL=http://192.168.122.54:8888/v1 docker compose up --build
```

Compose exposes the API on host port 8765:

```bash
curl -fsS http://127.0.0.1:8765/health
curl -fsS http://127.0.0.1:8765/voices
curl -fsS http://127.0.0.1:8765/synthesise \
  -H 'Content-Type: application/json' \
  -d '{"text":"Telephony prompt test","output_format":"wav-alaw-8k","filename":"prompt"}' \
  -o prompt.wav
```

Required volumes:

- `./config:/app/config`
- `./voices/samples:/app/voices/samples`
- `./output:/app/output`
- `tts_model_cache:/root/.local`

## Configuration

Edit `config/config.json` using `config/config.example.json` as a starting point.

Custom voices:

```json
{
  "custom_voices": {
    "my-voice": {
      "label": "My Voice",
      "sample_file": "/app/voices/samples/my_voice.wav",
      "language": "en"
    }
  }
}
```

Missing custom voice sample files are ignored at registry load so broken config does not stop the service.

## Tests

```bash
pytest -q
```

The audio conversion test requires `ffmpeg` and `ffprobe`; it is skipped if those are unavailable.
