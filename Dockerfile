FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BRITISHTTS_CONFIG_DIR=/app/config \
    BRITISHTTS_OUTPUT_DIR=/app/output \
    BRITISHTTS_SAMPLE_DIR=/app/voices/samples \
    LMSTUDIO_BASE_URL=http://192.168.122.54:8888/v1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY config/config.example.json ./config/config.example.json

RUN mkdir -p /app/config /app/voices/samples /app/output /root/.local

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health >/dev/null || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
