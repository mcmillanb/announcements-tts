FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BRITISHTTS_CONFIG_DIR=/app/config \
    BRITISHTTS_OUTPUT_DIR=/app/output \
    BRITISHTTS_SAMPLE_DIR=/app/voices/samples \
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

RUN mkdir -p /app/config /app/voices/samples /app/output /root/.local /app/voices/piper \
    && curl -fsSL -o /app/voices/piper/en_GB-alan-medium.onnx \
      https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx \
    && curl -fsSL -o /app/voices/piper/en_GB-alan-medium.onnx.json \
      https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx.json

RUN python -c "from kokoro import KPipeline; p=KPipeline(lang_code='b'); [list(p('voice check', voice=v, speed=1.0)) for v in ('bm_george','bm_daniel','bf_emma','bf_isabella')]"

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8001/health >/dev/null || exit 1

CMD ["uvicorn", "app.tts_service:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]

FROM api AS final
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
