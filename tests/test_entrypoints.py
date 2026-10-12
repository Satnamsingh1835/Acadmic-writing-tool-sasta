import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_script(path, *arguments):
    return subprocess.run(
        [sys.executable, str(path), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_every_workflow_wrapper_runs_directly():
    wrappers = sorted(
        path
        for path in (ROOT / "workflows").glob("*.py")
        if not path.name.startswith("_")
    )

    failures = []
    for wrapper in wrappers:
        result = run_script(wrapper, "--help")
        if result.returncode != 0:
            failures.append((wrapper.name, result.stderr))
        assert "usage:" in result.stdout.lower(), wrapper.name

    assert not failures, failures


def test_benchmark_runs_directly():
    result = run_script(ROOT / "benchmarks" / "benchmark_review.py")

    assert result.returncode == 0, result.stderr
    assert "short: median=" in result.stdout
    assert "full: median=" in result.stdout
