from __future__ import annotations

import sys

from .config import load_config
from .utils import CliError
from .workflow import parse_args, run_pipeline


def main(argv: list[str] | None = None) -> int:
    config = load_config()
    try:
        options = parse_args(argv, config)
        return run_pipeline(options, config)
    except CliError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
