# British TTS System

FastAPI implementation of `BritishTTS_Specification.md` for British English prompt generation, telephony conversion, Docker deployment and LM Studio integration.

Current engine behaviour:

- Built-in voice registry for Kokoro British speakers: `bm_george`, `bm_daniel`, `bf_emma`, `bf_isabella`.
- The main API can route synthesis to either an optional bundled model service or an external OpenAI-compatible service such as LM Studio.
- LM Studio adapter probes an OpenAI-compatible local endpoint and only accepts binary `audio/*` responses.
- If the selected provider is unavailable, synthesis falls back to a deterministic local 24 kHz WAV tone. This keeps API, Docker and telephony conversion usable. It is labelled fallback, not production speech.
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

### NVIDIA CUDA Deployment (GPU Acceleration)

For GPU-accelerated inference on your aibox host with an NVIDIA RTX 3050, use the custom CUDA-composed configuration:

```bash
# SSH to the host
ssh user@server

# Copy project directory if needed (from another machine or existing local clone)
cd /home/code/announcements-tts

# Enable GPU support in Docker Compose
cp docker-compose.yml docker-compose.cuda.yml  # creates docker-compose.cuda.yml with GPU flags
# Edit docker-compose.cuda.yml to enable CUDA runtime and NVIDIA driver access if running directly on host
sed -i 's/nvidia-enabled.*/nvidia-enabled: true/' docker-compose.cuda.yml

# Optional: For direct aibox deployment, ensure NVIDIA toolkit is installed
sudo apt-get install -y nvidia-cuda-toolkit  # if not already present

# Launch with GPU acceleration
docker compose -f docker-compose.cuda.yml up --build

# Health check (same API endpoint available on host)
curl http://localhost:8765/health
```

This configuration enables the TTS synthesis models to run on your host's CUDA-capable GPU, significantly improving inference speed for batch generation or real-time telephony prompts. The `tts_model_cache` volume mounts `/root/.local` where the model files are cached during the first container run.

If deploying directly on a machine with NVIDIA drivers (like the `aibox`), ensure that:

1. Docker and GPU drivers are properly integrated (`nvidia-smi` shows CUDA version matching).
2. The Docker Compose file includes `deploy.resources.reservations.devices` for GPU passthrough.
3. Environment variable `CUDA_VISIBLE_DEVICES=0` is set if only one GPU exists (adjust as needed).

### Notes

- Use the base `docker-compose.yml` for CPU-only environments (e.g., development on your local machine).
- Use `docker-compose.cuda.yml` when deploying on an NVIDIA-enabled host for faster model inference.
- The LM Studio adapter will probe the configured endpoint and fall back to a deterministic tone generation if the TTS endpoint is unavailable during startup.

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

The default Compose service runs only the main API container. To run the bundled
TTS model container as well:

```bash
docker compose --profile bundled up --build
```

The bundled model service listens on host port 8766 and is reached by the API at
`http://bundled-tts:8001` inside the Compose network. To skip bundled model
deployment, leave that profile disabled and set the UI configuration provider to
`External OpenAI-compatible service`, or set `TTS_PROVIDER=external`.

For NVIDIA GPU deployment of the bundled model service on a CUDA-enabled host (e.g., 192.168.123.219):

```bash
docker compose -f docker-compose.yml -f docker-compose.cuda.yml --profile bundled up --build
```

**NVIDIA CUDA Deployment Checklist:**

- **Docker GPU support**: Ensure NVIDIA Container Toolkit is installed and enabled on your host.
- **GPU driver compatibility**: Use CUDA 12.1+ runtime base image with `nvidia/cuda:12.1.0-cudnn8-runtime`.
- **Container resource reservation**: The docker-compose.cuda.yml file configures device reservations for GPU passthrough.

**Quick verification on CUDA-enabled host:**

```bash
# Check NVIDIA is detected by Docker
docker run --rm nvidia/cuda:12.1.0-cudnn8-runtime nvidia-smi

# Test the bundled TTS model with GPU acceleration
docker compose -f docker-compose.yml -f docker-compose.cuda.yml --profile bundled up --build

# Verify GPU usage inside container
docker compose exec bundled-tts python3 -c "import torch; print('CUDA available:', torch.cuda.is_available())"
```

**Complete deployment workflow (tested on aibox at 192.168.123.219):**

```bash
# 1. Build with CUDA support and bundled model profile
docker compose -f docker-compose.yml -f docker-compose.cuda.yml --profile bundled up --build

# 2. Check GPU allocation in container
docker compose exec bundled-tts python3 -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"; nvidia-smi

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
  docker compose exec bundled-tts python3 -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}, CUDA devices: {torch.cuda.device_count()}')"
  ```

## Configuration

Edit `config/config.json` using `config/config.example.json` as a starting point.
You can also open `/ui` and use the Configuration button to switch between the
bundled model service and an external OpenAI-compatible service.

Provider selection:

```json
{
  "engine": {
    "provider": "bundled"
  },
  "bundled_tts": {
    "enabled": true,
    "base_url": "http://bundled-tts:8001",
    "timeout_seconds": 60.0
  },
  "lmstudio": {
    "enabled": true,
    "base_url": "http://host.docker.internal:8888/v1",
    "timeout_seconds": 8.0
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
