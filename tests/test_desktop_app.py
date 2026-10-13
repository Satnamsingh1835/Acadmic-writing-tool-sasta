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
    assert (root / "web" / "index.html").is_file()
