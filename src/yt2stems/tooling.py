from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig


@dataclass(slots=True)
class Tooling:
    env_prefix: Path
    python_bin: Path
    yt_dlp_bin: Path | None
    demucs_bin: Path | None
    ffmpeg_bin: Path | None


class ToolingError(RuntimeError):
    """Raised when a required external dependency cannot be found."""


def detect_env_prefix(config: AppConfig | None = None) -> Path:
    if config and config.env_prefix:
        return config.env_prefix.expanduser()
    return Path(sys.prefix)


def resolve_binary(name: str, env_prefix: Path | None = None) -> Path | None:
    if env_prefix is not None:
        candidate = env_prefix / "bin" / name
        if candidate.exists():
            return candidate
    resolved = shutil.which(name)
    return Path(resolved) if resolved else None


def resolve_tooling(config: AppConfig | None = None) -> Tooling:
    env_prefix = detect_env_prefix(config)
    python_bin = env_prefix / "bin" / "python"
    if not python_bin.exists():
        python_bin = Path(sys.executable)
    return Tooling(
        env_prefix=env_prefix,
        python_bin=python_bin,
        yt_dlp_bin=resolve_binary("yt-dlp", env_prefix),
        demucs_bin=resolve_binary("demucs", env_prefix),
        ffmpeg_bin=resolve_binary("ffmpeg", env_prefix=None),
    )


def require_binary(path: Path | None, label: str) -> Path:
    if path is None:
        raise ToolingError(f"Missing dependency: {label}")
    return path


def detect_mps_available(python_bin: Path) -> bool:
    command = [
        str(python_bin),
        "-c",
        (
            "import sys\n"
            "try:\n"
            "    import torch\n"
            "except Exception:\n"
            "    raise SystemExit(1)\n"
            "has_mps = hasattr(torch.backends, 'mps') and torch.backends.mps.is_available()\n"
            "raise SystemExit(0 if has_mps else 1)\n"
        ),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    return completed.returncode == 0
