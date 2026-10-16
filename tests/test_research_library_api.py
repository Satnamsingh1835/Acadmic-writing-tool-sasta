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


def test_library_page_has_a_working_add_reference_form(tmp_path, monkeypatch):
    """Regression: the library UI must expose POST /api/library/work.

    Previously the endpoint existed but no form or button reached it, so a
    reference could not be added from the Research Library at all.
    """
    monkeypatch.setenv("SCHOLARFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(api, "_library_instance", None)
    monkeypatch.setattr(api, "_library_instance_path", None)
    client = TestClient(api.app)
    page = client.get("/library")
    assert page.status_code == 200
    assert 'id="add-work-form"' in page.text
    assert 'id="add-title"' in page.text
    script = client.get("/assets/library.js")
    assert script.status_code == 200
    assert 'byId("add-work-form")' in script.text
    assert '"/api/library/work"' in script.text
    # The form's endpoint persists: a fresh store on the same file sees it.
    created = client.post("/api/library/work", json={
        "record": {"title": "Synthetic persistent reference", "authors": ["Test Researcher"], "year": 2022}
    })
    assert created.status_code == 200
    from research_library.store import ResearchLibrary
    reopened = ResearchLibrary(tmp_path / "research-library.sqlite3")
    assert reopened.count_works() >= 1
    assert reopened.search_works(q="persistent reference")
