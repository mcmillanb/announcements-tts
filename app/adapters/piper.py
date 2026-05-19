from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Sequence


Runner = Callable[..., subprocess.CompletedProcess]


class PiperTTSClient:
    """Wrapper around the Piper CLI for local real speech synthesis."""

    def __init__(self, model_path: str | Path, runner: Runner = subprocess.run):
        self.model_path = Path(model_path)
        self.runner = runner

    @property
    def available(self) -> bool:
        return self.model_path.exists()

    def synthesise(self, text: str, output_path: Path, speed: float = 1.0) -> Path | None:
        if not self.available:
            return None

        output_path.parent.mkdir(parents=True, exist_ok=True)
        length_scale = self._speed_to_length_scale(speed)
        cmd: Sequence[str] = (
            "piper",
            "--model",
            str(self.model_path),
            "--output_file",
            str(output_path),
            "--length-scale",
            f"{length_scale:.3f}",
        )
        try:
            self.runner(
                cmd,
                input=text,
                text=True,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except (OSError, subprocess.CalledProcessError):
            return None

        if output_path.exists() and output_path.stat().st_size > 44:
            return output_path
        return None

    @staticmethod
    def _speed_to_length_scale(speed: float) -> float:
        # Piper length scale is inverse-ish: smaller is faster, larger is slower.
        if speed <= 0:
            return 1.0
        return max(0.5, min(2.0, 1.0 / speed))
