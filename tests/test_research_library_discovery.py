import json

import httpx

from research_library.discovery import DiscoveryService, normalize_crossref
from research_library.store import ResearchLibrary


def test_crossref_discovery_normalises_and_caches_results(tmp_path):
    calls = {"count": 0}

    def handler(request):
        calls["count"] += 1
        return httpx.Response(200, json={
            "message": {"items": [{
                "title": ["Village land and caste"],
                "DOI": "10.1234/example",
                "author": [{"given": "A", "family": "Scholar"}],
                "published": {"date-parts": [[2022]]},
                "URL": "https://doi.org/10.1234/example",
            }]}
        })

    library = ResearchLibrary(tmp_path / "library.sqlite3")
    service = DiscoveryService(library, transport=httpx.MockTransport(handler))
    first = service.search("crossref", "village land", limit=5)
    second = service.search("crossref", "village land", limit=5)
    service.close()
    assert first["status"] == "live"
    assert first["results"][0]["title"] == "Village land and caste"
    assert first["results"][0]["metadata_verified"] is False
    assert second["status"] == "cached"
    assert calls["count"] == 1


def test_offline_cache_miss_is_explicit(tmp_path):
    library = ResearchLibrary(tmp_path / "library.sqlite3")
    service = DiscoveryService(library, transport=httpx.MockTransport(
        lambda request: httpx.Response(500)
    ))
    result = service.search("openalex", "commons", offline=True)
    service.close()
    assert result["status"] == "offline_cache_miss"
    assert result["results"] == []


def test_normalize_crossref_does_not_claim_verification():
    record = normalize_crossref({
        "title": ["Synthetic title"],
        "DOI": "10.1234/test",
        "author": [{"given": "A", "family": "B"}],
        "issued": {"date-parts": [[2021]]},
    })
    assert record["year"] == 2021
    assert record["metadata_verified"] is False
