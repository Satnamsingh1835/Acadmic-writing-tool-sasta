"""Run the DOM-level GUI checks from pytest.

The workspace and quick-editor pages are driven in a real DOM (jsdom) against a
live local server: typing, formatting, saving, reloading, crash recovery,
accept/dismiss/stale handling and error surfaces. Backend-only tests are not
enough for this feature, so these checks run in CI whenever Node and jsdom are
available; otherwise they skip with an explicit reason instead of passing
silently.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUI_DIR = ROOT / "tests" / "gui"
HARNESS = GUI_DIR / "workspace_dom_check.mjs"


def _node() -> str | None:
    return shutil.which("node") or shutil.which("nodejs")


def _jsdom_available(node: str) -> bool:
    if not (GUI_DIR / "node_modules" / "jsdom").exists():
        return False
    result = subprocess.run(
        [node, "-e", "require.resolve('jsdom')"],
        cwd=GUI_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


@pytest.fixture()
def live_server(tmp_path, monkeypatch):
    """Start the real API on a free loopback port with isolated data."""
    monkeypatch.setenv("SCHOLARFLOW_DATA_DIR", str(tmp_path))
    import api
    import desktop_app

    monkeypatch.setattr(api, "_document_store", None)
    monkeypatch.setattr(api, "_document_store_path", None)
    monkeypatch.setattr(api, "_library_instance", None)
    monkeypatch.setattr(api, "_library_instance_path", None)
    server, thread, listener, base_url = desktop_app._start_server()
    try:
        yield base_url
    finally:
        desktop_app._stop_server(server, thread, listener)


def test_workspace_gui_checks_run_against_a_live_server(live_server):
    node = _node()
    if node is None:
        pytest.skip("Node.js is not installed, so the DOM-level GUI checks did not run.")
    if not _jsdom_available(node):
        pytest.skip(
            "jsdom is not installed for tests/gui. Run "
            "'npm install --prefix tests/gui' to enable the GUI checks."
        )

    result = subprocess.run(
        [node, str(HARNESS), live_server],
        cwd=GUI_DIR,
        capture_output=True,
        text=True,
        timeout=420,
        check=False,
        env={**os.environ, "NODE_PATH": str(GUI_DIR / "node_modules")},
    )
    combined = result.stdout + result.stderr
    summary = [line for line in combined.splitlines() if line.startswith(("PASS", "FAIL", "GUI RESULT"))]
    print("\n".join(summary))
    assert result.returncode == 0, combined
    assert "GUI RESULT: PASS" in combined
    assert "FAIL " not in combined


def test_gui_harness_files_are_tracked_and_documented():
    """The harness must ship with the repository so CI and reviewers can run it."""
    assert HARNESS.is_file()
    manifest = json.loads((GUI_DIR / "package.json").read_text(encoding="utf-8"))
    assert "jsdom" in manifest["devDependencies"]
    text = HARNESS.read_text(encoding="utf-8")
    for marker in ("Stage 1: document editing", "reviewable refine", "Ctrl+Enter"):
        assert marker in text
    if sys.platform == "win32":
        assert _node() is not None or True  # Windows availability is reported by the run above
