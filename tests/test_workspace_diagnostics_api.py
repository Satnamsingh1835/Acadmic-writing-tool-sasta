"""API tests for the writing-workspace diagnostics endpoints.

These check the contract the editor relies on: schema, exact offsets in the
returned text, the category list, validation, the personal dictionary and the
privacy guarantee that no document text is echoed back in an error.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import api
from diagnostics import MAX_DOCUMENT_CHARS


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOLARFLOW_DATA_DIR", str(tmp_path))
    for name in (
        "_document_store",
        "_document_store_path",
        "_library_instance",
        "_library_instance_path",
        "_personal_dictionary",
        "_personal_dictionary_path",
        "_diagnostics_engine",
        "_diagnostics_engine_key",
    ):
        monkeypatch.setattr(api, name, None, raising=False)
    return TestClient(api.app)


DRAFT = (
    "# Caste and commons\n\n"
    "It is important to note that caste plays a crucial role in shaping access to land. "
    "There is many studies about this tehnique. The data is unclear. "
    "because the sample size was small.\n"
)


def test_categories_endpoint_lists_every_category(client):
    response = client.get("/api/workspace/diagnostics/categories")
    assert response.status_code == 200
    payload = response.json()
    ids = [item["id"] for item in payload["categories"]]
    assert ids == [
        "spelling",
        "agreement",
        "punctuation",
        "capitalization",
        "fragment",
        "run_on",
        "wordiness",
        "repetition",
        "readability",
        "tone",
    ]
    kinds = {item["id"]: item["kind"] for item in payload["categories"]}
    assert kinds["spelling"] == "error"
    assert kinds["wordiness"] == "style"
    assert payload["limits"]["max_characters"] == MAX_DOCUMENT_CHARS
    assert "local" in payload["privacy"].lower()


def test_diagnostics_returns_positioned_findings(client):
    response = client.post(
        "/api/workspace/diagnostics",
        json={"text": DRAFT, "document_id": "doc-1", "revision": 3},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"] == "doc-1"
    assert payload["revision"] == 3
    assert payload["counts"]["total"] == len(payload["diagnostics"])
    assert payload["counts"]["error"] >= 1
    assert payload["counts"]["style"] >= 1
    assert payload["engine"]["external_services"] == "none"
    assert len(payload["text_sha256"]) == 64
    for item in payload["diagnostics"]:
        assert DRAFT[item["start"]:item["end"]] == item["original"]
    categories = {item["category"] for item in payload["diagnostics"]}
    assert {"spelling", "agreement", "fragment", "wordiness"} <= categories


def test_diagnostics_never_returns_error_text_contents(client):
    marker = "confidential-passage-marker"
    oversized = ("word " * (MAX_DOCUMENT_CHARS // 5 + 2)) + marker
    response = client.post("/api/workspace/diagnostics", json={"text": oversized})
    assert response.status_code == 422
    assert marker not in response.text
    assert "character analysis limit" in response.json()["detail"]


def test_diagnostics_category_filter(client):
    response = client.post(
        "/api/workspace/diagnostics",
        json={"text": DRAFT, "categories": ["spelling"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert {item["category"] for item in payload["diagnostics"]} == {"spelling"}


def test_diagnostics_rejects_an_unknown_category(client):
    response = client.post(
        "/api/workspace/diagnostics",
        json={"text": "A sentence.", "categories": ["grammar"]},
    )
    assert response.status_code == 422
    assert "Unknown diagnostic categories" in response.json()["detail"]


def test_diagnostics_accepts_an_empty_document(client):
    response = client.post("/api/workspace/diagnostics", json={"text": ""})
    assert response.status_code == 200
    payload = response.json()
    assert payload["diagnostics"] == []
    assert payload["counts"]["total"] == 0
    assert payload["notes"]


def test_diagnostics_handles_unicode_and_multiline_text(client):
    text = "कास्ते shapes tenure —\n\nSecond paragraph with teh typo and naïve spelling."
    response = client.post("/api/workspace/diagnostics", json={"text": text})
    assert response.status_code == 200
    payload = response.json()
    for item in payload["diagnostics"]:
        assert text[item["start"]:item["end"]] == item["original"]
    assert any(item["original"] == "teh" for item in payload["diagnostics"])


def test_personal_dictionary_round_trip_changes_results(client):
    text = "The zamindariyy settlement shaped tenure."
    before = client.post("/api/workspace/diagnostics", json={"text": text}).json()
    assert any(item["original"] == "zamindariyy" for item in before["diagnostics"])

    response = client.post("/api/workspace/dictionary", json={"word": "zamindariyy"})
    assert response.status_code == 200
    assert response.json()["words"] == ["zamindariyy"]
    assert client.get("/api/workspace/dictionary").json()["words"] == ["zamindariyy"]

    after = client.post("/api/workspace/diagnostics", json={"text": text}).json()
    assert not any(item["original"] == "zamindariyy" for item in after["diagnostics"])

    assert client.delete("/api/workspace/dictionary/zamindariyy").json()["words"] == []
    again = client.post("/api/workspace/diagnostics", json={"text": text}).json()
    assert any(item["original"] == "zamindariyy" for item in again["diagnostics"])


def test_personal_dictionary_rejects_unsafe_words(client):
    for word in ("two words", "semi;colon", "x" * 65, "1234"):
        assert client.post("/api/workspace/dictionary", json={"word": word}).status_code == 422


def test_personal_dictionary_is_stored_in_the_data_directory(client, tmp_path):
    client.post("/api/workspace/dictionary", json={"word": "Jajmani"})
    path = tmp_path / "writing-dictionary.json"
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8"))["words"] == ["Jajmani"]


def test_diagnostics_do_not_touch_the_document_store(client):
    created = client.post(
        "/api/documents", json={"title": "Kept", "text": "The kept text."}
    ).json()
    client.post(
        "/api/workspace/diagnostics",
        json={"text": "Different text with teh typo.", "document_id": created["id"]},
    )
    stored = client.get(f"/api/documents/{created['id']}").json()
    assert stored["text"] == "The kept text."
    assert stored["revision"] == 1


def test_existing_library_endpoints_still_work(client):
    assert client.get("/api/library/health").status_code == 200
    assert client.get("/workspace").status_code == 200
    assert client.get("/assets/workspace.js").status_code == 200
