from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yt2stems.workflow as workflow
from yt2stems.config import AppConfig
from yt2stems.tooling import Tooling
from yt2stems.workflow import (
    AuthSession,
    DemucsProgress,
    RunOptions,
    auth_help_suffix,
    auth_rejected_hint,
    build_auth_args,
    choose_info_json,
    choose_source_audio,
    combine_command_output,
    diagnose_cookie_configuration,
    diagnose_demucs_failure,
    diagnose_yt_dlp_environment,
    extract_demucs_progress,
    extract_video_id_from_url,
    fit_progress_line,
    format_demucs_progress_line,
    format_elapsed,
    format_model_note,
    format_yt_dlp_error,
    load_downloaded_metadata,
    prepare_auth_session,
    remove_downloaded_info_json,
    render_progress_bar,
    resolve_device,
    run_yt_dlp_command,
    sanitize_title,
    should_retry_yt_dlp,
    write_metadata_summary,
    yt_dlp_base_args,
)


class WorkflowTests(unittest.TestCase):
    def make_tooling(self, tmp_dir: Path) -> Tooling:
        env_prefix = tmp_dir / "venv"
        env_prefix.mkdir()
        python_bin = env_prefix / "python"
        python_bin.write_text("", encoding="utf-8")
        return Tooling(
            env_prefix=env_prefix,
            python_bin=python_bin,
            yt_dlp_bin=None,
            demucs_bin=None,
            ffmpeg_bin=None,
        )

    def make_options(self, **overrides: object) -> RunOptions:
        base: dict[str, object] = {
            "url": "https://www.youtube.com/watch?v=C8wpfQ5pdfo",
            "model": "htdemucs_ft",
            "out_root": Path("/tmp"),
            "requested_device": "auto",
            "two_stem": None,
            "model_set_by_user": False,
            "device_set_by_user": False,
            "cookies_from_browser": None,
            "cookies_file": None,
        }
        base.update(overrides)
        return RunOptions(**base)

    def test_sanitize_title_replaces_problem_characters(self) -> None:
        self.assertEqual(sanitize_title("./Song:Name?\n"), "__Song_Name__")

    def test_extract_video_id_from_watch_url_with_playlist_params(self) -> None:
        url = "https://www.youtube.com/watch?v=C8wpfQ5pdfo&list=RDC8wpfQ5pdfo&start_radio=1"
        self.assertEqual(extract_video_id_from_url(url), "C8wpfQ5pdfo")

    def test_extract_video_id_from_simple_watch_url(self) -> None:
        url = "https://www.youtube.com/watch?v=C8wpfQ5pdfo"
        self.assertEqual(extract_video_id_from_url(url), "C8wpfQ5pdfo")

    def test_extract_video_id_from_youtu_be_url(self) -> None:
        url = "https://youtu.be/C8wpfQ5pdfo?t=32"
        self.assertEqual(extract_video_id_from_url(url), "C8wpfQ5pdfo")

    def test_build_auth_args_with_browser(self) -> None:
        options = self.make_options(cookies_from_browser="safari")
        self.assertEqual(build_auth_args(options), ["--cookies-from-browser", "safari"])

    def test_build_auth_args_with_cookies_file(self) -> None:
        options = self.make_options(cookies_file=Path("/tmp/cookies.txt"))
        self.assertEqual(build_auth_args(options), ["--cookies", "/tmp/cookies.txt"])

    def test_combine_command_output_merges_stdout_and_stderr(self) -> None:
        completed = subprocess.CompletedProcess(["yt-dlp"], 1, stdout="hello", stderr="world")
        self.assertEqual(combine_command_output(completed), "hello\nworld")

    def test_yt_dlp_base_args_ignores_external_config(self) -> None:
        self.assertEqual(
            yt_dlp_base_args(Path("/usr/bin/yt-dlp")),
            ["/usr/bin/yt-dlp", "--ignore-config"],
        )

    def test_auth_help_suffix_is_suppressed_when_auth_is_present(self) -> None:
        options = self.make_options(cookies_from_browser="safari")
        self.assertEqual(auth_help_suffix(options), "")

    def test_diagnose_cookie_configuration_for_chrome_keychain_failure(self) -> None:
        options = self.make_options(cookies_from_browser="chrome")
        stderr = "\n".join(
            [
                "WARNING: find-generic-password failed",
                "WARNING: cannot decrypt v10 cookies: no key found",
                "Extracted 0 cookies from chrome (148 could not be decrypted)",
            ]
        )
        hint = diagnose_cookie_configuration(stderr, options)
        self.assertIsNotNone(hint)
        self.assertIn("could not decrypt cookies from chrome", hint)
        self.assertIn("signed into Chrome/your Google account and YouTube", hint)
        self.assertIn("cookies.txt file", hint)

    def test_diagnose_yt_dlp_environment_for_missing_ejs_support(self) -> None:
        stderr = "\n".join(
            [
                (
                    "WARNING: [youtube] [jsc] Remote components challenge solver "
                    "script (deno) and NPM package (deno) were skipped."
                ),
                (
                    "WARNING: [youtube] C8wpfQ5pdfo: Signature solving failed: "
                    "Some formats may be missing."
                ),
                (
                    "WARNING: [youtube] C8wpfQ5pdfo: n challenge solving failed: "
                    "Some formats may be missing."
                ),
                "WARNING: Only images are available for download. use --list-formats to see them",
                (
                    "ERROR: [youtube] C8wpfQ5pdfo: Requested format is not "
                    "available. Use --list-formats for a list of available formats"
                ),
            ]
        )
        hint = diagnose_yt_dlp_environment(stderr)
        self.assertIsNotNone(hint)
        self.assertIn("yt-dlp[default]", hint)
        self.assertIn("remote-components ejs:github", hint)

    def test_diagnose_demucs_failure_for_missing_torchcodec(self) -> None:
        log_text = (
            "ImportError: TorchCodec is required for save_with_torchcodec. "
            "Please install torchcodec to use this function."
        )
        hint = diagnose_demucs_failure(log_text)
        self.assertIsNotNone(hint)
        self.assertIn("torchaudio 2.10 without torchcodec", hint)
        self.assertIn("torch==2.8.*", hint)

    def test_diagnose_demucs_failure_for_missing_audio_backend(self) -> None:
        log_text = (
            "RuntimeError: Couldn't find appropriate backend to handle uri "
            "/tmp/vocals.wav and format None."
        )
        hint = diagnose_demucs_failure(log_text)
        self.assertIsNotNone(hint)
        self.assertIn("could not find any audio backend", hint)
        self.assertIn("soundfile", hint)

    def test_extract_demucs_progress_for_single_pass_model(self) -> None:
        log_text = (
            "12%|###| 36/300 [00:12<01:30, 2.9seconds/s]\r"
            "57%|####| 171/300 [00:57<00:43, 3.0seconds/s]"
        )
        progress = extract_demucs_progress(log_text, "htdemucs")
        self.assertEqual(
            progress,
            DemucsProgress(
                overall_percent=57,
                current_pass=1,
                total_passes=1,
                current_pass_percent=57,
            ),
        )

    def test_extract_demucs_progress_for_multi_pass_model(self) -> None:
        log_text = (
            "100%|#####| 300/300 [01:40<00:00, 3.0seconds/s]\r"
            "18%|#| 54/300 [00:18<01:22, 3.0seconds/s]"
        )
        progress = extract_demucs_progress(log_text, "htdemucs_ft")
        self.assertEqual(
            progress,
            DemucsProgress(
                overall_percent=30,
                current_pass=2,
                total_passes=4,
                current_pass_percent=18,
            ),
        )

    def test_format_elapsed_uses_compact_labels(self) -> None:
        self.assertEqual(format_elapsed(9), "9s")
        self.assertEqual(format_elapsed(69), "1m09s")
        self.assertEqual(format_elapsed(3661), "1h01m01s")

    def test_render_progress_bar_uses_ascii_bar(self) -> None:
        self.assertEqual(render_progress_bar(50, width=10), "[#####-----]")

    def test_format_demucs_progress_line_includes_pass_details(self) -> None:
        progress = DemucsProgress(
            overall_percent=30,
            current_pass=2,
            total_passes=4,
            current_pass_percent=18,
        )
        line = format_demucs_progress_line(progress, 69)
        self.assertIn("30%", line)
        self.assertIn("pass 2/4", line)
        self.assertIn("18% current", line)
        self.assertIn("1m09s elapsed", line)

    def test_fit_progress_line_truncates_for_narrow_terminal(self) -> None:
        line = fit_progress_line(
            "Separating stems: [##########----------] 50% "
            "(pass 2/4, 18% current, 1m09s elapsed)",
            width=40,
        )
        self.assertLessEqual(len(line), 39)
        self.assertTrue(line.endswith("..."))

    def test_fit_progress_line_keeps_short_lines(self) -> None:
        line = "Separating stems: [#####-----] 50%"
        self.assertEqual(fit_progress_line(line, width=80), line)

    def test_auth_rejected_hint_mentions_browser_profile_when_using_browser_cookies(self) -> None:
        options = self.make_options(cookies_from_browser="chrome")
        hint = auth_rejected_hint(options)
        self.assertIn("did use browser cookies", hint)
        self.assertIn("cookies.txt export", hint)

    def test_diagnose_cookie_configuration_for_safari_permission_failure(self) -> None:
        options = self.make_options(cookies_from_browser="safari")
        stderr = (
            "ERROR: [Errno 1] Operation not permitted: "
            "'/Users/test/Library/Containers/com.apple.Safari/Data/Library/"
            "Cookies/Cookies.binarycookies'"
        )
        hint = diagnose_cookie_configuration(stderr, options)
        self.assertIsNotNone(hint)
        self.assertIn("Full Disk Access", hint)

    def test_format_yt_dlp_error_prefers_cookie_hint_when_diagnostic_is_available(self) -> None:
        options = self.make_options(cookies_from_browser="chrome")
        error = subprocess.CalledProcessError(
            1,
            ["yt-dlp"],
            stderr="ERROR: [youtube] C8wpfQ5pdfo: Sign in to confirm you’re not a bot",
        )
        diagnostic = "\n".join(
            [
                "WARNING: find-generic-password failed",
                "WARNING: cannot decrypt v10 cookies: no key found",
                "Extracted 0 cookies from chrome (148 could not be decrypted)",
            ]
        )
        message = str(
            format_yt_dlp_error(
                "Failed to fetch video metadata with yt-dlp.",
                error,
                options,
                diagnostic,
            )
        )
        self.assertIn("could not decrypt cookies from chrome", message)
        self.assertNotIn("Try again with --cookies-from-browser safari", message)

    def test_prepare_auth_session_uses_direct_auth_args(self) -> None:
        options = self.make_options(cookies_from_browser="chrome")
        session = prepare_auth_session(options.url, Path("/usr/bin/yt-dlp"), options)

        self.assertEqual(session.auth_args, ["--cookies-from-browser", "chrome"])
        self.assertIsInstance(session, AuthSession)

    def test_should_retry_yt_dlp_for_bot_challenge(self) -> None:
        self.assertTrue(should_retry_yt_dlp("ERROR: [youtube] Sign in to confirm you’re not a bot"))
        self.assertFalse(should_retry_yt_dlp("ERROR: Requested format is not available"))

    def test_run_yt_dlp_command_retries_bot_challenge_then_succeeds(self) -> None:
        error = subprocess.CalledProcessError(
            1,
            ["yt-dlp"],
            stderr="ERROR: [youtube] Sign in to confirm you’re not a bot",
        )
        success = subprocess.CompletedProcess(["yt-dlp"], 0, stdout="ok", stderr="")
        with mock.patch.object(
            workflow,
            "run_command",
            side_effect=[error, success],
        ) as run_command_mock:
            with mock.patch.object(workflow.time, "sleep") as sleep_mock:
                completed = run_yt_dlp_command(
                    ["yt-dlp", "--get-id"],
                    capture_output=True,
                    retry_label="Download",
                )
        self.assertEqual(completed.stdout, "ok")
        self.assertEqual(run_command_mock.call_count, 2)
        sleep_mock.assert_called_once()

    def test_choose_source_audio_picks_downloaded_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.info.json").write_text("{}", encoding="utf-8")
            file_path = root / "source.webm"
            file_path.write_text("x", encoding="utf-8")
            self.assertEqual(choose_source_audio(root), file_path)

    def test_choose_info_json_finds_downloaded_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            info_path = root / "source.info.json"
            info_path.write_text("{}", encoding="utf-8")
            self.assertEqual(choose_info_json(root), info_path)

    def test_load_downloaded_metadata_reads_title_and_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = {"title": "Example Song", "id": "C8wpfQ5pdfo"}
            (root / "source.info.json").write_text(json.dumps(payload), encoding="utf-8")
            metadata = load_downloaded_metadata(root, "https://www.youtube.com/watch?v=C8wpfQ5pdfo")
            self.assertEqual(metadata.title, "Example Song")
            self.assertEqual(metadata.video_id, "C8wpfQ5pdfo")

    def test_remove_downloaded_info_json_deletes_raw_info_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            info_path = root / "source.info.json"
            info_path.write_text("{}", encoding="utf-8")
            remove_downloaded_info_json(root)
            self.assertFalse(info_path.exists())

    def test_write_metadata_summary_combines_title_and_source_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = workflow.VideoMetadata(
                title="Example Song",
                video_id="C8wpfQ5pdfo",
                normalized_url="https://www.youtube.com/watch?v=C8wpfQ5pdfo",
                safe_title="Example Song",
            )
            metadata_path = write_metadata_summary(root, metadata)
            self.assertEqual(metadata_path.name, "metadata.txt")
            self.assertEqual(
                metadata_path.read_text(encoding="utf-8"),
                "Title: Example Song\nSource URL: https://www.youtube.com/watch?v=C8wpfQ5pdfo\n",
            )


    def test_run_pipeline_keeps_source_audio_but_drops_demucs_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out_root = root / "output"
            env_prefix = root / "venv"
            bin_dir = env_prefix / "bin"
            bin_dir.mkdir(parents=True)
            python_bin = bin_dir / "python"
            python_bin.write_text("", encoding="utf-8")
            yt_dlp_bin = bin_dir / "yt-dlp"
            yt_dlp_bin.write_text("", encoding="utf-8")
            demucs_bin = bin_dir / "demucs"
            demucs_bin.write_text("", encoding="utf-8")
            ffmpeg_bin = bin_dir / "ffmpeg"
            ffmpeg_bin.write_text("", encoding="utf-8")
            tooling = Tooling(
                env_prefix=env_prefix,
                python_bin=python_bin,
                yt_dlp_bin=yt_dlp_bin,
                demucs_bin=demucs_bin,
                ffmpeg_bin=ffmpeg_bin,
            )
            options = self.make_options(out_root=out_root)
            config = AppConfig(default_model="htdemucs_ft", default_device="mps")
            metadata = workflow.VideoMetadata(
                title="Example Song",
                video_id="C8wpfQ5pdfo",
                normalized_url="https://www.youtube.com/watch?v=C8wpfQ5pdfo",
                safe_title="Example Song",
            )

            def fake_download(
                url: str,
                destination_dir: Path,
                yt_dlp_bin: Path,
                auth_session: AuthSession,
                options: RunOptions,
            ) -> Path:
                source_audio = destination_dir / "source.webm"
                source_audio.write_text("audio", encoding="utf-8")
                return source_audio

            def fake_run_demucs(
                *,
                demucs_bin: Path,
                source_audio: Path,
                model: str,
                device: str,
                out_dir: Path,
                two_stem: str | None,
                log_path: Path,
            ) -> None:
                stem_dir = out_dir / model / source_audio.stem
                stem_dir.mkdir(parents=True)
                (stem_dir / "vocals.wav").write_text("vocals", encoding="utf-8")
                log_path.write_text("ok", encoding="utf-8")

            with mock.patch.object(workflow, "resolve_tooling", return_value=tooling):
                with mock.patch.object(workflow, "resolve_device", return_value="mps"):
                    with mock.patch.object(
                        workflow,
                        "prepare_auth_session",
                        return_value=AuthSession(auth_args=[]),
                    ):
                        with mock.patch.object(
                            workflow,
                            "download_audio",
                            side_effect=fake_download,
                        ):
                            with mock.patch.object(
                                workflow,
                                "load_downloaded_metadata",
                                return_value=metadata,
                            ):
                                with mock.patch.object(
                                    workflow,
                                    "run_demucs",
                                    side_effect=fake_run_demucs,
                                ):
                                    result = workflow.run_pipeline(options, config)

            final_dir = out_root / "Example Song [C8wpfQ5pdfo]"
            self.assertEqual(result, 0)
            self.assertTrue((final_dir / "source.webm").exists())
            self.assertTrue((final_dir / "metadata.txt").exists())
            self.assertTrue((final_dir / "stems" / "vocals.wav").exists())
            self.assertFalse((final_dir / ".demucs.log").exists())

    def test_format_model_note_known_models(self) -> None:
        self.assertIsNotNone(format_model_note("htdemucs_ft"))
        self.assertIsNotNone(format_model_note("htdemucs_6s"))
        self.assertIsNone(format_model_note("htdemucs"))

    def test_resolve_device_auto_prefers_mps_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tooling = self.make_tooling(Path(directory))
            with mock.patch.object(workflow.sys, "platform", "darwin"):
                with mock.patch.object(workflow, "detect_mps_available", return_value=True):
                    self.assertEqual(resolve_device("auto", tooling), "mps")

    def test_resolve_device_auto_falls_back_to_cpu(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tooling = self.make_tooling(Path(directory))
            with mock.patch.object(workflow.sys, "platform", "linux"):
                with mock.patch.object(workflow, "detect_mps_available", return_value=False):
                    self.assertEqual(resolve_device("auto", tooling), "cpu")
