from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__
from .config import AppConfig
from .constants import DEFAULT_OUTPUT_ROOT, SUPPORTED_DEVICES, SUPPORTED_MODELS
from .tooling import Tooling, detect_mps_available, require_binary, resolve_tooling
from .utils import CliError, remove_path, run_command, tail_file

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
BOT_CHALLENGE_TEXT = "Sign in to confirm you\u2019re not a bot"
CHROME_KEYCHAIN_FAILURE = "cannot decrypt v10 cookies: no key found"
CHROME_PASSWORD_LOOKUP_FAILURE = "find-generic-password failed"
SAFARI_PERMISSION_PATTERN = "Cookies.binarycookies"
SAFARI_PERMISSION_ERROR = "Operation not permitted"
ZERO_COOKIES_PATTERN = "Extracted 0 cookies from"
EJS_REMOTE_COMPONENTS_PATTERN = "Remote components challenge solver script"
EJS_SIGNATURE_FAILURE_PATTERN = "Signature solving failed"
EJS_N_FAILURE_PATTERN = "n challenge solving failed"
ONLY_IMAGES_PATTERN = "Only images are available for download"
TORCHCODEC_REQUIRED_PATTERN = "TorchCodec is required for save_with_torchcodec"
AUDIO_BACKEND_REQUIRED_PATTERN = "Couldn't find appropriate backend to handle uri"
YTDLP_RETRY_ATTEMPTS = 3
YTDLP_RETRY_DELAY_SECONDS = 2
DEMUCS_PROGRESS_PATTERN = re.compile(r"(?<!\d)(\d{1,3})%\|")
DEMUCS_PROGRESS_WIDTH = 28


@dataclass(slots=True)
class RunOptions:
    url: str
    model: str
    out_root: Path
    requested_device: str
    two_stem: str | None
    model_set_by_user: bool
    device_set_by_user: bool
    cookies_from_browser: str | None
    cookies_file: Path | None


@dataclass(slots=True)
class VideoMetadata:
    title: str
    video_id: str
    normalized_url: str
    safe_title: str


@dataclass(slots=True)
class AuthSession:
    auth_args: list[str]
    diagnostic_output: str = ""


@dataclass(slots=True)
class DemucsProgress:
    overall_percent: int
    current_pass: int
    total_passes: int
    current_pass_percent: int


def sanitize_title(title: str) -> str:
    sanitized = title.replace("/", "_").replace(":", "_")
    sanitized = sanitized.replace("\n", "_").replace("\r", "_")
    sanitized = re.sub(r"[^A-Za-z0-9 _.\-]", "_", sanitized)
    sanitized = re.sub(r"^[. ]+", "_", sanitized)
    return sanitized or "untitled"


def extract_video_id_from_url(url: str) -> str | None:
    candidate = url.strip()
    if VIDEO_ID_RE.fullmatch(candidate):
        return candidate

    parsed = urlparse(candidate)
    host = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]

    if host in {"youtu.be", "www.youtu.be"} and path_parts:
        video_id = path_parts[0]
        return video_id if VIDEO_ID_RE.fullmatch(video_id) else None

    if host in {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtube-nocookie.com",
        "www.youtube-nocookie.com",
    }:
        query = parse_qs(parsed.query)
        if path_parts[:1] == ["watch"]:
            video_id = query.get("v", [""])[0]
            return video_id if VIDEO_ID_RE.fullmatch(video_id) else None

        if path_parts[:1] in (["shorts"], ["embed"], ["live"]):
            if len(path_parts) >= 2 and VIDEO_ID_RE.fullmatch(path_parts[1]):
                return path_parts[1]

    return None


def build_auth_args(options: RunOptions) -> list[str]:
    if options.cookies_from_browser and options.cookies_file:
        raise CliError("Choose either --cookies-from-browser or --cookies, not both.")
    if options.cookies_from_browser:
        return ["--cookies-from-browser", options.cookies_from_browser]
    if options.cookies_file:
        return ["--cookies", str(options.cookies_file)]
    return []


def combine_command_output(completed: subprocess.CompletedProcess[str]) -> str:
    parts = [completed.stdout or "", completed.stderr or ""]
    return "\n".join(part for part in parts if part).strip()


def yt_dlp_base_args(yt_dlp_bin: Path) -> list[str]:
    return [str(yt_dlp_bin), "--ignore-config"]


def prepare_auth_session(url: str, yt_dlp_bin: Path, options: RunOptions) -> AuthSession:
    del url, yt_dlp_bin
    return AuthSession(auth_args=build_auth_args(options))


def auth_help_suffix(options: RunOptions) -> str:
    if options.cookies_from_browser or options.cookies_file:
        return ""
    return (
        " Try again with --cookies-from-browser safari, --cookies-from-browser chrome, "
        "or configure a cookies.txt file with --cookies."
    )


def diagnose_cookie_configuration(stderr: str, options: RunOptions) -> str | None:
    if not stderr:
        return None

    if (
        options.cookies_from_browser
        and CHROME_KEYCHAIN_FAILURE in stderr
        and CHROME_PASSWORD_LOOKUP_FAILURE in stderr
    ):
        browser = options.cookies_from_browser
        return (
            f" yt-dlp could not decrypt cookies from {browser}. "
            "On this Mac, browser-cookie authentication is failing before the YouTube request. "
            "First make sure you are signed into Chrome/your Google account "
            "and YouTube in that browser profile. "
            "If you are already signed in, try a Netscape cookies.txt file with --cookies, "
            "or switch to Safari after granting the terminal app Full Disk Access."
        )

    if (
        options.cookies_from_browser == "safari"
        and SAFARI_PERMISSION_PATTERN in stderr
        and SAFARI_PERMISSION_ERROR in stderr
    ):
        return (
            " macOS blocked access to Safari cookies. "
            "Grant Full Disk Access to the terminal/Codex app, "
            "or use a Netscape cookies.txt file with --cookies."
        )

    if options.cookies_from_browser and ZERO_COOKIES_PATTERN in stderr:
        browser = options.cookies_from_browser
        profile_hint = (
            " If you're signed into YouTube in a non-default Chrome profile, "
            "try chrome:Profile 1."
        )
        if ":" in browser or not browser.startswith("chrome"):
            profile_hint = ""
        return (
            f" yt-dlp extracted 0 cookies from {browser}. "
            "Make sure that browser/profile is signed into YouTube."
            f"{profile_hint}"
        )

    return None


def diagnose_yt_dlp_environment(stderr: str) -> str | None:
    if not stderr:
        return None

    if (
        EJS_REMOTE_COMPONENTS_PATTERN in stderr
        and EJS_SIGNATURE_FAILURE_PATTERN in stderr
        and EJS_N_FAILURE_PATTERN in stderr
    ) or (
        ONLY_IMAGES_PATTERN in stderr
        and "Requested format is not available" in stderr
    ):
        return (
            " Your yt-dlp install is missing the recommended EJS challenge-solver "
            "support for YouTube. "
            "Upgrade the venv to yt-dlp[default], or rerun install-yt2stems.sh "
            "so it reinstalls yt-dlp with its default extras. "
            "As an alternative, yt-dlp can fetch the solver at runtime with "
            "--remote-components ejs:github."
        )

    return None


def auth_rejected_hint(options: RunOptions) -> str:
    if options.cookies_from_browser:
        return (
            " yt-dlp did use browser cookies, but YouTube still rejected the session. "
            "This is often a YouTube-side or IP/session challenge rather than "
            "a missing-cookies problem. "
            "Try a fresh cookies.txt export from the same logged-in browser profile, "
            "a different browser/profile, or a different network. "
            "If stable yt-dlp still fails, the upstream project recommends trying "
            "the nightly build for YouTube regressions."
        )
    if options.cookies_file:
        return (
            " yt-dlp did use your cookies file, but YouTube still rejected the session. "
            "The cookies may be stale, incomplete, or tied to a session YouTube "
            "no longer accepts. "
            "Try exporting a fresh cookies.txt file from the same logged-in browser "
            "profile, or try a different network."
        )
    return auth_help_suffix(options)


def collect_auth_diagnostic(
    url: str,
    yt_dlp_bin: Path,
    options: RunOptions,
    auth_session: AuthSession,
) -> str:
    if auth_session.diagnostic_output:
        return auth_session.diagnostic_output
    if not options.cookies_from_browser:
        return ""

    command = [
        *yt_dlp_base_args(yt_dlp_bin),
        *auth_session.auth_args,
        "--verbose",
        "--no-playlist",
        "--no-download",
        "--get-id",
        url,
    ]
    completed = run_command(command, check=False, capture_output=True)
    parts = [completed.stdout or "", completed.stderr or ""]
    return "\n".join(part for part in parts if part).strip()


def format_yt_dlp_error(
    prefix: str,
    error: subprocess.CalledProcessError,
    options: RunOptions,
    diagnostic_output: str = "",
) -> CliError:
    stderr = (error.stderr or "").strip()
    detail = f" yt-dlp said: {stderr.splitlines()[-1]}" if stderr else ""

    combined_output = "\n".join(part for part in [stderr, diagnostic_output] if part)
    diagnostic_hint = diagnose_cookie_configuration(combined_output, options)
    if diagnostic_hint:
        return CliError(prefix + detail + diagnostic_hint)

    environment_hint = diagnose_yt_dlp_environment(combined_output)
    if environment_hint:
        return CliError(prefix + detail + environment_hint)

    if BOT_CHALLENGE_TEXT in stderr:
        return CliError(prefix + detail + auth_rejected_hint(options))
    return CliError(prefix + detail)


def should_retry_yt_dlp(stderr: str) -> bool:
    return BOT_CHALLENGE_TEXT in stderr


def run_yt_dlp_command(
    args: list[str],
    *,
    capture_output: bool = False,
    retry_label: str | None = None,
) -> subprocess.CompletedProcess[str]:
    last_error: subprocess.CalledProcessError | None = None
    for attempt in range(1, YTDLP_RETRY_ATTEMPTS + 1):
        try:
            return run_command(args, capture_output=capture_output)
        except subprocess.CalledProcessError as error:
            stderr = (error.stderr or "").strip()
            last_error = error
            if attempt >= YTDLP_RETRY_ATTEMPTS or not should_retry_yt_dlp(stderr):
                raise
            label = retry_label or "yt-dlp"
            print(
                f"{label} retry   : attempt {attempt}/{YTDLP_RETRY_ATTEMPTS} "
                "hit a YouTube bot challenge; "
                f"retrying in {YTDLP_RETRY_DELAY_SECONDS}s"
            )
            time.sleep(YTDLP_RETRY_DELAY_SECONDS)
    assert last_error is not None
    raise last_error


def normalize_youtube_url(
    url: str,
    yt_dlp_bin: Path,
    options: RunOptions,
    auth_session: AuthSession,
) -> str:
    video_id = extract_video_id_from_url(url)
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"

    try:
        completed = run_yt_dlp_command(
            [
                *yt_dlp_base_args(yt_dlp_bin),
                *auth_session.auth_args,
                "--get-id",
                "--no-playlist",
                url,
            ],
            capture_output=True,
            retry_label="Lookup",
        )
    except subprocess.CalledProcessError as error:
        diagnostic_output = collect_auth_diagnostic(url, yt_dlp_bin, options, auth_session)
        raise format_yt_dlp_error(
            "Could not extract a YouTube video ID from the provided input.",
            error,
            options,
            diagnostic_output,
        ) from error

    video_id = next((line.strip() for line in completed.stdout.splitlines() if line.strip()), "")
    if not video_id:
        raise CliError("Could not extract a YouTube video ID from the provided input.")
    return f"https://www.youtube.com/watch?v={video_id}"


def fetch_metadata(
    url: str,
    yt_dlp_bin: Path,
    options: RunOptions,
    auth_session: AuthSession,
) -> VideoMetadata:
    try:
        title = run_yt_dlp_command(
            [
                *yt_dlp_base_args(yt_dlp_bin),
                *auth_session.auth_args,
                "--no-playlist",
                "--no-download",
                "--get-title",
                url,
            ],
            capture_output=True,
            retry_label="Metadata",
        ).stdout.strip()
        video_id = run_yt_dlp_command(
            [
                *yt_dlp_base_args(yt_dlp_bin),
                *auth_session.auth_args,
                "--no-playlist",
                "--no-download",
                "--get-id",
                url,
            ],
            capture_output=True,
            retry_label="Metadata",
        ).stdout.strip()
    except subprocess.CalledProcessError as error:
        diagnostic_output = collect_auth_diagnostic(url, yt_dlp_bin, options, auth_session)
        raise format_yt_dlp_error(
            "Failed to fetch video metadata with yt-dlp.",
            error,
            options,
            diagnostic_output,
        ) from error

    if not title or not video_id:
        raise CliError("yt-dlp returned incomplete video metadata.")

    return VideoMetadata(
        title=title,
        video_id=video_id,
        normalized_url=url,
        safe_title=sanitize_title(title),
    )


def resolve_device(requested_device: str, tooling: Tooling) -> str:
    if requested_device not in SUPPORTED_DEVICES:
        raise CliError(f"Invalid device: {requested_device}")

    if requested_device == "cpu":
        return "cpu"

    if requested_device == "mps":
        if sys.platform != "darwin":
            raise CliError("MPS is only available on macOS.")
        if not detect_mps_available(tooling.python_bin):
            raise CliError("MPS is not available in the configured Python environment.")
        return "mps"

    if sys.platform == "darwin" and detect_mps_available(tooling.python_bin):
        return "mps"
    return "cpu"


def choose_source_audio(work_dir: Path) -> Path:
    matches = sorted(
        path
        for path in work_dir.glob("source.*")
        if (
            path.is_file()
            and not path.name.endswith(".info.json")
            and not path.name.endswith(".part")
        )
    )
    if not matches:
        raise CliError("Download failed; no source audio file was created.")
    return matches[0]


def choose_info_json(work_dir: Path) -> Path:
    matches = sorted(path for path in work_dir.glob("source*.info.json") if path.is_file())
    if not matches:
        raise CliError("Download finished, but yt-dlp did not leave a metadata .info.json file.")
    return matches[0]


def load_downloaded_metadata(work_dir: Path, normalized_url: str) -> VideoMetadata:
    info_path = choose_info_json(work_dir)
    try:
        payload = json.loads(info_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CliError(f"Could not parse yt-dlp metadata file: {info_path}") from error

    title = str(payload.get("title") or "").strip()
    video_id = str(payload.get("id") or "").strip()
    if not title or not video_id:
        raise CliError("yt-dlp metadata file was missing a title or video id.")

    return VideoMetadata(
        title=title,
        video_id=video_id,
        normalized_url=normalized_url,
        safe_title=sanitize_title(title),
    )


def remove_downloaded_info_json(work_dir: Path) -> None:
    for path in work_dir.glob("source*.info.json"):
        remove_path(path)


def write_metadata_summary(work_dir: Path, metadata: VideoMetadata) -> Path:
    metadata_path = work_dir / "metadata.txt"
    rendered = (
        f"Title: {metadata.title}\n"
        f"Source URL: {metadata.normalized_url}\n"
    )
    metadata_path.write_text(rendered, encoding="utf-8")
    return metadata_path


def download_audio(
    url: str,
    destination_dir: Path,
    yt_dlp_bin: Path,
    auth_session: AuthSession,
    options: RunOptions,
) -> Path:
    try:
        run_yt_dlp_command(
            [
                *yt_dlp_base_args(yt_dlp_bin),
                *auth_session.auth_args,
                "--no-playlist",
                "--write-info-json",
                "-f",
                "bestaudio[acodec=opus]/bestaudio",
                "-o",
                str(destination_dir / "source.%(ext)s"),
                url,
            ],
            retry_label="Download",
        )
    except subprocess.CalledProcessError as error:
        diagnostic_output = collect_auth_diagnostic(url, yt_dlp_bin, options, auth_session)
        raise format_yt_dlp_error(
            "Failed to download source audio with yt-dlp.",
            error,
            options,
            diagnostic_output,
        ) from error
    return choose_source_audio(destination_dir)


def format_model_note(model: str) -> str | None:
    if model == "htdemucs_ft":
        return "htdemucs_ft runs 4 internal model passes, so longer runtimes are expected."
    if model == "htdemucs_6s":
        return "htdemucs_6s adds guitar and piano stems and uses more memory."
    return None


def diagnose_demucs_failure(log_text: str) -> str | None:
    if TORCHCODEC_REQUIRED_PATTERN in log_text:
        return (
            "Demucs finished separation but could not write the output stems "
            "because this environment has "
            "torchaudio 2.10 without torchcodec. Repair the venv by rerunning install-yt2stems.sh, "
            "or install pinned versions with pip install -U 'torch==2.8.*' 'torchaudio==2.8.*'."
        )
    if AUDIO_BACKEND_REQUIRED_PATTERN in log_text:
        return (
            "Demucs finished separation but torchaudio could not find any "
            "audio backend to write WAV files. "
            "Repair the venv by rerunning install-yt2stems.sh, or install soundfile with "
            "pip install -U 'soundfile>=0.13'."
        )
    return None


def demucs_total_passes(model: str) -> int:
    if model == "htdemucs_ft":
        return 4
    return 1


def extract_demucs_progress(log_text: str, model: str) -> DemucsProgress | None:
    percentages = [
        min(100, int(match.group(1)))
        for match in DEMUCS_PROGRESS_PATTERN.finditer(log_text)
    ]
    if not percentages:
        return None

    grouped_passes: list[list[int]] = [[percentages[0]]]
    for percent in percentages[1:]:
        if percent < grouped_passes[-1][-1]:
            grouped_passes.append([percent])
        else:
            grouped_passes[-1].append(percent)

    total_passes = demucs_total_passes(model)
    completed_passes = sum(
        1 for values in grouped_passes[:-1] if values[-1] >= 100
    )
    current_pass_percent = grouped_passes[-1][-1]

    if current_pass_percent >= 100:
        completed_passes = min(completed_passes + 1, total_passes)
        if completed_passes < total_passes:
            return DemucsProgress(
                overall_percent=round(completed_passes * 100 / total_passes),
                current_pass=completed_passes + 1,
                total_passes=total_passes,
                current_pass_percent=0,
            )
        return DemucsProgress(
            overall_percent=100,
            current_pass=total_passes,
            total_passes=total_passes,
            current_pass_percent=100,
        )

    current_pass = min(completed_passes + 1, total_passes)
    overall_percent = round(
        ((completed_passes + current_pass_percent / 100.0) / total_passes) * 100
    )
    return DemucsProgress(
        overall_percent=min(100, overall_percent),
        current_pass=current_pass,
        total_passes=total_passes,
        current_pass_percent=current_pass_percent,
    )


def format_elapsed(seconds: int) -> str:
    minutes, seconds = divmod(max(0, seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{seconds:02d}s"
    if minutes:
        return f"{minutes}m{seconds:02d}s"
    return f"{seconds}s"


def render_progress_bar(percent: int, width: int = DEMUCS_PROGRESS_WIDTH) -> str:
    clamped = max(0, min(100, percent))
    filled = round(clamped * width / 100)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def format_demucs_progress_line(progress: DemucsProgress | None, elapsed: int) -> str:
    elapsed_label = format_elapsed(elapsed)
    if progress is None:
        return (
            f"Separating stems: {render_progress_bar(0)} "
            f"warming up ({elapsed_label} elapsed)"
        )

    base = (
        f"Separating stems: {render_progress_bar(progress.overall_percent)} "
        f"{progress.overall_percent:>3}%"
    )
    if progress.total_passes > 1:
        return (
            f"{base} (pass {progress.current_pass}/{progress.total_passes}, "
            f"{progress.current_pass_percent:>3}% current, {elapsed_label} elapsed)"
        )
    return f"{base} ({elapsed_label} elapsed)"


def supports_inline_progress() -> bool:
    return sys.stdout.isatty() and os.environ.get("TERM", "").lower() != "dumb"


def fit_progress_line(line: str, width: int | None = None) -> str:
    columns = width or shutil.get_terminal_size(fallback=(100, 24)).columns
    max_width = max(24, columns - 1)
    if len(line) <= max_width:
        return line
    if max_width <= 3:
        return line[:max_width]
    return line[: max_width - 3] + "..."


def run_demucs(
    *,
    demucs_bin: Path,
    source_audio: Path,
    model: str,
    device: str,
    out_dir: Path,
    two_stem: str | None,
    log_path: Path,
) -> None:
    command = [
        str(demucs_bin),
        "-n",
        model,
        "--device",
        device,
        "--float32",
        "--out",
        str(out_dir),
    ]
    if two_stem:
        command.extend(["--two-stems", two_stem])
    command.append(str(source_audio))

    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )

    start = time.monotonic()
    inline_progress = supports_inline_progress()
    last_line = ""
    last_non_tty_percent = -1
    last_non_tty_pass = 0
    last_non_tty_elapsed = -1

    while process.poll() is None:
        elapsed = int(time.monotonic() - start)
        log_text = (
            log_path.read_text(encoding="utf-8", errors="replace")
            if log_path.exists()
            else ""
        )
        progress = extract_demucs_progress(log_text, model)
        line = fit_progress_line(format_demucs_progress_line(progress, elapsed))
        if inline_progress:
            if line != last_line:
                print(f"\r\033[2K{line}", end="", flush=True)
                last_line = line
        else:
            should_report = (
                progress is None
                and (elapsed == 0 or elapsed - last_non_tty_elapsed >= 15)
            )
            if progress is not None:
                percent_changed = progress.overall_percent >= last_non_tty_percent + 5
                pass_changed = progress.current_pass != last_non_tty_pass
                time_changed = elapsed - last_non_tty_elapsed >= 15
                should_report = (
                    percent_changed
                    or pass_changed
                    or time_changed
                    or progress.overall_percent == 100
                )
            if should_report:
                print(line)
                last_line = line
                last_non_tty_elapsed = elapsed
                if progress is not None:
                    last_non_tty_percent = progress.overall_percent
                    last_non_tty_pass = progress.current_pass
        time.sleep(1)

    return_code = process.wait()
    elapsed = int(time.monotonic() - start)
    log_text = (
        log_path.read_text(encoding="utf-8", errors="replace")
        if log_path.exists()
        else ""
    )
    final_progress = extract_demucs_progress(log_text, model)
    if final_progress is None and return_code == 0:
        total_passes = demucs_total_passes(model)
        final_progress = DemucsProgress(
            overall_percent=100,
            current_pass=total_passes,
            total_passes=total_passes,
            current_pass_percent=100,
        )
    final_line = fit_progress_line(format_demucs_progress_line(final_progress, elapsed))
    if inline_progress:
        print(f"\r\033[2K{final_line}")
    elif final_line != last_line:
        print(final_line)

    if return_code != 0:
        diagnostic = diagnose_demucs_failure(log_text)
        if diagnostic:
            raise CliError(diagnostic)
        raise CliError("Demucs failed.\n" + "\n".join(tail_file(log_path)))


def parse_args(argv: list[str] | None, config: AppConfig) -> RunOptions:
    parser = argparse.ArgumentParser(
        prog="yt2stems",
        description="Download YouTube audio with yt-dlp and split stems with Demucs.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("url", help="YouTube URL to process")
    parser.add_argument("-m", "--model", choices=SUPPORTED_MODELS, default=None)
    parser.add_argument("-d", "--device", choices=SUPPORTED_DEVICES, default=None)
    parser.add_argument("-o", "--out", type=Path, default=DEFAULT_OUTPUT_ROOT)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-v", "--voice", action="store_true", help="Separate vocals and the rest")
    group.add_argument("-b", "--bass", action="store_true", help="Separate bass and the rest")
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

    args = parser.parse_args(argv)
    two_stem = "vocals" if args.voice else "bass" if args.bass else None

    return RunOptions(
        url=args.url,
        model=args.model or config.default_model,
        out_root=args.out.expanduser(),
        requested_device=args.device or config.default_device,
        two_stem=two_stem,
        model_set_by_user=args.model is not None,
        device_set_by_user=args.device is not None,
        cookies_from_browser=args.cookies_from_browser or config.cookies_from_browser,
        cookies_file=args.cookies_file.expanduser() if args.cookies_file else config.cookies_file,
    )


def run_pipeline(options: RunOptions, config: AppConfig) -> int:
    tooling = resolve_tooling(config)
    yt_dlp_bin = require_binary(tooling.yt_dlp_bin, "yt-dlp")
    demucs_bin = require_binary(tooling.demucs_bin, "demucs")
    require_binary(tooling.ffmpeg_bin, "ffmpeg")

    if options.model not in SUPPORTED_MODELS:
        raise CliError(f"Invalid model: {options.model}")

    resolved_device = resolve_device(options.requested_device, tooling)

    print("Preparing run...")
    print(f"Model        : {options.model}")
    print(f"Device       : {resolved_device}")
    if not options.model_set_by_user and config.default_model:
        print("Model source : install-time benchmark default")
    if not options.device_set_by_user:
        if config.default_device and config.default_device != "auto":
            print("Device source: install-time benchmark default")
        else:
            print("Device source: automatic detection")
    if options.cookies_from_browser:
        print(f"Cookies      : browser ({options.cookies_from_browser})")
    elif options.cookies_file:
        print(f"Cookies      : file ({options.cookies_file})")
    note = format_model_note(options.model)
    if note:
        print(f"Note         : {note}")
    if options.two_stem:
        print(f"Output mode  : {options.two_stem} + no_{options.two_stem}")
    else:
        print("Output mode  : full stem split")

    auth_session = prepare_auth_session(options.url, yt_dlp_bin, options)

    guessed_video_id = extract_video_id_from_url(options.url)
    normalized_url = (
        f"https://www.youtube.com/watch?v={guessed_video_id}"
        if guessed_video_id
        else normalize_youtube_url(options.url, yt_dlp_bin, options, auth_session)
    )

    options.out_root.mkdir(parents=True, exist_ok=True)
    work_prefix = guessed_video_id or "download"
    work_dir = Path(
        tempfile.mkdtemp(prefix=f".yt2stems_{work_prefix}.", dir=options.out_root)
    )
    log_path = work_dir / ".demucs.log"

    start_time = time.monotonic()
    final_destination: Path | None = None

    try:
        print(f"Workspace    : {work_dir}")
        print("Step 1/3 - Downloading audio...")
        source_audio = download_audio(normalized_url, work_dir, yt_dlp_bin, auth_session, options)
        metadata = load_downloaded_metadata(work_dir, normalized_url)
        final_destination = options.out_root / f"{metadata.safe_title} [{metadata.video_id}]"

        if final_destination.exists():
            raise CliError(f"Output already exists: {final_destination}")

        print(f"Source       : {source_audio.name}")

        print("Step 2/3 - Separating stems...")
        run_demucs(
            demucs_bin=demucs_bin,
            source_audio=source_audio,
            model=options.model,
            device=resolved_device,
            out_dir=work_dir / "separated",
            two_stem=options.two_stem,
            log_path=log_path,
        )
        print("Separation finished")

        stem_dir = work_dir / "separated" / options.model / source_audio.stem
        if not stem_dir.is_dir():
            raise CliError(f"Stem output missing at {stem_dir}")

        shutil.move(str(stem_dir), str(work_dir / "stems"))
        remove_path(work_dir / "separated")
        remove_downloaded_info_json(work_dir)
        write_metadata_summary(work_dir, metadata)

        log_text = (
            log_path.read_text(encoding="utf-8", errors="replace")
            if log_path.exists()
            else ""
        )
        if "TorchCodec AudioEncoder" in log_text:
            warning = (
                "torchaudio warned that this environment ignored some WAV export settings.\n"
                "The stems were created successfully, but they may have been "
                "written as 16-bit PCM instead of float32.\n"
            )
            (work_dir / "export_warning.txt").write_text(warning, encoding="utf-8")
            print(
                "Export note  : torchaudio ignored some WAV precision settings "
                "in this environment."
            )

        remove_path(log_path)

        print("Step 3/3 - Finalizing output...")
        shutil.move(str(work_dir), str(final_destination))
        work_dir = final_destination
        elapsed = int(time.monotonic() - start_time)
        print(f"Completed in {elapsed}s")
        print(f"Output       : {final_destination}")
        return 0
    finally:
        if work_dir.exists() and work_dir != final_destination:
            remove_path(work_dir)
        remove_path(log_path)


__all__ = [
    "DemucsProgress",
    "RunOptions",
    "VideoMetadata",
    "AuthSession",
    "auth_help_suffix",
    "auth_rejected_hint",
    "build_auth_args",
    "choose_info_json",
    "choose_source_audio",
    "combine_command_output",
    "collect_auth_diagnostic",
    "diagnose_demucs_failure",
    "diagnose_cookie_configuration",
    "diagnose_yt_dlp_environment",
    "extract_demucs_progress",
    "extract_video_id_from_url",
    "format_demucs_progress_line",
    "format_elapsed",
    "fit_progress_line",
    "fetch_metadata",
    "format_model_note",
    "format_yt_dlp_error",
    "load_downloaded_metadata",
    "normalize_youtube_url",
    "parse_args",
    "prepare_auth_session",
    "remove_downloaded_info_json",
    "resolve_device",
    "run_pipeline",
    "run_yt_dlp_command",
    "render_progress_bar",
    "sanitize_title",
    "should_retry_yt_dlp",
    "supports_inline_progress",
    "write_metadata_summary",
    "yt_dlp_base_args",
]
