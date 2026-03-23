#!/usr/bin/env bash

set -Eeuo pipefail
IFS=$'\n\t'

SOURCE_PATH="${BASH_SOURCE[0]}"
while [[ -L "$SOURCE_PATH" ]]; do
  SOURCE_DIR="$(cd -P "$(dirname "$SOURCE_PATH")" && pwd)"
  SOURCE_PATH="$(readlink "$SOURCE_PATH")"
  [[ "$SOURCE_PATH" != /* ]] && SOURCE_PATH="$SOURCE_DIR/$SOURCE_PATH"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE_PATH")" && pwd)"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/yt2stems"
VENV_DIR="${VENV_DIR:-$DATA_DIR/venv}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
TORCH_SPEC="${YT2STEMS_TORCH_SPEC:-torch==2.8.*}"
TORCHAUDIO_SPEC="${YT2STEMS_TORCHAUDIO_SPEC:-torchaudio==2.8.*}"
DEMUCS_SPEC="${YT2STEMS_DEMUCS_SPEC:-demucs==4.0.1}"
YTDLP_SPEC="${YT2STEMS_YTDLP_SPEC:-yt-dlp[default]}"
SOUNDFILE_SPEC="${YT2STEMS_SOUNDFILE_SPEC:-soundfile>=0.13}"

show_help() {
  cat <<'HELP'
Usage: ./install-yt2stems.sh [yt2stems-install options]

Creates a dedicated virtual environment, installs the runtime dependencies,
installs the local yt2stems package, and then runs yt2stems-install.

Environment overrides:
  PYTHON_BIN                  Python interpreter to use for the venv
  VENV_DIR                    Virtual environment destination
  BIN_DIR                     Launcher install directory (default: ~/.local/bin)
  YT2STEMS_TORCH_SPEC         torch package spec passed to pip
  YT2STEMS_TORCHAUDIO_SPEC    torchaudio package spec passed to pip
  YT2STEMS_DEMUCS_SPEC        demucs package spec passed to pip
  YT2STEMS_YTDLP_SPEC         yt-dlp package spec passed to pip
  YT2STEMS_SOUNDFILE_SPEC     soundfile package spec passed to pip

Examples:
  ./install-yt2stems.sh
  ./install-yt2stems.sh --skip-benchmark
  BIN_DIR=/usr/local/bin ./install-yt2stems.sh
HELP
}

pick_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    printf '%s\n' "$PYTHON_BIN"
    return 0
  fi

  local candidates=(python3.12 python3.13 python3.11 python3.10 python3.14 python3)
  local candidate
  for candidate in "${candidates[@]}"; do
    if command -v "$candidate" >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
  done

  return 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing dependency: $1" >&2
    exit 1
  }
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  show_help
  exit 0
fi

PYTHON_BIN="$(pick_python)" || {
  echo "Could not find a compatible python3 interpreter." >&2
  exit 1
}

require_cmd ffmpeg

mkdir -p "$DATA_DIR"

if [[ -x "$VENV_DIR/bin/python" ]]; then
  echo "Reusing virtual environment: $VENV_DIR"
else
  echo "Creating virtual environment: $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

VENV_PYTHON="$VENV_DIR/bin/python"

echo "Upgrading pip tooling..."
"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel

echo "Installing runtime dependencies..."
"$VENV_PYTHON" -m pip install "$TORCH_SPEC" "$TORCHAUDIO_SPEC" "$DEMUCS_SPEC" "$YTDLP_SPEC" "$SOUNDFILE_SPEC"

echo "Installing yt2stems package..."
"$VENV_PYTHON" -m pip install --upgrade --force-reinstall --no-deps "$SCRIPT_DIR"

echo "Configuring yt2stems..."
"$VENV_DIR/bin/yt2stems-install" --bin-dir "$BIN_DIR" "$@"
