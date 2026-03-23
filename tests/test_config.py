from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from yt2stems.config import AppConfig, load_config, parse_env_text, write_config


class ConfigTests(unittest.TestCase):
    def test_parse_env_text_ignores_comments_and_blank_lines(self) -> None:
        raw = """
        # comment
        DEFAULT_MODEL=htdemucs

        DEFAULT_DEVICE=mps
        """
        parsed = parse_env_text(raw)
        self.assertEqual(parsed, {"DEFAULT_MODEL": "htdemucs", "DEFAULT_DEVICE": "mps"})

    def test_write_and_load_config_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            path = tmp_path / "config.env"
            original = AppConfig(
                env_kind="venv",
                env_prefix=tmp_path / "venv",
                default_model="htdemucs",
                default_device="cpu",
                quality_margin_percent=10,
                python_bin=tmp_path / "venv" / "bin" / "python",
                cookies_from_browser="safari",
            )
            write_config(original, path)
            loaded = load_config(path)
            self.assertEqual(loaded.env_kind, "venv")
            self.assertEqual(loaded.env_prefix, original.env_prefix)
            self.assertEqual(loaded.default_model, "htdemucs")
            self.assertEqual(loaded.default_device, "cpu")
            self.assertEqual(loaded.quality_margin_percent, 10)
            self.assertEqual(loaded.cookies_from_browser, "safari")
