# Announcement TTS System

FastAPI implementation for announcement prompt generation, telephony conversion, Docker deployment and LM Studio integration.

Current engine behaviour:

- Built-in voice registry for Kokoro British speakers: `bm_george`, `bm_daniel`, `bf_emma`, `bf_isabella`.
- The main API can route synthesis to either an optional bundled model service or an external OpenAI-compatible service such as LM Studio, OpenAI, Ollama-compatible endpoints, Open WebUI, or a custom endpoint.
- The external adapter probes an OpenAI-compatible endpoint and only accepts binary `audio/*` responses.
- If the selected provider is unavailable, synthesis returns an error instead of substituting a tone.
- A separate tone generator can create beep files with configurable frequency, duration, leading/trailing silence and amplitude.
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

### Predownloading Build Assets

For internet-isolated builds where Hugging Face and GitHub are unavailable,
stage the non-package model assets first on a machine with internet access:

```bash
./scripts/predownload-build-assets.sh
```

This writes assets under `vendor/model-assets/`:

- Piper voice model and JSON config from Hugging Face
- Kokoro model cache from Hugging Face
- spaCy `en_core_web_sm` wheel from GitHub

Copy the repository, including `vendor/model-assets/`, to the isolated build
host. The Dockerfile will use those local files when present and will only need
Docker Hub, Debian package repositories and PyPI access for the rest of the
build.

### CPU Deployment (Default)

```bash
mkdir -p config voices/samples output
cp config/config.example.json config/config.json   # optional
LMSTUDIO_BASE_URL=http://192.168.122.54:8888/v1 docker compose up --build
```

Compose exposes the API on host port 8765:

```bash
curl -fsS http://127.0.0.1:8765/health
curl -fsS http://127.0.0.1:8765/voices
curl -fsS http://127.0.0.1:8765/synthesise \\\n  -H 'Content-Type: application/json' \\\n  -d '{"text":"Telephony prompt test","output_format":"wav-alaw-8k","filename":"prompt"}' \\\n  -o prompt.wav
```

Required volumes:

- `./config:/app/config`
- `./voices/samples:/app/voices/samples`
- `./output:/app/output`
- `tts_model_cache:/root/.local`

### Docker Deployment

The single `docker-compose.yml` supports both CPU and GPU model service modes.
Select the mode with `COMPOSE_PROFILES`:

```bash
# CPU bundled model service
COMPOSE_PROFILES=cpu docker compose up --build

# GPU bundled model service
COMPOSE_PROFILES=gpu docker compose up --build
```

Both modes expose the same API on host port 8765 and the same internal model
service hostname, `http://bundled-tts:8001`. GPU mode requires NVIDIA drivers
and NVIDIA Container Toolkit on the Docker host.

The `tts_model_cache` volume mounts `/root/.local` where model files are cached
during the first container run. The LM Studio adapter will probe the configured
endpoint and report an error if the TTS endpoint is unavailable.

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

To skip bundled model deployment, omit `COMPOSE_PROFILES` and set the UI
configuration provider to `External OpenAI-compatible service`, or set
`TTS_PROVIDER=external`.

```bash
TTS_PROVIDER=external docker compose up --build
```

**NVIDIA CUDA Deployment Checklist:**

- **Docker GPU support**: Ensure NVIDIA Container Toolkit is installed and enabled on your host.
- **GPU driver compatibility**: Use CUDA 12.1+ runtime base image with `nvidia/cuda:12.1.0-cudnn8-runtime`.
- **Container resource reservation**: The `gpu` profile in `docker-compose.yml` configures device reservations for GPU passthrough.

**Quick verification on CUDA-enabled host:**

```bash
# Check NVIDIA is detected by Docker
docker run --rm nvidia/cuda:12.1.0-cudnn8-runtime nvidia-smi

# Test the bundled TTS model with GPU acceleration
COMPOSE_PROFILES=gpu docker compose up --build

# Verify GPU usage inside container
docker compose exec bundled-tts-gpu python3 -c "import torch; print('CUDA available:', torch.cuda.is_available())"
```

**Complete deployment workflow (tested on aibox at 192.168.123.219):**

```bash
# 1. Build with CUDA support and the GPU model profile
COMPOSE_PROFILES=gpu docker compose up --build

# 2. Check GPU allocation in container
docker compose exec bundled-tts-gpu python3 -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"; nvidia-smi

# 3. Test API health (host port 8765)
curl http://127.0.0.1:8765/health

# 4. Test synthesis with GPU acceleration
curl -fsS http://127.0.0.1:8765/synthesise \\\n    -H 'Content-Type: application/json' \\\n    -d '{"text":"Test GPU TTS","voice_id":"uk-female-1","output_format":"wav-alaw-8k","filename":"gpu_test"}' \\\n    -o gpu_test.wav

# 5. Check output file metadata
ffprobe -show_format gpu_test.wav
```

**Troubleshooting GPU issues:**

- **CUDA not detected**: Verify NVIDIA driver and Docker GPU support on host:
  ```bash
  nvidia-smi              # Should show your GPU
  docker run --rm nvidia/cuda:12.1.0-cudnn8-runtime nvidia-smi    # Docker can see GPU
  ```

- **Check container resources**: Verify GPU passthrough is configured:
  ```bash
  docker compose exec bundled-tts-gpu python3 -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}, CUDA devices: {torch.cuda.device_count()}')"
  ```

## Configuration

Edit `config/config.json` using `config/config.example.json` as a starting point.
You can also open `/ui` and use the Configuration button to switch between the
bundled model service and external provider options.

Provider selection:

```json
{
  "engine": {
    "provider": "bundled",
    "external_provider": "lmstudio"
  },
  "bundled_tts": {
    "enabled": true,
    "base_url": "http://bundled-tts:8001",
    "timeout_seconds": 60.0
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
  }
}
```

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
