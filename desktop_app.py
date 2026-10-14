from __future__ import annotations

import json
import logging
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

STARTUP_TIMEOUT_SECONDS = 25.0
HEALTH_PATH = "/health"
SMOKE_FLAG = "--smoke-test"
SMOKE_REPORT_FLAG = "--smoke-report"


def app_resource_dir() -> Path:
    """Resolve source and PyInstaller resource roots."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    return Path(frozen_root).resolve() if frozen_root else Path(__file__).resolve().parent


def allocate_local_listener() -> socket.socket:
    """Reserve an ephemeral IPv4 loopback listener before starting Uvicorn."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    return listener


def health_url(port: int) -> str:
    return "http://127.0.0.1:" + str(int(port)) + HEALTH_PATH


def wait_for_health(url: str, server, thread: threading.Thread, timeout: float = STARTUP_TIMEOUT_SECONDS) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if not thread.is_alive():
            raise RuntimeError("ScholarFlow's local web server stopped during startup.")
        if getattr(server, "started", False):
            try:
                with urllib.request.urlopen(url, timeout=0.8) as response:
                    if response.status == 200:
                        return
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
        time.sleep(0.15)
    message = "ScholarFlow's local server did not become healthy within the startup timeout."
    if last_error:
        message += " Last health-check error: " + type(last_error).__name__
    raise RuntimeError(message)


def _configure_log() -> Path:
    from research_library.store import default_data_dir
    log_dir = default_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "desktop.log"
    logging.basicConfig(filename=str(log_path), level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    return log_path


def _show_error(message: str) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, "ScholarFlow could not start", 0x10)
        return
    except Exception:
        pass
    try:
        print(message, file=sys.stderr)
    except (AttributeError, OSError, ValueError):
        pass


def _start_server():
    """Start the loopback API server exactly as the desktop window does.

    Returns ``(server, thread, listener, base_url)``. The caller owns
    shutdown via :func:`_stop_server`. ``webview`` is deliberately not
    imported here so headless checks exercise the same server path.
    """
    import uvicorn
    from api import app
    listener = allocate_local_listener()
    port = listener.getsockname()[1]
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False, server_header=False, date_header=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, name="scholarflow-local-api", daemon=True)
    thread.start()
    base_url = "http://127.0.0.1:" + str(port)
    try:
        wait_for_health(base_url + HEALTH_PATH, server, thread)
    except Exception:
        _stop_server(server, thread, listener)
        raise
    return server, thread, listener, base_url


def _stop_server(server, thread, listener) -> None:
    if server is not None:
        server.should_exit = True
    if thread is not None:
        thread.join(timeout=5)
    if listener is not None:
        try:
            listener.close()
        except OSError:
            pass


def _prepare_resource_root() -> Path:
    root = app_resource_dir()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if not (root / "web" / "index.html").is_file():
        raise RuntimeError("ScholarFlow web assets are missing from the application package.")
    return root


def ensure_standard_streams() -> None:
    """Make stdout/stderr usable in a PyInstaller windowed build.

    A ``console=False`` executable has no console attached: ``sys.stdout``
    and ``sys.stderr`` are ``None`` and any ``print()`` raises
    ``AttributeError``. Attach to the parent console when one exists (so a
    terminal launch shows output) and fall back to a sink otherwise, so
    logging and diagnostics can never crash the application.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    if os.name == "nt":
        try:
            import ctypes
            if ctypes.windll.kernel32.AttachConsole(-1):  # ATTACH_PARENT_PROCESS
                if sys.stdout is None:
                    sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
                if sys.stderr is None:
                    sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w", encoding="utf-8")
    except OSError:
        pass


def smoke_report_path(explicit: str | None = None) -> Path:
    """Report file for smoke runs so results survive a windowed build."""
    if explicit:
        return Path(explicit).expanduser()
    from research_library.store import default_data_dir
    return default_data_dir() / "logs" / "smoke-test.log"


def _write_line(line: str, report) -> None:
    """Write a smoke line to the report file and, when possible, the console."""
    if report is not None:
        try:
            report.write(line + "\n")
            report.flush()
        except OSError:
            pass
    try:
        print(line, flush=True)
    except (AttributeError, OSError, ValueError):
        pass


# ---------------------------------------------------------------------------
# Headless smoke test
#
# ``ScholarFlow.exe --smoke-test`` (or ``python desktop_app.py
# --smoke-test``) starts the real local server -- without importing
# pywebview or opening a window -- and exercises the editor and research
# library with synthetic records only. It never touches the user's real
# library: unless SCHOLARFLOW_DATA_DIR is already set, an isolated
# temporary data directory is used. Only check names and HTTP status
# codes are printed/logged; no passage or document text is recorded.
# ---------------------------------------------------------------------------

_SMOKE_TEXT = (
    "It is important to note that caste plays a crucial role in shaping "
    "access to village commons (Gupta, 2000). The issue remains underexplored."
)


def _smoke_request(base_url: str, method: str, path: str, payload=None, raw: bytes | None = None, content_type: str | None = None):
    data = raw
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(base_url + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, body
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def _smoke_json(base_url: str, method: str, path: str, payload=None):
    status, body = _smoke_request(base_url, method, path, payload=payload)
    try:
        return status, json.loads(body) if body else {}
    except json.JSONDecodeError:
        return status, {}


def run_smoke_checks(base_url: str, root: Path) -> list[tuple[str, bool, str]]:
    """Run editor/library checks against a running server.

    Returns ``(name, passed, detail)`` rows. Details contain only status
    codes and counts, never user or synthetic passage text.
    """
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, passed: bool, detail: str = "") -> None:
        checks.append((name, bool(passed), detail))

    web_dir = root / "web"
    for asset in (
        "index.html",
        "app.js",
        "styles.css",
        "library.html",
        "library.js",
        "library.css",
        "workspace.html",
        "workspace.js",
        "workspace.css",
    ):
        record("bundled asset web/" + asset, (web_dir / asset).is_file())

    for name, path in (
        ("editor page /", "/"),
        ("editor script /assets/app.js", "/assets/app.js"),
        ("editor styles /assets/styles.css", "/assets/styles.css"),
        ("writing workspace page /workspace", "/workspace"),
        ("workspace script /assets/workspace.js", "/assets/workspace.js"),
        ("workspace styles /assets/workspace.css", "/assets/workspace.css"),
        ("library page /library", "/library"),
        ("library script /assets/library.js", "/assets/library.js"),
        ("library styles /assets/library.css", "/assets/library.css"),
    ):
        status, _ = _smoke_request(base_url, "GET", path)
        record(name, status == 200, "HTTP " + str(status))

    status, payload = _smoke_json(base_url, "GET", "/health")
    record("health endpoint", status == 200 and payload.get("status") == "ok", "HTTP " + str(status))

    status, payload = _smoke_json(base_url, "GET", "/editor/capabilities")
    record(
        "editor capabilities",
        status == 200 and "llm_available" in payload and payload.get("default_profile") == "standard",
        "HTTP " + str(status),
    )

    for profile in ("conservative", "standard", "polish"):
        status, payload = _smoke_json(
            base_url, "POST", "/editor/rewrite",
            {"text": _SMOKE_TEXT, "profile": profile, "use_llm": False},
        )
        record(
            "editor rewrite profile=" + profile,
            status == 200
            and bool(str(payload.get("refined_text") or "").strip())
            and isinstance(payload.get("receipt"), dict)
            and isinstance(payload.get("safeguards"), dict),
            "HTTP " + str(status),
        )

    # The editor must stay usable when no AI provider is configured.
    status, payload = _smoke_json(
        base_url, "POST", "/editor/rewrite",
        {"text": _SMOKE_TEXT, "profile": "standard", "use_llm": True},
    )
    record(
        "editor rewrite with AI requested (local fallback kept)",
        status == 200 and bool(str(payload.get("refined_text") or "").strip()),
        "HTTP " + str(status) + " provider=" + str(payload.get("provider") or ""),
    )

    status, payload = _smoke_json(base_url, "GET", "/api/library/health")
    record(
        "library health",
        status == 200 and payload.get("status") == "ok" and "work_count" in payload,
        "HTTP " + str(status),
    )
    status, payload = _smoke_json(base_url, "GET", "/api/library/settings")
    record("library settings", status == 200 and "offline" in payload, "HTTP " + str(status))

    marker = "smoke" + uuid.uuid4().hex[:8]
    status, created = _smoke_json(
        base_url, "POST", "/api/library/work",
        {"record": {
            "title": "Synthetic smoke record " + marker,
            "authors": ["Smoke Tester"],
            "year": 2024,
            "abstract": "Synthetic record for automated smoke checks.",
        }},
    )
    work_id = str(created.get("id") or "")
    record("library add reference", status == 200 and bool(work_id), "HTTP " + str(status))

    status, payload = _smoke_json(base_url, "GET", "/api/library/search?q=" + marker)
    record(
        "library search finds added reference",
        status == 200 and any(row.get("id") == work_id for row in payload.get("results", [])),
        "HTTP " + str(status),
    )

    status, payload = _smoke_json(
        base_url, "POST", "/api/library/import/csl-json",
        {"records": [{
            "title": "Synthetic CSL smoke record " + marker,
            "author": [{"given": "Smoke", "family": "Tester"}],
            "issued": {"date-parts": [[2023]]},
            "type": "article-journal",
        }]},
    )
    record("library CSL JSON import", status == 200 and payload.get("imported", 0) >= 1, "HTTP " + str(status))

    boundary = "----scholarflow-smoke-" + uuid.uuid4().hex
    document_text = "Synthetic indexed passage about village commons and " + marker + "."
    multipart = (
        "--" + boundary + "\r\n"
        'Content-Disposition: form-data; name="file"; filename="smoke.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n" + document_text + "\r\n"
        "--" + boundary + "--\r\n"
    ).encode("utf-8")
    # urllib needs the raw multipart body, so issue this one directly.
    status, body = _smoke_request(
        base_url, "POST", "/api/library/documents", raw=multipart,
        content_type="multipart/form-data; boundary=" + boundary,
    )
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        payload = {}
    record(
        "library TXT document indexing",
        status == 200 and int(payload.get("passages_indexed") or 0) >= 1,
        "HTTP " + str(status),
    )

    status, payload = _smoke_json(base_url, "GET", "/api/library/passages?q=" + marker)
    record(
        "library passage search",
        status == 200 and len(payload.get("results", [])) >= 1,
        "HTTP " + str(status),
    )

    if work_id:
        status, _payload = _smoke_json(
            base_url, "POST", "/api/library/matrix",
            {"work_id": work_id, "research_question": "Synthetic smoke question?"},
        )
        record("library matrix add", status == 200, "HTTP " + str(status))
        status, payload = _smoke_json(base_url, "GET", "/api/library/matrix")
        record(
            "library matrix list",
            status == 200 and any(row.get("work_id") == work_id for row in payload.get("results", [])),
            "HTTP " + str(status),
        )
    else:
        record("library matrix add", False, "no work id from add-reference check")
        record("library matrix list", False, "no work id from add-reference check")

    created_text = (
        "# Synthetic smoke draft\n\nIt is important to note that this passage exists "
        "only for automated smoke checks."
    )
    saved_text = "# Synthetic smoke draft\n\nThe synthetic passage was edited by the smoke check."
    status, created = _smoke_json(
        base_url,
        "POST",
        "/api/documents",
        {"title": "Synthetic smoke document " + marker, "text": created_text},
    )
    document_id = created.get("id") if isinstance(created, dict) else None
    record("writing workspace create document", status == 200 and bool(document_id), "HTTP " + str(status))

    if document_id:
        document_path = "/api/documents/" + document_id
        title = "Synthetic smoke document " + marker
        status, saved = _smoke_json(
            base_url,
            "PUT",
            document_path,
            {"title": title, "text": saved_text, "expected_revision": 1, "reason": "manual"},
        )
        revision = saved.get("revision") if isinstance(saved, dict) else None
        record(
            "writing workspace save document",
            status == 200 and isinstance(revision, int) and revision > 1,
            "HTTP " + str(status),
        )

        status, reopened = _smoke_json(base_url, "GET", document_path)
        record(
            "writing workspace reopen document",
            status == 200 and reopened.get("text") == saved_text,
            "HTTP " + str(status),
        )

        status, payload = _smoke_json(base_url, "GET", document_path + "/revisions")
        history = payload.get("revisions", []) if isinstance(payload, dict) else []
        record(
            "writing workspace revision history",
            status == 200 and any(entry.get("revision") == 1 for entry in history),
            "HTTP " + str(status) + " revisions=" + str(len(history)),
        )

        status, restored = _smoke_json(base_url, "POST", document_path + "/revisions/1/restore")
        record(
            "writing workspace restore revision",
            status == 200 and restored.get("text") == created_text,
            "HTTP " + str(status),
        )
        status, payload = _smoke_json(base_url, "GET", document_path + "/revisions")
        history = payload.get("revisions", []) if isinstance(payload, dict) else []
        before_restore = [entry for entry in history if entry.get("reason") == "before-restore"]
        record(
            "writing workspace restore keeps the replaced text",
            status == 200 and bool(before_restore),
            "HTTP " + str(status),
        )
        if before_restore:
            status, reverted = _smoke_json(
                base_url,
                "POST",
                document_path + "/revisions/" + str(before_restore[0].get("revision")) + "/restore",
            )
            record(
                "writing workspace restore is reversible",
                status == 200 and reverted.get("text") == saved_text,
                "HTTP " + str(status),
            )
        else:
            record("writing workspace restore is reversible", False, "no before-restore snapshot")

        status, _conflict = _smoke_json(
            base_url,
            "PUT",
            document_path,
            {"title": "stale write", "text": "stale write", "expected_revision": 1, "reason": "manual"},
        )
        record("writing workspace stale save refused", status == 409, "HTTP " + str(status))
        status, after = _smoke_json(base_url, "GET", document_path)
        record(
            "writing workspace text survived the refused write",
            status == 200 and after.get("text") == saved_text,
            "HTTP " + str(status),
        )
        # Stage 2: the deterministic diagnostics must work inside the packaged
        # application, which also proves the bundled spelling dictionary was
        # collected (a frozen build without it reports no spelling findings).
        diagnostic_text = (
            "There is many studies about this tehnique. The data is unclear. "
            "because the sample size was small."
        )
        status, report = _smoke_json(
            base_url,
            "POST",
            "/api/workspace/diagnostics",
            {"text": diagnostic_text, "document_id": document_id, "revision": 1},
        )
        findings = report.get("diagnostics", []) if isinstance(report, dict) else []
        record(
            "workspace diagnostics endpoint",
            status == 200 and len(findings) >= 3,
            "HTTP " + str(status) + " findings=" + str(len(findings)),
        )
        exact = all(
            diagnostic_text[item.get("start", 0):item.get("end", 0)] == item.get("original")
            for item in findings
        )
        record("workspace diagnostics offsets are exact", bool(findings) and exact)
        spelling = [item for item in findings if item.get("category") == "spelling"]
        record(
            "workspace bundled dictionary works when frozen",
            bool(spelling) and any(item.get("replacement") for item in spelling),
            "spelling findings=" + str(len(spelling)),
        )
        by_kind = {item.get("kind") for item in findings}
        record(
            "workspace diagnostics separate errors from style",
            {"error", "style"} <= by_kind,
            "kinds=" + ",".join(sorted(str(kind) for kind in by_kind)),
        )
        record(
            "workspace diagnostics stay local",
            isinstance(report, dict)
            and report.get("engine", {}).get("external_services") == "none",
        )

        marker = "smokeword" + uuid.uuid4().hex[:6]
        status, payload = _smoke_json(base_url, "POST", "/api/workspace/dictionary", {"word": marker})
        record(
            "workspace personal dictionary add",
            status == 200 and marker in payload.get("words", []),
            "HTTP " + str(status),
        )
        status, report = _smoke_json(
            base_url,
            "POST",
            "/api/workspace/diagnostics",
            {"text": "The " + marker + " settlement shaped tenure."},
        )
        record(
            "workspace personal dictionary suppresses a word",
            status == 200
            and not any(item.get("original") == marker for item in report.get("diagnostics", [])),
            "HTTP " + str(status),
        )
        status, payload = _smoke_json(base_url, "DELETE", "/api/workspace/dictionary/" + marker)
        record(
            "workspace personal dictionary remove",
            status == 200 and marker not in payload.get("words", []),
            "HTTP " + str(status),
        )
        status, payload = _smoke_json(base_url, "GET", "/api/documents/" + document_id)
        record(
            "workspace diagnostics never write to the document",
            status == 200 and payload.get("text") == saved_text,
            "HTTP " + str(status),
        )
    else:
        for name in (
            "writing workspace save document",
            "writing workspace reopen document",
            "writing workspace revision history",
            "writing workspace restore revision",
            "writing workspace restore keeps the replaced text",
            "writing workspace restore is reversible",
            "writing workspace stale save refused",
            "writing workspace text survived the refused write",
            "workspace diagnostics endpoint",
            "workspace diagnostics offsets are exact",
            "workspace bundled dictionary works when frozen",
            "workspace diagnostics separate errors from style",
            "workspace diagnostics stay local",
            "workspace personal dictionary add",
            "workspace personal dictionary suppresses a word",
            "workspace personal dictionary remove",
            "workspace diagnostics never write to the document",
        ):
            record(name, False, "no document id from the create check")

    return checks


def _smoke_persistence_check() -> tuple[str, bool, str]:
    """Reopen the smoke databases from disk to prove writes persisted."""
    try:
        from research_library.store import ResearchLibrary, default_data_dir
        db_path = default_data_dir() / "research-library.sqlite3"
        if not db_path.is_file():
            return ("library database persisted to disk", False, "database file missing")
        library = ResearchLibrary(db_path)
        return (
            "library database persisted to disk",
            library.count_works() >= 1 and library.count_documents() >= 1,
            "works=" + str(library.count_works()) + " documents=" + str(library.count_documents()),
        )
    except Exception as exc:  # Report the type only; never log contents.
        return ("library database persisted to disk", False, type(exc).__name__)


def _smoke_document_persistence_check() -> tuple[str, bool, str]:
    """Reopen the writing-workspace database to prove the text persisted."""
    try:
        from document_store import DocumentStore
        from research_library.store import default_data_dir
        db_path = default_data_dir() / "writing-documents.sqlite3"
        if not db_path.is_file():
            return ("writing workspace database persisted to disk", False, "database file missing")
        store = DocumentStore(db_path)
        return (
            "writing workspace database persisted to disk",
            store.count() >= 1,
            "documents=" + str(store.count()),
        )
    except Exception as exc:  # Report the type only; never log contents.
        return ("writing workspace database persisted to disk", False, type(exc).__name__)


def smoke_main(argv: list[str] | None = None) -> int:
    """Headless verification used by CI and by ``--smoke-test`` runs."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    ensure_standard_streams()
    explicit_report = None
    if SMOKE_REPORT_FLAG in arguments:
        index = arguments.index(SMOKE_REPORT_FLAG)
        if index + 1 < len(arguments):
            explicit_report = arguments[index + 1]
    isolated = not os.getenv("SCHOLARFLOW_DATA_DIR")
    if isolated:
        # Set before any research_library/api import reads the data dir so
        # the smoke run can never write to the user's real library.
        os.environ["SCHOLARFLOW_DATA_DIR"] = tempfile.mkdtemp(prefix="scholarflow-smoke-")
    server = thread = listener = None
    report = None
    report_path = None
    try:
        report_path = smoke_report_path(explicit_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = report_path.open("w", encoding="utf-8")
    except OSError:
        report = None
    try:
        log_path = _configure_log()
        root = _prepare_resource_root()
        server, thread, listener, base_url = _start_server()
        checks = run_smoke_checks(base_url, root)
        _stop_server(server, thread, listener)
        server = thread = listener = None
        checks.append(_smoke_persistence_check())
        checks.append(_smoke_document_persistence_check())
        failed = 0
        for name, passed, detail in checks:
            line = ("SMOKE PASS " if passed else "SMOKE FAIL ") + name + ((" :: " + detail) if detail else "")
            _write_line(line, report)
            logging.info(line) if passed else logging.error(line)
            failed += 0 if passed else 1
        _write_line("Smoke data directory" + (" (isolated)" if isolated else "") + ": " + os.environ["SCHOLARFLOW_DATA_DIR"], report)
        _write_line("Diagnostic log: " + str(log_path), report)
        if report_path is not None:
            _write_line("Smoke report: " + str(report_path), report)
        _write_line("SMOKE RESULT: " + ("PASS" if failed == 0 else "FAIL (" + str(failed) + " check(s) failed)"), report)
        return 0 if failed == 0 else 1
    except Exception as exc:
        logging.exception("ScholarFlow smoke test failed")
        _write_line("SMOKE FAIL startup :: " + type(exc).__name__ + ": " + str(exc), report)
        _write_line("SMOKE RESULT: FAIL (startup)", report)
        return 1
    finally:
        if report is not None:
            report.close()
        _stop_server(server, thread, listener)


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    ensure_standard_streams()
    if SMOKE_FLAG in arguments:
        return smoke_main(arguments)
    log_path = None
    server = None
    thread = None
    listener = None
    try:
        log_path = _configure_log()
        _prepare_resource_root()
        import webview
        server, thread, listener, base_url = _start_server()
        window = webview.create_window("ScholarFlow", base_url, width=1440, height=960, min_size=(1000, 680))
        window.events.closed += lambda *_args: setattr(server, "should_exit", True)
        webview.start(debug=False)
        return 0
    except Exception as exc:
        logging.exception("ScholarFlow desktop startup failed")
        detail = "ScholarFlow could not start.\n\n" + str(exc)
        if log_path:
            detail += "\n\nDiagnostic log: " + str(log_path)
        _show_error(detail)
        return 1
    finally:
        _stop_server(server, thread, listener)


if __name__ == "__main__":
    if sys.platform == "win32":
        from multiprocessing import freeze_support
        freeze_support()
    raise SystemExit(main())
