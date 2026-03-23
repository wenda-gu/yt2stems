from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .constants import DEFAULT_CONFIG_FILE, DEFAULT_DEVICE, DEFAULT_MODEL


@dataclass(slots=True)
class AppConfig:
    env_kind: str | None = None
    env_prefix: Path | None = None
    default_model: str = DEFAULT_MODEL
    default_device: str = DEFAULT_DEVICE
    quality_margin_percent: int = 25
    python_bin: Path | None = None
    cookies_from_browser: str | None = None
    cookies_file: Path | None = None


def parse_env_text(text: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or DEFAULT_CONFIG_FILE
    if not config_path.exists():
        return AppConfig()

    raw = parse_env_text(config_path.read_text(encoding="utf-8"))
    margin = raw.get("QUALITY_MARGIN_PERCENT", "25")
    try:
        quality_margin_percent = int(margin)
    except ValueError:
        quality_margin_percent = 25

    env_prefix = Path(raw["ENV_PREFIX"]).expanduser() if raw.get("ENV_PREFIX") else None
    python_bin = Path(raw["PYTHON_BIN"]).expanduser() if raw.get("PYTHON_BIN") else None
    cookies_file = Path(raw["COOKIES_FILE"]).expanduser() if raw.get("COOKIES_FILE") else None

    return AppConfig(
        env_kind=raw.get("ENV_KIND"),
        env_prefix=env_prefix,
        default_model=raw.get("DEFAULT_MODEL", DEFAULT_MODEL),
        default_device=raw.get("DEFAULT_DEVICE", DEFAULT_DEVICE),
        quality_margin_percent=quality_margin_percent,
        python_bin=python_bin,
        cookies_from_browser=raw.get("COOKIES_FROM_BROWSER"),
        cookies_file=cookies_file,
    )


def write_config(config: AppConfig, path: Path | None = None) -> Path:
    config_path = path or DEFAULT_CONFIG_FILE
    config_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"ENV_KIND={config.env_kind or ''}".rstrip(),
        f"ENV_PREFIX={config.env_prefix}" if config.env_prefix else "",
        f"DEFAULT_MODEL={config.default_model}",
        f"DEFAULT_DEVICE={config.default_device}",
        f"QUALITY_MARGIN_PERCENT={config.quality_margin_percent}",
        f"PYTHON_BIN={config.python_bin}" if config.python_bin else "",
        (
            f"COOKIES_FROM_BROWSER={config.cookies_from_browser}"
            if config.cookies_from_browser
            else ""
        ),
        f"COOKIES_FILE={config.cookies_file}" if config.cookies_file else "",
    ]
    rendered = "\n".join(line for line in lines if line) + "\n"
    config_path.write_text(rendered, encoding="utf-8")
    return config_path
