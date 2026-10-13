from fastapi.testclient import TestClient

import api


def test_library_api_import_search_and_evidence_warning(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOLARFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(api, "_library_instance", None)
    monkeypatch.setattr(api, "_library_instance_path", None)
    client = TestClient(api.app)
    created = client.post("/api/library/work", json={
        "record": {
            "title": "Synthetic common land article",
            "authors": ["Test Researcher"],
            "year": 2020,
            "abstract": "A synthetic record about village land",
        }
    })
    assert created.status_code == 200
    found = client.get("/api/library/search", params={"q": "common land"})
    assert found.status_code == 200
    assert found.json()["results"]
    brief = client.post("/api/library/evidence-brief", json={"query": "nonexistent topic"})
    assert brief.status_code == 200
    assert brief.json()["status"] == "insufficient_evidence"
    assert "not proof" in brief.json()["warning"]
    assert client.get("/library").status_code == 200
