from __future__ import annotations

import logging
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

STARTUP_TIMEOUT_SECONDS = 25.0
HEALTH_PATH = "/health"


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
    except Exception:
        print(message, file=sys.stderr)


def main() -> int:
    log_path = None
    server = None
    thread = None
    listener = None
    try:
        log_path = _configure_log()
        root = app_resource_dir()
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        if not (root / "web" / "index.html").is_file():
            raise RuntimeError("ScholarFlow web assets are missing from the application package.")
        import uvicorn
        import webview
        from api import app
        listener = allocate_local_listener()
        port = listener.getsockname()[1]
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False, server_header=False, date_header=False)
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, name="scholarflow-local-api", daemon=True)
        thread.start()
        base_url = "http://127.0.0.1:" + str(port)
        wait_for_health(base_url + HEALTH_PATH, server, thread)
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
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=5)
        if listener is not None:
            try:
                listener.close()
            except OSError:
                pass


if __name__ == "__main__":
    if sys.platform == "win32":
        from multiprocessing import freeze_support
        freeze_support()
    raise SystemExit(main())
