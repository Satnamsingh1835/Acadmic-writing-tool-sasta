from pathlib import Path

from tools.repository_check import scan_repository


ROOT = Path(__file__).resolve().parents[1]


def test_every_repository_source_file_passes_static_validation():
    results = scan_repository(ROOT)
    failures = [result for result in results if not result.ok]

    assert not failures, failures
    checked_paths = {result.path for result in results}
    assert "api.py" in checked_paths
    assert "agent/cli.py" in checked_paths
    assert "web/index.html" in checked_paths
    assert "web/app.js" in checked_paths
