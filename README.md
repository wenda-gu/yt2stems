# yt2stems

[![CI](https://github.com/wenda-gu/yt2stems/actions/workflows/ci.yml/badge.svg)](https://github.com/wenda-gu/yt2stems/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

`yt2stems` is a CLI for downloading audio from YouTube with `yt-dlp` and separating it into stems with Demucs.

It is tuned for a practical local workflow on macOS and Apple Silicon, but the codebase is structured as a small Python package with tests, CI, release docs, and packaging scaffolding so it can be maintained in the open.

## Features

- Normalizes YouTube URLs before processing
- Downloads the best available audio track with `yt-dlp`
- Runs Demucs with configurable model and device selection
- Supports `htdemucs`, `htdemucs_ft`, and `htdemucs_6s`
- Auto-benchmarks `cpu` vs `mps` and chooses sensible defaults during setup
- Supports `yt-dlp` browser-cookie authentication for YouTube bot-check challenges
- Retries transient YouTube anti-bot failures automatically
- Keeps runtime output readable with a simplified stem-splitting progress display
- Writes a single `metadata.txt` file alongside the generated stems

## Prerequisites

- Python 3.10+
- `ffmpeg` available on your `PATH`
- enough disk space for model downloads and separated stems

On macOS with Homebrew:

```bash
brew install ffmpeg python
```

## Install From GitHub

Clone the repository and run the setup command:

```bash
git clone https://github.com/wenda-gu/yt2stems.git
cd yt2stems
./yt2stems-setup
```

`yt2stems-setup` creates a dedicated virtual environment, installs the runtime dependencies, benchmarks your machine, and links the commands into `~/.local/bin` by default.

If `~/.local/bin` is not already on your `PATH`, add it to your shell profile.

### Optional setup overrides

```bash
./yt2stems-setup --skip-benchmark
BIN_DIR=/usr/local/bin ./yt2stems-setup
PYTHON_BIN=/opt/homebrew/bin/python3.12 ./yt2stems-setup
YT2STEMS_TORCH_SPEC='torch==2.8.*' YT2STEMS_TORCHAUDIO_SPEC='torchaudio==2.8.*' ./yt2stems-setup
./yt2stems-setup --cookies-from-browser safari
```

## Usage

```bash
yt2stems "https://www.youtube.com/watch?v=..."
yt2stems "https://www.youtube.com/watch?v=..." --model htdemucs --device cpu
yt2stems "https://www.youtube.com/watch?v=..." --model htdemucs_6s
yt2stems "https://www.youtube.com/watch?v=..." --voice
yt2stems "https://www.youtube.com/watch?v=..." --cookies-from-browser safari
yt2stems "https://www.youtube.com/watch?v=..." --cookies ~/Downloads/youtube-cookies.txt
yt2stems --version
```

If YouTube asks `yt-dlp` to sign in and confirm you are not a bot, pass authenticated browser cookies for that run or save the preference once with `yt2stems-install --cookies-from-browser safari`.

When `--cookies-from-browser` is used, `yt2stems` passes that browser source directly through to `yt-dlp`. If browser-cookie extraction or YouTube session acceptance fails, `yt2stems` surfaces the auth error more clearly and suggests the next best recovery options.

`yt2stems` also runs its internal `yt-dlp` commands with `--ignore-config` so personal `yt-dlp` config files do not accidentally override metadata, auth, or download behavior inside the pipeline.

### Output layout

Each completed run produces a folder containing:

- one WAV per stem
- `metadata.txt`
- `export_warning.txt` only when torchaudio downgraded the requested WAV precision during export

## Compatibility notes

The setup flow defaults to `yt-dlp[default]` instead of plain `yt-dlp`, because YouTube challenge solving may require the `yt-dlp-ejs` support package that ships through the default extras set.

The runtime defaults also pin:

- `torch==2.8.*`
- `torchaudio==2.8.*`
- `soundfile>=0.13`

That combination avoids newer TorchCodec-related Demucs export failures and ensures `torchaudio` has a working WAV backend for stem export.

For intermittent YouTube anti-bot failures, `yt2stems` automatically retries its internal `yt-dlp` commands a few times before giving up.

## Benchmarking

```bash
yt2stems-benchmark
yt2stems-benchmark --devices cpu,mps --models htdemucs,htdemucs_ft
yt2stems-benchmark --version
```

## Development

Create a development environment and install the package in editable mode:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e '.[dev]'
python -m pip install torch torchaudio demucs==4.0.1 "yt-dlp[default]" "soundfile>=0.13"
python -m unittest
ruff check .
python -m build
```

The package deliberately avoids hard runtime dependency declarations for the heavy audio stack. The runtime tools are installed by the setup script or manually during development.

## Repository layout

- `src/yt2stems/`: package source
- `tests/`: unit tests
- `yt2stems-setup`: friendly bootstrap entry point for end users
- `install-yt2stems.sh`: bootstrap implementation used by the setup wrapper
- `yt2stems`: development wrapper for the main CLI
- `demucs_benchmark.sh`: development wrapper for the benchmark CLI
- `docs/releasing.md`: release process notes
- `CHANGELOG.md`: human-readable change history

## License

This project is available under the [MIT License](LICENSE).

## Legal note

Make sure your usage complies with YouTube's terms of service and the rights associated with the media you download and process.
