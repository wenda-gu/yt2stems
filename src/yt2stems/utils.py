from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path


class CliError(RuntimeError):
    """Raised when a user-facing CLI failure occurs."""


def run_command(
    args: Sequence[str | Path],
    *,
    check: bool = True,
    capture_output: bool = False,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [str(arg) for arg in args]
    return subprocess.run(
        command,
        check=check,
        capture_output=capture_output,
        text=True,
        cwd=str(cwd) if cwd else None,
    )


def tail_file(path: Path, lines: int = 20) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]


def remove_path(path: Path | None) -> None:
    if path is None or not path.exists():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)
