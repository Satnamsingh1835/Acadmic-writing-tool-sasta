"""Measure the diagnostic engine against pastes that are not prose.

The tool exists because several scans in the engine were quadratic: a real
document is fine, but a paste of dot leaders, a base64 blob or a table copied
out of a PDF made the checker take seconds to minutes, and a person notices that
as the editor freezing. The sweep times each shape at two sizes, so a scan that
is quadratic shows up as a ratio near four rather than near two. It is a
developer probe, not part of the test suite: the suite keeps loose ceilings that
catch an order-of-magnitude regression without failing on a slow shared runner.

Usage::

    python -m tools.diagnostics_timing            # the sweep
    python -m tools.diagnostics_timing --pastes   # the long single pastes

Named shapes are short so the whole sweep finishes in seconds; ``--pastes``
covers the larger, slower cases individually.
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable, Sequence

from diagnostics import DiagnosticEngine

SHAPES: dict[str, Callable[[int], str]] = {
    "open brackets": lambda n: "[" * n,
    "close brackets": lambda n: "]" * n,
    "parentheses": lambda n: "(" * n,
    "quotes": lambda n: '"' * n,
    "apostrophes": lambda n: "'" * n,
    "backticks": lambda n: "`" * n,
    "asterisks": lambda n: "*" * n,
    "underscores": lambda n: "_" * n,
    "hashes": lambda n: "#" * n,
    "pipes": lambda n: "|" * n,
    "slashes": lambda n: "/" * n,
    "colons": lambda n: ":" * n,
    "semicolons": lambda n: ";" * n,
    "exclamations": lambda n: "!" * n,
    "questions": lambda n: "?" * n,
    "dots": lambda n: "." * n,
    "commas": lambda n: "," * n,
    "spaces": lambda n: " " * n,
    "braces": lambda n: "(" * n,
    "letters": lambda n: "x" * n,
    "digits": lambda n: "1" * n,
    "at signs": lambda n: "@" * n,
    "initials": lambda n: "A." * (n // 2),
    "dot leaders": lambda n: "Intro " + "." * n + " 1",
    "ellipsis runs": lambda n: ". . . " * (n // 6),
    "sentence end runs": lambda n: "a." * (n // 2),
    "hyphen chains": lambda n: "a-" * (n // 2),
    "apostrophe chains": lambda n: "d'" * (n // 2),
    "word colons": lambda n: "word:" * (n // 5),
    "word commas": lambda n: "word," * (n // 5),
    "word stops": lambda n: "word." * (n // 5),
    "space before marks": lambda n: " ," * (n // 2),
    "space before stops": lambda n: " ." * (n // 2),
    "space before colons": lambda n: " :" * (n // 2),
    "tab before marks": lambda n: "\t," * (n // 2),
    "fences": lambda n: "```\n" * (n // 4),
    "markdown links": lambda n: "[a](b) " * (n // 7),
    "bracketed refs": lambda n: "[1]" * (n // 3),
    "parenthetical years": lambda n: "(2001) " * (n // 7),
    "citation commas": lambda n: "(Gupta, 2000) " * (n // 14),
    "urls": lambda n: "https://a.example/b " * (n // 20),
    "emails": lambda n: "a@b.co " * (n // 7),
    "mixed soup": lambda n: ". , ; : ! ? [ ] ( ) { } \" ' ` * _ - / \\ | ~" * (n // 30),
}

PASTES: dict[str, str] = {
    "40k spaces between words": "The data " + " " * 40_000 + "was analysed.",
    "40k tabs": "The data" + "\t" * 40_000 + "was analysed.",
    "40k commas": "The data" + "," * 40_000 + "was analysed.",
    "40k dots": "." * 40_000,
    "40k brackets": "[" * 40_000,
    "50k unbroken token": "x" * 50_000,
    "60k identifier": "_".join(["ab"] * 20_000),
    "66k base64 blob": "QUJDREVGR0g" * 6_000,
}


def _time(engine: DiagnosticEngine, text: str) -> float:
    started = time.perf_counter()
    engine.analyse(text)
    return time.perf_counter() - started


def sweep(engine: DiagnosticEngine, size: int) -> int:
    """Time every shape at ``size`` and twice ``size``; report outliers."""
    flagged = 0
    for name, build in SHAPES.items():
        small_text, large_text = build(size), build(size * 2)
        small, large = _time(engine, small_text), _time(engine, large_text)
        ratio = large / small if small > 1e-4 else float("inf")
        worst = max(small, large)
        # A linear scan roughly doubles; a quadratic one roughly quadruples. The
        # thresholds are deliberately loose so only a real scan stands out.
        if worst > 0.4 or (ratio > 3.2 and large > 0.05):
            flagged += 1
            print(
                f"{name:24} {len(small_text):>7,}/{len(large_text):>7,} chars "
                f"{small * 1000:>8.0f}/{large * 1000:>8.0f} ms  ratio {ratio:5.2f}  <-- CHECK"
            )
    return flagged


def pastes(engine: DiagnosticEngine) -> None:
    for name, text in PASTES.items():
        elapsed = _time(engine, text)
        note = "  <-- SLOW" if elapsed > 0.8 else ""
        print(f"{name:24} {len(text):>8,} chars {elapsed * 1000:>8.0f} ms{note}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pastes", action="store_true", help="time the long single pastes")
    parser.add_argument("--size", type=int, default=10_000, help="small sweep size in characters")
    args = parser.parse_args(argv)

    engine = DiagnosticEngine()
    # Warm up, so the dictionary load and the caches are not measured.
    engine.analyse("Warm up the dictionary and the caches.")

    if args.pastes:
        pastes(engine)
        return 0
    flagged = sweep(engine, args.size)
    print(f"sweep complete: {len(SHAPES)} shapes, {flagged} flagged")
    return 1 if flagged else 0


if __name__ == "__main__":
    raise SystemExit(main())
