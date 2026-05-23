#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSET_DIR="${1:-$ROOT_DIR/vendor/model-assets}"

PIPER_DIR="$ASSET_DIR/piper"
SPACY_DIR="$ASSET_DIR/spacy"
HF_HOME_DIR="$ASSET_DIR/huggingface"

mkdir -p "$PIPER_DIR" "$SPACY_DIR" "$HF_HOME_DIR"

echo "Downloading Piper voice assets..."
curl -fL --retry 3 --retry-delay 2 \
  -o "$PIPER_DIR/en_GB-alan-medium.onnx" \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx"
curl -fL --retry 3 --retry-delay 2 \
  -o "$PIPER_DIR/en_GB-alan-medium.onnx.json" \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx.json"

echo "Downloading spaCy English model wheel..."
curl -fL --retry 3 --retry-delay 2 \
  -o "$SPACY_DIR/en_core_web_sm-3.8.0-py3-none-any.whl" \
  "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"

echo "Downloading Kokoro Hugging Face cache..."
python3 -m pip install --quiet "huggingface_hub>=0.23"
HF_HOME="$HF_HOME_DIR" python3 - <<'PY'
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="hexgrad/Kokoro-82M",
    repo_type="model",
)
PY

cat <<EOF

Build assets are ready in:
  $ASSET_DIR

Include this directory in the Docker build context before building in an
internet-isolated environment. The Dockerfile will use these files when present.
EOF
