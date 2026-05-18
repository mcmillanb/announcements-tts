from pathlib import Path

import httpx
import pytest

from app.adapters.lmstudio import LMStudioTTSClient


@pytest.mark.asyncio
async def test_lmstudio_ignores_http_200_json_error_and_returns_none(tmp_path):
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "kokoro_gguf"}]})
        if request.url.path == "/v1/audio/speech":
            return httpx.Response(200, json={"error": "TTS route is not serving audio"})
        raise AssertionError(f"unexpected path {request.url.path}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://lm.test/v1")
    lm = LMStudioTTSClient(base_url="http://lm.test/v1", client=client)
    out = tmp_path / "out.wav"

    result = await lm.synthesise("hello", "kokoro_gguf", out)

    assert result is None
    assert not out.exists()
    await client.aclose()


@pytest.mark.asyncio
async def test_lmstudio_writes_audio_response(tmp_path):
    wav = b"RIFF$\x00\x00\x00WAVEfmt "

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "kokoro-82m"}]})
        if request.url.path == "/v1/audio/speech":
            return httpx.Response(200, content=wav, headers={"content-type": "audio/wav"})
        raise AssertionError(f"unexpected path {request.url.path}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://lm.test/v1")
    lm = LMStudioTTSClient(base_url="http://lm.test/v1", client=client)
    out = tmp_path / "out.wav"

    result = await lm.synthesise("hello", "kokoro-82m", out)

    assert result == out
    assert out.read_bytes() == wav
    await client.aclose()
