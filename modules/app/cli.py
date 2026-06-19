"""Compatibility CLI entrypoint that delegates to composer CLI."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2] / "src"))
from composer.cli import app as composer_app

def main() -> None:
    composer_app()


if __name__ == "__main__":
    main()
