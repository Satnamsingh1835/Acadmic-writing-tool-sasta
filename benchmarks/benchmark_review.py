"""Repeatable latency benchmark for short, medium, and full-length drafts."""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from academic_analyser import AcademicAnalyzer  # noqa: E402
from advanced_humanize import AdvancedHumanizer  # noqa: E402

SAMPLES = {
    "short": "Caste shapes land relations. This remains underexplored.",
    "medium": "Caste shapes land relations. " * 40,
    "full": "Caste shapes land relations. This remains underexplored. " * 400,
}


def run(rounds: int = 3) -> None:
    analyzer = AcademicAnalyzer()
    editor = AdvancedHumanizer()
    for name, text in SAMPLES.items():
        durations = []
        for _ in range(rounds):
            start = time.perf_counter()
            editor.humanize(text)
            analyzer.analyse(text)
            durations.append((time.perf_counter() - start) * 1000)
        percentile_index = min(len(durations) - 1, int(len(durations) * 0.95))
        p95 = sorted(durations)[percentile_index]
        print(
            f"{name}: median={statistics.median(durations):.2f}ms "
            f"p95={p95:.2f}ms chars={len(text)}"
        )


if __name__ == "__main__":
    run()
