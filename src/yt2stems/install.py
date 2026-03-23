from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from . import __version__
from .benchmark import BenchResult, benchmark_matrix, generate_sample
from .config import AppConfig, write_config
from .constants import DEFAULT_BIN_DIR, DEFAULT_CONFIG_FILE
from .tooling import require_binary, resolve_tooling
from .utils import CliError


def select_fastest_device(results: list[BenchResult]) -> str:
    ok_results = [item for item in results if item.status == "OK" and item.model == "htdemucs"]
    if not ok_results:
        return "cpu"
    return min(ok_results, key=lambda item: item.elapsed_seconds).device


def select_default_model(
    results: list[BenchResult],
    *,
    device: str,
    quality_margin_percent: int,
) -> str:
    ok_results = {
        item.model: item
        for item in results
        if (
            item.status == "OK"
            and item.device == device
            and item.model in {"htdemucs", "htdemucs_ft"}
        )
    }
    baseline = ok_results.get("htdemucs")
    fine_tuned = ok_results.get("htdemucs_ft")

    if baseline is None and fine_tuned is None:
        return "htdemucs_ft"
    if baseline is None:
        return "htdemucs_ft"
    if fine_tuned is None:
        return "htdemucs"

    threshold = baseline.elapsed_seconds + (
        baseline.elapsed_seconds * quality_margin_percent / 100.0
    )
    return "htdemucs_ft" if fine_tuned.elapsed_seconds <= threshold else "htdemucs"


def install_launcher(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        destination.unlink()
    try:
        destination.symlink_to(source)
    except OSError:
        shutil.copy2(source, destination)
        destination.chmod(0o755)


def path_contains(directory: Path) -> bool:
    entries = [
        Path(part).expanduser().resolve()
        for part in os.environ.get("PATH", "").split(os.pathsep)
        if part
    ]
    return directory.expanduser().resolve() in entries


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yt2stems-install",
        description="Configure yt2stems after installing it into a virtual environment.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--bin-dir",
        type=Path,
        default=DEFAULT_BIN_DIR,
        help="Directory for the CLI launchers",
    )
    parser.add_argument(
        "--config-file",
        type=Path,
        default=DEFAULT_CONFIG_FILE,
        help="Path to config.env",
    )
    parser.add_argument(
        "--skip-benchmark",
        action="store_true",
        help="Skip auto-tuning and use conservative defaults",
    )
    parser.add_argument(
        "--quality-margin-percent",
        type=int,
        default=25,
        help="Keep htdemucs_ft if it is within this slowdown margin",
    )
    auth_group = parser.add_mutually_exclusive_group()
    auth_group.add_argument(
        "--cookies-from-browser",
        help=(
            "Pass-through value for yt-dlp --cookies-from-browser, "
            "for example safari or chrome:Default"
        ),
    )
    auth_group.add_argument(
        "--cookies",
        dest="cookies_file",
        type=Path,
        help="Path to a Netscape-format cookies.txt file for yt-dlp",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        tooling = resolve_tooling(None)
        demucs_bin = require_binary(tooling.demucs_bin, "demucs")
        ffmpeg_bin = require_binary(tooling.ffmpeg_bin, "ffmpeg")

        if args.skip_benchmark:
            default_device = "auto"
            default_model = "htdemucs_ft"
            print("Skipping benchmark; using conservative defaults.")
        else:
            print("Benchmarking device defaults...")
            device_sample = generate_sample(ffmpeg_bin, 12)
            try:
                device_results = benchmark_matrix(
                    demucs_bin=demucs_bin,
                    python_bin=tooling.python_bin,
                    input_file=device_sample,
                    models=["htdemucs"],
                    devices=["cpu", "mps"],
                )
            finally:
                device_sample.unlink(missing_ok=True)
            default_device = select_fastest_device(device_results)
            print(f"Selected default device: {default_device}")

            print(f"Benchmarking model defaults on {default_device}...")
            sample = generate_sample(ffmpeg_bin, 12)
            try:
                model_results = benchmark_matrix(
                    demucs_bin=demucs_bin,
                    python_bin=tooling.python_bin,
                    input_file=sample,
                    models=["htdemucs", "htdemucs_ft"],
                    devices=[default_device],
                )
            finally:
                sample.unlink(missing_ok=True)
            default_model = select_default_model(
                model_results,
                device=default_device,
                quality_margin_percent=args.quality_margin_percent,
            )
            print(f"Selected default model: {default_model}")

        config = AppConfig(
            env_kind="venv",
            env_prefix=tooling.env_prefix,
            default_model=default_model,
            default_device=default_device,
            quality_margin_percent=args.quality_margin_percent,
            python_bin=tooling.python_bin,
            cookies_from_browser=args.cookies_from_browser,
            cookies_file=args.cookies_file.expanduser() if args.cookies_file else None,
        )
        config_path = write_config(config, args.config_file.expanduser())
        print(f"Wrote config to {config_path}")

        env_bin = tooling.env_prefix / "bin"
        install_launcher(env_bin / "yt2stems", args.bin_dir.expanduser() / "yt2stems")
        install_launcher(
            env_bin / "yt2stems-benchmark",
            args.bin_dir.expanduser() / "yt2stems-benchmark",
        )
        print(f"Installed launchers into {args.bin_dir.expanduser()}")
        if not path_contains(args.bin_dir.expanduser()):
            print(f"Note: add {args.bin_dir.expanduser()} to your PATH to run yt2stems directly.")
        return 0
    except CliError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
