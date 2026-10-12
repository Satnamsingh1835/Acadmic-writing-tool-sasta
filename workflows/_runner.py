"""Shared bootstrap for directly executable workflow scripts."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.cli import main  # noqa: E402


def run(command: str) -> int:
    return main([command, *sys.argv[1:]])
