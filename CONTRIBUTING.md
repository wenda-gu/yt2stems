# Contributing

Thanks for considering a contribution.

## Before you start

- Read the README for local setup instructions.
- Open an issue before large changes so the direction is aligned early.
- Keep pull requests focused. Small, reviewable changes move faster.

## Development workflow

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e '.[dev]'
python -m pip install "torch==2.8.*" "torchaudio==2.8.*" "demucs==4.0.1" "yt-dlp[default]" "soundfile>=0.13"
python -m unittest
ruff check .
python -m build
```

## Coding guidelines

- Prefer standard-library solutions where they are sufficient.
- Keep CLI error messages actionable.
- Add tests for parsing, decision logic, and path handling when behavior changes.
- Avoid introducing new shell logic when the Python package can own the behavior instead.
- Update `CHANGELOG.md` for user-visible changes.

## Pull requests

Please include:

- a short summary of the change
- why the change is needed
- how you tested it
- any screenshots or terminal output if the UX changed

## Release readiness

Before tagging a release, make sure:

- tests pass locally and in CI
- contributor docs are still accurate
- runtime dependency guidance still matches the recommended install path
- the changelog is updated
- the LICENSE file and release metadata still match the intended project license
