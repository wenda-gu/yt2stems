# Releasing yt2stems

## Before the release

- Confirm CI is green on the default branch
- Verify `./yt2stems-setup` on a clean machine or fresh user account
- Confirm the current recommended Python version still works with the chosen torch and torchaudio specs
- Review `CHANGELOG.md` and move the relevant notes out of `Unreleased`
- Decide whether the release should keep the current pre-1.0 status or bump toward a more stable contract
- Make sure the project license is in place before any public release

## Build verification

In a clean development environment:

```bash
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m build
python -m unittest
ruff check .
```

## GitHub release flow

On a release tag such as `v0.1.0`, the release workflow will:

- build the source distribution and wheel
- generate a `SHA256SUMS` file for the release artifacts
- attach those files to the GitHub release

## Tagging strategy

This repository is still early, so keep tags simple and explicit:

- `v0.1.0` for the first packaged preview
- `v0.1.1` for backward-compatible fixes
- `v0.2.0` for behavior changes that users should notice

## Release notes checklist

Include:

- notable user-facing changes
- installation or compatibility changes
- known limitations
- upgrade notes if defaults or config behavior changed
