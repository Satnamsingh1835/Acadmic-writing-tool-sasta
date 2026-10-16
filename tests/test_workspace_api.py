"""API tests for the writing workspace document endpoints."""

from fastapi.testclient import TestClient

import api


def client_for(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOLARFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(api, "_document_store", None)
    monkeypatch.setattr(api, "_document_store_path", None)
    monkeypatch.setattr(api, "_library_instance", None)
    monkeypatch.setattr(api, "_library_instance_path", None)
    return TestClient(api.app)


def test_workspace_page_and_assets_are_served(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)

    page = client.get("/workspace")
    assert page.status_code == 200
    assert "ScholarFlow Writing Workspace" in page.text
    assert 'id="editor"' in page.text
    for asset in ("workspace.js", "workspace.css"):
        response = client.get(f"/assets/{asset}")
        assert response.status_code == 200


def test_document_lifecycle_round_trip(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)

    created = client.post("/api/documents", json={"title": "Paper draft", "text": "# Intro\n\nText."})
    assert created.status_code == 200
    document = created.json()
    assert document["revision"] == 1
    # Markdown markers are not words: "# Intro" plus "Text." is two words.
    assert document["word_count"] == 2

    listed = client.get("/api/documents")
    assert [item["id"] for item in listed.json()["documents"]] == [document["id"]]

    saved = client.put(
        f"/api/documents/{document['id']}",
        json={"title": "Paper draft", "text": "# Intro\n\nLonger text with detail.", "expected_revision": 1, "reason": "manual"},
    )
    assert saved.status_code == 200
    assert saved.json()["revision"] == 2

    fetched = client.get(f"/api/documents/{document['id']}")
    assert fetched.json()["text"] == "# Intro\n\nLonger text with detail."


def test_stale_revision_returns_conflict_and_keeps_stored_text(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    document = client.post("/api/documents", json={"title": "Shared", "text": "Original."}).json()

    first = client.put(
        f"/api/documents/{document['id']}",
        json={"text": "Saved elsewhere.", "expected_revision": 1, "reason": "autosave"},
    )
    assert first.status_code == 200

    stale = client.put(
        f"/api/documents/{document['id']}",
        json={"text": "Stale overwrite.", "expected_revision": 1, "reason": "manual"},
    )
    assert stale.status_code == 409
    assert "another window" in stale.json()["detail"]
    assert client.get(f"/api/documents/{document['id']}").json()["text"] == "Saved elsewhere."


def test_revisions_and_restore_endpoints(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    document = client.post("/api/documents", json={"title": "History", "text": "one"}).json()
    client.put(f"/api/documents/{document['id']}", json={"text": "two", "reason": "manual"})

    history = client.get(f"/api/documents/{document['id']}/revisions")
    assert history.status_code == 200
    assert [entry["revision"] for entry in history.json()["revisions"]] == [1]

    restored = client.post(f"/api/documents/{document['id']}/revisions/1/restore")
    assert restored.status_code == 200
    assert restored.json()["text"] == "one"

    missing = client.post(f"/api/documents/{document['id']}/revisions/99/restore")
    assert missing.status_code == 404


def test_archive_and_restore_document(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    document = client.post("/api/documents", json={"title": "Temp", "text": "text"}).json()

    archived = client.delete(f"/api/documents/{document['id']}")
    assert archived.status_code == 200
    assert archived.json()["archived"] is True
    assert client.get("/api/documents").json()["documents"] == []
    assert client.get(f"/api/documents/{document['id']}").json()["text"] == "text"

    restored = client.post(f"/api/documents/{document['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["archived"] is False
    assert len(client.get("/api/documents").json()["documents"]) == 1


def test_document_endpoints_report_validation_and_missing_records(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)

    assert client.get("/api/documents/missing").status_code == 404
    assert client.put("/api/documents/missing", json={"text": "x"}).status_code == 404
    assert client.delete("/api/documents/missing").status_code == 404
    assert client.get("/api/documents/missing/revisions").status_code == 404

    document = client.post("/api/documents", json={"title": "Guard", "text": "text"}).json()
    assert client.put(
        f"/api/documents/{document['id']}", json={"text": "x", "reason": "restore"}
    ).status_code == 400
    assert client.post("/api/documents", json={"title": "x" * 301}).status_code == 422
    assert client.get("/api/documents", params={"q": "x" * 201}).status_code == 422


def test_documents_survive_a_fresh_store_instance(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    document = client.post("/api/documents", json={"title": "Persistent", "text": "kept"}).json()

    # Simulate an application restart by dropping the cached store instance.
    monkeypatch.setattr(api, "_document_store", None)
    monkeypatch.setattr(api, "_document_store_path", None)

    fetched = client.get(f"/api/documents/{document['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["text"] == "kept"


def test_workspace_does_not_break_the_research_library(tmp_path, monkeypatch):
    """Preserve existing functionality: the library endpoints stay available."""
    client = client_for(tmp_path, monkeypatch)

    assert client.get("/api/library/health").status_code == 200
    client.post("/api/documents", json={"title": "Unrelated doc", "text": "text"})
    assert client.get("/library").status_code == 200
    assert client.get("/api/library/search", params={"q": "anything"}).status_code == 200
