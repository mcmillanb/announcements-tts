from __future__ import annotations

from pathlib import Path
from typing import Iterable

import httpx


class LMStudioTTSClient:
    """Small OpenAI-compatible audio client with defensive content-type checks."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 4.0,
        client: httpx.AsyncClient | None = None,
        api_key: str = "",
        model: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = client
        self.api_key = api_key
        self.model = model

    async def _client_ctx(self):
        if self._client is not None:
            return self._client, False
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else None
        return httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout, headers=headers), True

    async def probe_models(self) -> list[str]:
        client, close = await self._client_ctx()
        try:
            resp = await client.get("/models")
            resp.raise_for_status()
            data = resp.json()
            return [str(item.get("id")) for item in data.get("data", []) if item.get("id")]
        except Exception:
            return []
        finally:
            if close:
                await client.aclose()

    async def synthesise(self, text: str, voice_or_model: str, output_path: Path, speed: float = 1.0) -> Path | None:
        models = await self.probe_models()
        model = self.model or self._choose_model(models, voice_or_model)
        endpoints = ["/audio/speech", "/tts", "/audio"]
        client, close = await self._client_ctx()
        try:
            for endpoint in endpoints:
                try:
                    resp = await client.post(endpoint, json={
                        "model": model,
                        "input": text,
                        "voice": voice_or_model,
                        "response_format": "wav",
                        "speed": speed,
                    })
                except Exception:
                    continue
                ctype = resp.headers.get("content-type", "").lower()
                if resp.status_code < 400 and ctype.startswith("audio/"):
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(resp.content)
                    return output_path
            return None
        finally:
            if close:
                await client.aclose()

    @staticmethod
    def _choose_model(models: Iterable[str], preferred: str) -> str:
        model_list = list(models)
        for candidate in (preferred, "kokoro_gguf", "kokoro-82m", "f5-tts"):
            if candidate in model_list:
                return candidate
        return model_list[0] if model_list else preferred
