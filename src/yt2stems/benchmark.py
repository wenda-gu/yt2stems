from __future__ import annotations

import argparse
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .config import load_config
from .tooling import detect_mps_available, require_binary, resolve_tooling
from .utils import CliError, remove_path


@dataclass(slots=True)
class BenchResult:
    status: str
    device: str
    model: str
    elapsed_seconds: int
    detail: str = ""


def generate_sample(ffmpeg_bin: Path, duration: int) -> Path:
    sample_path = Path(tempfile.mkstemp(prefix="yt2stems_benchmark.", suffix=".wav")[1])
    command = [
        str(ffmpeg_bin),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=220:duration={duration}:sample_rate=44100",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={duration}:sample_rate=44100",
        "-f",
        "lavfi",
        "-i",
        f"anoisesrc=color=pink:duration={duration}:sample_rate=44100:amplitude=0.03",
        "-filter_complex",
        (
            "[0:a]volume=0.35[a0];"
            "[1:a]volume=0.25[a1];"
            "[2:a]highpass=f=1200,volume=0.10[a2];"
            "[a0][a1][a2]amix=inputs=3:normalize=0,"
            "pan=stereo|c0<c0+0.15*c2|c1<c1+0.15*c2[aout]"
        ),
        "-map",
        "[aout]",
        "-ar",
        "44100",
        "-ac",
        "2",
        str(sample_path),
    ]
    subprocess.run(command, check=True)
    return sample_path


def device_supported(python_bin: Path, device: str) -> bool:
    if device == "cpu":
        return True
    if device == "mps":
        return detect_mps_available(python_bin)
    return False


def run_benchmark_once(demucs_bin: Path, input_file: Path, device: str, model: str) -> BenchResult:
    run_dir = Path(tempfile.mkdtemp(prefix="yt2stems_bench_run."))
    log_file = run_dir / "demucs.log"
    command = [
        str(demucs_bin),
        "--device",
        device,
        "-n",
        model,
        "--out",
        str(run_dir / "out"),
        str(input_file),
    ]

    started = time.monotonic()
    try:
        with log_file.open("w", encoding="utf-8") as handle:
            completed = subprocess.run(
                command,
                stdout=handle,
                stderr=subprocess.STDOUT,
                check=False,
            )
        elapsed = int(time.monotonic() - started)
        if completed.returncode == 0:
            return BenchResult("OK", device, model, elapsed)
        tail = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-1:] or [
            "demucs exited with an error"
        ]
        return BenchResult("FAIL", device, model, elapsed, tail[0])
    finally:
        remove_path(run_dir)


def benchmark_matrix(
    *,
    demucs_bin: Path,
    python_bin: Path,
    input_file: Path,
    models: list[str],
    devices: list[str],
) -> list[BenchResult]:
    results: list[BenchResult] = []
    for model in models:
        for device in devices:
            if not device_supported(python_bin, device):
                results.append(BenchResult("SKIP", device, model, 0, "device unavailable"))
                continue
            results.append(run_benchmark_once(demucs_bin, input_file, device, model))
    return results


def render_result(result: BenchResult, machine_readable: bool) -> str:
    if machine_readable:
        parts = [result.status, result.device, result.model, str(result.elapsed_seconds)]
        if result.detail:
            parts.append(result.detail.replace("\t", " "))
        return "\t".join(parts)

    if result.status == "OK":
        return f"OK    {result.device:<4} | {result.model:<11} | {result.elapsed_seconds}s"
    if result.status == "SKIP":
        return f"SKIP  {result.device:<4} | {result.model:<11} | {result.detail}"
    return f"FAIL  {result.device:<4} | {result.model:<11} | {result.detail}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yt2stems-benchmark",
        description="Benchmark Demucs devices and models for yt2stems.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("input_audio", nargs="?", type=Path)
    parser.add_argument("--demucs", type=Path, default=None, help="Path to demucs binary")
    parser.add_argument(
        "--python",
        dest="python_bin",
        type=Path,
        default=None,
        help="Path to Python binary",
    )
    parser.add_argument("--ffmpeg", type=Path, default=None, help="Path to ffmpeg binary")
    parser.add_argument(
        "--models",
        default="htdemucs,htdemucs_ft",
        help="Comma-separated Demucs models to test",
    )
    parser.add_argument("--devices", default="cpu,mps", help="Comma-separated devices to test")
    parser.add_argument(
        "--duration",
        type=int,
        default=12,
        help="Generated sample duration in seconds",
    )
    parser.add_argument("--keep-sample", action="store_true", help="Keep the generated sample file")
    parser.add_argument(
        "--machine-readable",
        action="store_true",
        help="Emit tab-separated output for scripting",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = load_config()
    tooling = resolve_tooling(config)
    demucs_bin = args.demucs or tooling.demucs_bin
    python_bin = args.python_bin or tooling.python_bin
    ffmpeg_bin = args.ffmpeg or tooling.ffmpeg_bin

    try:
        demucs_path = require_binary(demucs_bin, "demucs")
        ffmpeg_path = require_binary(ffmpeg_bin, "ffmpeg")
    except Exception as error:
        raise CliError(str(error)) from error

    generated_sample = False
    input_file = args.input_audio
    if input_file is None:
        input_file = generate_sample(ffmpeg_path, args.duration)
        generated_sample = True

    try:
        if not input_file.exists():
            raise CliError(f"Input file not found: {input_file}")
        models = [item.strip() for item in args.models.split(",") if item.strip()]
        devices = [item.strip() for item in args.devices.split(",") if item.strip()]
        results = benchmark_matrix(
            demucs_bin=demucs_path,
            python_bin=python_bin,
            input_file=input_file,
            models=models,
            devices=devices,
        )
        for result in results:
            print(render_result(result, args.machine_readable))
        return 0
    except CliError as error:
        print(f"Error: {error}")
        return 1
    finally:
        if generated_sample and not args.keep_sample:
            remove_path(input_file)


if __name__ == "__main__":
    raise SystemExit(main())
