# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-03-23

### Added
- Python package layout under `src/yt2stems`
- CLI entry points for the main workflow, benchmark, and installer/configurator
- Unit tests for config parsing, install decision logic, and workflow helpers
- GitHub Actions CI, contributor docs, issue templates, code of conduct, and security policy
- Bootstrap installer for creating a virtual environment and installing runtime dependencies
- MIT license and release workflow
- Friendly `yt2stems-setup` entry point for GitHub installs
- Draft release notes for the first public tag in `docs/releases/v0.1.0.md`

### Changed
- Refactored the original shell-script logic into testable Python modules
- Kept shell scripts as thin wrappers/bootstrap helpers instead of the primary implementation
- Improved runtime messaging and benchmark-driven default selection
- Updated the README and packaging metadata for public GitHub publication
- Kept Demucs run logs out of the final output folder while preserving `source.webm`
