FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ANNOUNCEMENTTTS_CONFIG_DIR=/app/config \
    ANNOUNCEMENTTTS_OUTPUT_DIR=/app/output \
    ANNOUNCEMENTTTS_SAMPLE_DIR=/app/voices/samples \
    PIPER_MODEL_PATH=/app/voices/piper/en_GB-alan-medium.onnx \
    LMSTUDIO_BASE_URL=http://192.168.122.54:8888/v1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates espeak-ng \
    && rm -rf /var/lib/apt/lists/*

FROM base AS api

COPY requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt

COPY app ./app
COPY config/config.example.json ./config/config.example.json

RUN mkdir -p /app/config /app/voices/samples /app/output

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health >/dev/null || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

FROM base AS bundled-tts

COPY requirements-api.txt requirements-tts.txt ./
RUN pip install --no-cache-dir -r requirements-tts.txt

COPY app ./app
COPY config/config.example.json ./config/config.example.json
COPY vendor/model-assets /tmp/model-assets

# Setup directories for voices, cache and model storage
RUN mkdir -p /app/config /app/voices/samples /app/output \
    /root/.cache /root/.local /app/voices/piper

# Configure PIPER_MODEL_PATH environment variable from config or default
ENV PIPER_MODEL_PATH=/app/voices/piper/en_GB-alan-medium.onnx \
    HF_HOME=/root/.cache/huggingface

# Use predownloaded build assets when present; otherwise download them.
RUN if [ -s /tmp/model-assets/piper/en_GB-alan-medium.onnx ]; then \
      cp /tmp/model-assets/piper/en_GB-alan-medium.onnx /app/voices/piper/en_GB-alan-medium.onnx; \
      cp /tmp/model-assets/piper/en_GB-alan-medium.onnx.json /app/voices/piper/en_GB-alan-medium.onnx.json; \
    else \
      curl -fsSL -o /app/voices/piper/en_GB-alan-medium.onnx \
        https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx \
      && curl -fsSL -o /app/voices/piper/en_GB-alan-medium.onnx.json \
        https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx.json; \
    fi \
    && if ls /tmp/model-assets/spacy/en_core_web_sm-*.whl >/dev/null 2>&1; then \
      pip install --no-cache-dir /tmp/model-assets/spacy/en_core_web_sm-*.whl; \
    fi \
    && if [ -d /tmp/model-assets/huggingface/hub ]; then \
      mkdir -p /root/.cache/huggingface; \
      cp -a /tmp/model-assets/huggingface/. /root/.cache/huggingface/; \
    fi

# Pre-initialize Kokoro British voice pipelines (bm/bf = British English)
# The 4 built-in British speakers: bm_george, bm_daniel, bf_emma, bf_isabella
RUN if [ -d /root/.cache/huggingface/hub ]; then export HF_HUB_OFFLINE=1; fi; \
    python -c "from kokoro import KPipeline; p=KPipeline(lang_code='b'); voices=['bm_george','bm_daniel','bf_emma','bf_isabella']; [list(p('voice check', voice=v, speed=1.0)) for v in voices]" || true

# Verify GPU support if running on CUDA-enabled host
RUN python -c "import torch; print('CUDA available:', torch.cuda.is_available() if torch.cuda.is_available() else 'CPU only')" || echo "Python/CUDA check"

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8001/health >/dev/null || exit 1

CMD ["uvicorn", "app.tts_service:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
FROM base AS f5-tts-service

COPY requirements-api.txt requirements-f5tts.txt ./
RUN pip install --no-cache-dir -r requirements-f5tts.txt

COPY app ./app
COPY vendor/model-assets /tmp/model-assets

RUN mkdir -p /app/voices/samples /root/.cache/huggingface \
    && if [ -d /tmp/model-assets/huggingface/hub ]; then \
      cp -a /tmp/model-assets/huggingface/. /root/.cache/huggingface/; \
    fi

ENV HF_HOME=/root/.cache/huggingface

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8002/health >/dev/null || exit 1

CMD ["uvicorn", "app.f5tts_service:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "1"]

FROM api AS final
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
