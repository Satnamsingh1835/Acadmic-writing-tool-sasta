"""Validate tracked repository files one by one.

This complements behavioural tests: Python files are compiled independently,
JSON and YAML files are parsed, and all remaining tracked text files are
checked for UTF-8 readability and accidental NUL bytes.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileCheck:
    path: str
    check: str
    ok: bool
    detail: str = ""


def repository_files(root: Path) -> list[Path]:
    """Return tracked and unignored source files in the repository."""
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            check=True,
            capture_output=True,
        )
        names = [name for name in result.stdout.decode("utf-8").split("\0") if name]
        return [root / name for name in names]
    except (FileNotFoundError, subprocess.CalledProcessError, UnicodeDecodeError):
        return sorted(
            path
            for path in root.rglob("*")
            if path.is_file() and ".git" not in path.parts
        )


def _check_python(path: Path, text: str) -> None:
    compile(text, str(path), "exec")


def _check_json(text: str) -> None:
    json.loads(text)


def _check_yaml(text: str) -> None:
    try:
        import yaml
    except ImportError:
        # UTF-8 and NUL checks still run when optional YAML tooling is absent.
        return
    yaml.safe_load(text)


def check_file(path: Path, root: Path) -> FileCheck:
    relative = path.relative_to(root).as_posix()
    if not path.exists():
        return FileCheck(relative, "existence", False, "Tracked file is missing.")

    try:
        text = path.read_text(encoding="utf-8")
        if "\x00" in text:
            raise ValueError("Text file contains a NUL byte.")

        suffix = path.suffix.lower()
        if suffix == ".py":
            _check_python(path, text)
            check = "python-compile"
        elif suffix == ".json":
            _check_json(text)
            check = "json-parse"
        elif suffix in {".yml", ".yaml"}:
            _check_yaml(text)
            check = "yaml-parse"
        else:
            check = "utf8-text"

        if not text.strip() and path.name != "__init__.py":
            raise ValueError("Tracked text file is empty.")
        return FileCheck(relative, check, True)
    except (OSError, SyntaxError, UnicodeError, ValueError) as exc:
        return FileCheck(relative, "validation", False, str(exc))
    except Exception as exc:  # YAML parsers use provider-specific exception types.
        return FileCheck(relative, "validation", False, f"{type(exc).__name__}: {exc}")


def scan_repository(root: Path) -> list[FileCheck]:
    root = root.resolve()
    return [check_file(path, root) for path in repository_files(root)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    results = scan_repository(args.root)
    failures = [result for result in results if not result.ok]

    if args.as_json:
        print(json.dumps([asdict(result) for result in results], indent=2))
    else:
        for result in results:
            status = "PASS" if result.ok else "FAIL"
            detail = f" — {result.detail}" if result.detail else ""
            print(f"[{status}] {result.path} ({result.check}){detail}")
        print(f"\nChecked {len(results)} repository files: {len(failures)} failure(s).")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
