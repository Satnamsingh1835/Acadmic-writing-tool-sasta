import sys

import desktop_app
from desktop_app import allocate_local_listener, app_resource_dir, health_url


def test_desktop_listener_binds_only_to_loopback():
    listener = allocate_local_listener()
    try:
        host, port = listener.getsockname()
        assert host == "127.0.0.1"
        assert isinstance(port, int) and 0 < port < 65536
    finally:
        listener.close()


def test_desktop_health_url_is_loopback_only():
    assert health_url(12345) == "http://127.0.0.1:12345/health"


def test_source_resource_root_contains_web_assets():
    root = app_resource_dir()
    for asset in ("index.html", "app.js", "styles.css", "library.html", "library.js", "library.css"):
        assert (root / "web" / asset).is_file(), asset


def test_smoke_checks_pass_against_live_server(tmp_path, monkeypatch):
    """The headless checks used by the packaged ``--smoke-test`` run."""
    monkeypatch.setenv("SCHOLARFLOW_DATA_DIR", str(tmp_path))
    server = thread = listener = None
    try:
        server, thread, listener, base_url = desktop_app._start_server()
        assert base_url.startswith("http://127.0.0.1:")
        checks = desktop_app.run_smoke_checks(base_url, app_resource_dir())
    finally:
        desktop_app._stop_server(server, thread, listener)
    failures = [name for name, passed, _ in checks if not passed]
    assert failures == [], failures
    names = {name for name, _, _ in checks}
    assert any("editor rewrite profile=polish" in name for name in names)
    assert any("library add reference" in name for name in names)
    assert any("library passage search" in name for name in names)


def test_smoke_main_uses_isolated_data_and_never_imports_webview(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOLARFLOW_DATA_DIR", str(tmp_path))
    # A None entry makes any ``import webview`` fail: the smoke path must
    # stay headless so CI can run the packaged exe without a window.
    monkeypatch.setitem(sys.modules, "webview", None)
    assert desktop_app.main([desktop_app.SMOKE_FLAG]) == 0
    # The synthetic smoke records were written to the isolated data dir.
    assert (tmp_path / "research-library.sqlite3").is_file()
    name, passed, _detail = desktop_app._smoke_persistence_check()
    assert passed, name


def test_smoke_main_defaults_to_an_isolated_temp_data_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("SCHOLARFLOW_DATA_DIR", raising=False)
    monkeypatch.setitem(sys.modules, "webview", None)
    assert desktop_app.main([desktop_app.SMOKE_FLAG]) == 0
