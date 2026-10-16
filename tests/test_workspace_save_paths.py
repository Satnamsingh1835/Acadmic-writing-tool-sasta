"""Save-path and offset-contract regression tests.

Three defects were reproduced while verifying the Windows data-integrity
checkpoint. Two of them live in the browser and are pinned by
``tests/gui/workspace_dom_check.mjs``; the parts that are the server's
responsibility are pinned here:

* a save whose text the server cannot represent (a lone surrogate, which an
  ill-formed paste can produce) answered with HTTP 500, because the handler for a
  rejected request echoed the offending input back and that input cannot be
  encoded. It must be a 4xx the caller can act on, carrying no document text, and
  the stored document must be untouched;
* the diagnostics engine reports offsets as *characters* (Unicode code points),
  which is the contract the editor has to convert from before it touches the
  textarea. This is asserted rather than assumed, because the whole correction
  path depends on it and a document containing an emoji is enough to expose a
  mismatch;
* a write for one document must never change another, whatever order the requests
  arrive in, and a restore must be scoped to its own document.

The DOM-level equivalents (marker positions, the accept refusal, the recovery
banner, the identity guards) run in the GUI harness.
"""

from __future__ import annotations

import json
import unicodedata

import pytest
from fastapi.testclient import TestClient

import api
from document_store import DocumentStore


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("SCHOLARFLOW_DATA_DIR", str(tmp_path / "data"))
    store = DocumentStore(tmp_path / "data")
    monkeypatch.setattr(api, "get_document_store", lambda: store)
    return TestClient(api.app, raise_server_exceptions=False)


def create(client: TestClient, title: str, text: str = "") -> dict:
    response = client.post("/api/documents", json={"title": title, "text": text})
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------
# text the server cannot represent
# --------------------------------------------------------------------------


def test_a_save_holding_a_lone_surrogate_is_refused_not_crashed(client) -> None:
    """Ill-formed text must be answered, never turn into a server error.

    A lone surrogate is the low half of an emoji, which an ill-formed paste or a
    programmatic edit can leave behind. Python cannot encode it, so echoing it
    back in an error response used to raise inside the error handler and the
    caller saw "the server returned 500".
    """
    document = create(client, "Lone surrogate", "original text\n")
    lone_surrogate = "text with half an emoji \ud83d in it\n"

    # A browser's JSON.stringify escapes a lone surrogate, so the request body is
    # the JSON text with the escape in it.
    response = client.put(
        f"/api/documents/{document['id']}",
        content=json.dumps(
            {"text": lone_surrogate, "reason": "manual", "expected_revision": 1}
        ),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code < 500, response.text
    assert response.status_code in (400, 422), response.status_code
    # The answer must be readable JSON and must not carry the document text back.
    detail = response.json()["detail"]
    assert "half an emoji" not in detail
    assert "\ud83d" not in detail


def test_a_refused_save_leaves_the_document_exactly_as_it_was(client) -> None:
    """A rejected write is a no-op: same text, same revision, no history entry."""
    document = create(client, "Unchanged", "original text\n")
    before = client.get(f"/api/documents/{document['id']}").json()

    client.put(
        f"/api/documents/{document['id']}",
        content=json.dumps(
            {
                "text": "broken \ud83d half\n",
                "reason": "manual",
                "expected_revision": before["revision"],
            }
        ),
        headers={"Content-Type": "application/json"},
    )
    after = client.get(f"/api/documents/{document['id']}").json()

    assert after["text"] == before["text"]
    assert after["revision"] == before["revision"]

    revisions = client.get(f"/api/documents/{document['id']}/revisions").json()["revisions"]
    assert all("half" not in entry.get("text", "") for entry in revisions)


def test_a_rejected_request_never_echoes_document_text(client) -> None:
    """An error response must not leak what the researcher wrote.

    The same reason is already recorded on the diagnostics request: a pydantic
    error echoes its input, so limits are enforced where the text cannot end up
    in a response.
    """
    secret = "unpublished fieldwork notes about the Chamarajanagar sample"
    document = create(client, "Echo", "text\n")

    response = client.put(
        f"/api/documents/{document['id']}",
        json={"text": "x" * 10, "reason": secret * 10, "expected_revision": 1},
    )

    assert response.status_code == 422, response.text
    assert "unpublished" not in response.text


# --------------------------------------------------------------------------
# the offset contract the editor depends on
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected_slice",
    [
        ("The tehnique used here is the analysys of caste.", "analysys"),
        ("The tehnique \U0001f642 used here is the analysys of caste.", "analysys"),
        ("\U0001f642\U0001f642 The tehnique used here is fine, and the analysys too.", "analysys"),
        ("ਪੰਜਾਬੀ The tehnique used here is fine.", "tehnique"),
        ("🙂🙂 🙂 The tehnique is fine.", "tehnique"),
    ],
)
def test_report_offsets_are_character_indices(text: str, expected_slice: str) -> None:
    """Offsets index the text by character, not by UTF-16 code unit.

    The editor's ``slice`` counts UTF-16 code units, so the page has to convert
    these before using them; a mismatch is invisible in a document of ordinary
    Latin text and appears the moment an emoji precedes a finding. Asserting the
    engine's side of that contract keeps the conversion honest.
    """
    from diagnostics import DiagnosticEngine

    report = DiagnosticEngine().analyse(text, profile="academic_standard")
    findings = [item for item in report["diagnostics"] if item["original"]]
    assert findings, "expected at least one finding to check"

    for finding in findings:
        assert text[finding["start"] : finding["end"]] == finding["original"], finding["id"]

    target = [
        item for item in findings if expected_slice in item["original"] or item["original"] in expected_slice
    ]
    assert target, [item["original"] for item in findings]
    for finding in target:
        assert text[finding["start"] : finding["end"]] == finding["original"]
        # The offset must be reached by counting characters. With an emoji in
        # front of it, the UTF-16 index is larger — which is exactly what the
        # browser needed and did not do.
        assert len(text) >= finding["end"]


# --------------------------------------------------------------------------
# one document's write never reaches another document
# --------------------------------------------------------------------------


def test_interleaved_writes_keep_each_document_its_own(client) -> None:
    """Two documents written in turn, then read back: neither holds the other's text."""
    first = create(client, "First", "First document text.\n")
    second = create(client, "Second", "Second document text.\n")

    edits = {
        first["id"]: [
            "First document text.\nEdited once.\n",
            "First document text.\nEdited once.\nEdited twice.\n",
        ],
        second["id"]: [
            "Second document text.\nAlso edited.\n",
            "Second document text.\nAlso edited.\nAnd again.\n",
        ],
    }

    # Interleave the writes the way two open documents do.
    for round_index in range(2):
        for document_id, texts in edits.items():
            response = client.put(
                f"/api/documents/{document_id}",
                json={"text": texts[round_index], "reason": "autosave"},
            )
            assert response.status_code == 200, response.text

    for document_id, texts in edits.items():
        stored = client.get(f"/api/documents/{document_id}").json()
        assert stored["text"] == texts[-1]
        assert len(stored["text"]) == len(texts[-1])

    assert client.get(f"/api/documents/{first['id']}").json()["text"] != client.get(
        f"/api/documents/{second['id']}"
    ).json()["text"]


def test_restoring_a_revision_does_not_touch_another_document(client) -> None:
    """A restore is scoped to its own document, byte for byte."""
    first = create(client, "Restore one", "First version.\n")
    second = create(client, "Restore two", "Second document, untouched.\n")
    client.put(f"/api/documents/{first['id']}", json={"text": "Second version.\n", "reason": "manual"})
    before_second = client.get(f"/api/documents/{second['id']}").json()

    response = client.post(f"/api/documents/{first['id']}/revisions/1/restore")
    assert response.status_code == 200, response.text
    assert response.json()["text"] == "First version.\n"

    after_second = client.get(f"/api/documents/{second['id']}").json()
    assert after_second["text"] == before_second["text"]
    assert after_second["revision"] == before_second["revision"]
    # And the restored text is kept in history, so the restore is reversible.
    revisions = client.get(f"/api/documents/{first['id']}/revisions").json()["revisions"]
    assert any(entry.get("reason") == "before-restore" for entry in revisions)


def test_restoring_a_revision_that_does_not_exist_is_refused(client) -> None:
    """An impossible restore is answered, and nothing is written."""
    document = create(client, "Bad restore", "Only version.\n")

    response = client.post(f"/api/documents/{document['id']}/revisions/999/restore")

    assert response.status_code >= 400
    assert client.get(f"/api/documents/{document['id']}").json()["text"] == "Only version.\n"


def test_a_save_for_a_document_that_does_not_exist_is_refused(client) -> None:
    """A write with nowhere to go is refused, and creates nothing."""
    response = client.put("/api/documents/does-not-exist", json={"text": "text\n", "reason": "manual"})

    assert response.status_code == 404, response.text
    listing = client.get("/api/documents").json()["documents"]
    assert all(entry["id"] != "does-not-exist" for entry in listing)


def test_a_whole_document_round_trip_is_byte_exact(tmp_path) -> None:
    """Storing a document and reading it back returns the same characters.

    The document store states its canonical form itself: NFC, and CRLF folded to
    LF once. Everything else, including trailing spaces, blank lines, tabs and a
    missing final newline, must survive exactly.
    """
    store = DocumentStore(tmp_path / "data")
    cases = [
        "plain ASCII, with commas; and 100% of the numbers 0123456789.\n",
        "Café — naïve, coöperate; “curly” and ‘single’ quotes.\n",
        "ਪੰਜਾਬੀ ਵਿੱਚ ਲਿਖਿਆ ਇੱਕ ਪੈਰਾ।\nਦੂਜਾ ਪੈਰਾ।\n",
        "emoji 🙂, a flag 🇮🇳 and a family 👩‍👩‍👧 in one line.\n",
        "tabs\tand trailing spaces  \n\nblank lines above\n",
        "First line.\r\nSecond line.\r\n",
        "no final newline",
        "an em dash — and an ellipsis …\n",
        "",
    ]
    for index, original in enumerate(cases):
        document = store.create(title=f"case {index}", text=original)
        folded = original.replace("\r\n", "\n").replace("\r", "\n")
        expected = unicodedata.normalize("NFC", folded)
        assert store.get(document["id"])["text"] == expected, original
        # Saving the same text again changes nothing.
        saved = store.save(document["id"], text=expected, reason="manual")
        assert saved["text"] == expected
        assert store.get(document["id"])["text"] == expected
        assert json.loads(json.dumps(store.get(document["id"])["text"])) == expected
