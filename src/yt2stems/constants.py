from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "yt2stems"
SUPPORTED_MODELS = ("htdemucs", "htdemucs_ft", "htdemucs_6s")
SUPPORTED_DEVICES = ("auto", "cpu", "mps")
DEFAULT_MODEL = "htdemucs_ft"
DEFAULT_DEVICE = "auto"
DEFAULT_OUTPUT_ROOT = Path.home() / "Downloads"
DEFAULT_CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME
DEFAULT_DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / APP_NAME
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.env"
DEFAULT_VENV_DIR = DEFAULT_DATA_DIR / "venv"
DEFAULT_BIN_DIR = Path.home() / ".local" / "bin"
TORCH_SPEC = os.environ.get("YT2STEMS_TORCH_SPEC", "torch==2.8.*")
TORCHAUDIO_SPEC = os.environ.get("YT2STEMS_TORCHAUDIO_SPEC", "torchaudio==2.8.*")
DEMUCS_SPEC = os.environ.get("YT2STEMS_DEMUCS_SPEC", "demucs==4.0.1")
YTDLP_SPEC = os.environ.get("YT2STEMS_YTDLP_SPEC", "yt-dlp[default]")
SOUNDFILE_SPEC = os.environ.get("YT2STEMS_SOUNDFILE_SPEC", "soundfile>=0.13")
