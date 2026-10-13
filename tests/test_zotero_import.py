import httpx
import pytest

from research_library.zotero import ZoteroConnectionError, fetch_zotero_items


def test_zotero_local_import_paginates_when_full_page_and_no_total_header():
    batches = [
        [{"key": "A", "data": {"title": "A"}}, {"key": "B", "data": {"title": "B"}}],
        [{"key": "C", "data": {"title": "C"}}],
    ]

    def handler(request):
        start = int(request.url.params.get("start", "0"))
        return httpx.Response(200, json=batches[0] if start == 0 else batches[1])

    transport = httpx.MockTransport(handler)
    result = fetch_zotero_items(source="local", limit=2, max_pages=5, transport=transport)
    assert len(result) == 3


def test_web_api_requires_credentials(monkeypatch):
    monkeypatch.delenv("ZOTERO_USER_ID", raising=False)
    monkeypatch.delenv("ZOTERO_API_KEY", raising=False)
    with pytest.raises(ZoteroConnectionError):
        fetch_zotero_items(source="web")
