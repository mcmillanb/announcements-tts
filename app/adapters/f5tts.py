from __future__ import annotations

from pathlib import Path

import httpx


class F5TTSClient:
    """HTTP client for the F5-TTS voice cloning service."""

    def __init__(self, base_url: str, timeout: float = 300.0, client: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = client

    async def _client_ctx(self):
        if self._client is not None:
            return self._client, False
        return httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout), True

    async def synthesise(self, text: str, ref_audio: str, output_path: Path, speed: float = 1.0) -> Path | None:
        client, close = await self._client_ctx()
        try:
            try:
                resp = await client.post(
                    "/synthesise",
                    json={"text": text, "ref_audio": ref_audio, "speed": speed},
                )
            except Exception:
                return None
            ctype = resp.headers.get("content-type", "").lower()
            if resp.status_code < 400 and ctype.startswith("audio/"):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(resp.content)
                return output_path
            return None
        finally:
            if close:
                await client.aclose()
