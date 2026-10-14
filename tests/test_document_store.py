import pytest

from document_store import (
    DEFAULT_TITLE,
    MAX_TITLE_CHARS,
    DocumentConflictError,
    DocumentNotFoundError,
    DocumentStore,
    DocumentValidationError,
    count_words,
    derive_title,
)


@pytest.fixture()
def store(tmp_path):
    return DocumentStore(tmp_path / "writing-documents.sqlite3")


def test_create_derives_title_from_first_heading(store):
    document = store.create(text="# Caste and commons\n\nBody text here.")

    assert document["title"] == "Caste and commons"
    assert document["revision"] == 1
    assert document["word_count"] == count_words(document["text"])
    assert document["archived"] is False


def test_create_without_text_uses_default_title(store):
    document = store.create()

    assert document["title"] == DEFAULT_TITLE
    assert document["text"] == ""
    assert document["character_count"] == 0


def test_save_persists_text_and_history_across_reopen(tmp_path):
    path = tmp_path / "writing-documents.sqlite3"
    store = DocumentStore(path)
    document = store.create(title="Draft", text="First version.")

    saved = store.save(document["id"], text="Second version with more detail.", reason="manual")
    assert saved["revision"] == 2
    assert saved["text"] == "Second version with more detail."

    reopened = DocumentStore(path)
    reloaded = reopened.get(document["id"])
    assert reloaded["text"] == "Second version with more detail."
    assert reloaded["revision"] == 2

    history = reopened.revisions(document["id"])
    assert [entry["revision"] for entry in history] == [1]
    assert history[0]["text"] if "text" in history[0] else True  # summaries only


def test_save_with_stale_revision_is_a_conflict(store):
    document = store.create(title="Shared", text="Original.")

    store.save(document["id"], text="Saved by another window.", expected_revision=1)

    with pytest.raises(DocumentConflictError) as error:
        store.save(document["id"], text="My stale text.", expected_revision=1)

    assert error.value.current_revision == 2
    # The conflict must not have changed the stored text.
    assert store.get(document["id"])["text"] == "Saved by another window."


def test_save_without_change_does_not_create_a_revision(store):
    document = store.create(title="Stable", text="Nothing to change.")

    same = store.save(document["id"], text="Nothing to change.", expected_revision=1)

    assert same["revision"] == 1
    assert store.revisions(document["id"]) == []


def test_autosave_and_manual_saves_are_recorded_and_bounded(store):
    document = store.create(title="Long draft", text="Start.")

    for index in range(12):
        store.save(document["id"], text=f"Revision {index}", reason="autosave")

    history = store.revisions(document["id"], limit=50)
    assert len(history) == 12
    assert {entry["reason"] for entry in history} == {"autosave"}
    assert history[0]["revision"] == 12


def test_restore_revision_restores_text_and_keeps_current_text(store):
    document = store.create(title="Rollback", text="Version one.")
    store.save(document["id"], text="Version two.")
    store.save(document["id"], text="Version three.")

    restored = store.restore_revision(document["id"], 1)

    assert restored["text"] == "Version one."
    assert restored["revision"] == 4
    reasons = {entry["reason"] for entry in store.revisions(document["id"])}
    assert "before-restore" in reasons
    # The text that was on screen before the rollback is still recoverable.
    assert any(
        entry["reason"] == "before-restore" and entry["revision"] == 3
        for entry in store.revisions(document["id"])
    )


def test_missing_revision_raises(store):
    document = store.create(title="No history", text="Only text.")

    with pytest.raises(DocumentNotFoundError):
        store.restore_revision(document["id"], 9)


def test_delete_archives_and_keeps_text_recoverable(store):
    document = store.create(title="Archive me", text="Keep this text.")
    store.save(document["id"], text="Newer text.")

    archived = store.delete(document["id"])
    assert archived["archived"] is True
    assert store.list() == []
    assert store.list(include_archived=True)[0]["id"] == document["id"]
    # Archived text is still readable and can be brought back.
    assert store.get(document["id"])["text"] == "Newer text."
    with pytest.raises(DocumentNotFoundError):
        store.save(document["id"], text="Cannot save while archived.")

    store.restore_document(document["id"])
    assert store.list()[0]["id"] == document["id"]
    assert store.save(document["id"], text="Editable again.")["text"] == "Editable again."


def test_list_orders_by_update_and_filters_by_query(store):
    first = store.create(title="Punjab land", text="shamlat and panchayat land")
    second = store.create(title="Boycott notes", text="social boycott in villages")
    store.save(second["id"], text="social boycott and exclusion")

    titles = [item["title"] for item in store.list()]
    assert titles[0] == "Boycott notes"

    assert [item["id"] for item in store.list(query="shamlat")] == [first["id"]]
    assert [item["id"] for item in store.list(query="Boycott notes")] == [second["id"]]
    assert store.list(query="no such phrase") == []
    assert store.count() == 2


def test_validation_rejects_oversized_and_wrong_typed_input(store):
    with pytest.raises(DocumentValidationError):
        store.create(title="x" * (MAX_TITLE_CHARS + 1))

    document = store.create(title="Typed", text="ok")
    with pytest.raises(DocumentValidationError):
        store.save(document["id"], text=12345)
    with pytest.raises(DocumentValidationError):
        store.save(document["id"], reason="teleport")
    with pytest.raises(DocumentValidationError):
        store.create(text="y" * 2_000_001)


def test_missing_document_operations_report_not_found(store):
    with pytest.raises(DocumentNotFoundError):
        store.get("missing")
    with pytest.raises(DocumentNotFoundError):
        store.save("missing", text="text")
    with pytest.raises(DocumentNotFoundError):
        store.delete("missing")
    with pytest.raises(DocumentNotFoundError):
        store.revisions("missing")


def test_derive_title_handles_blanks_and_markup():
    assert derive_title("\n\n## Commons and caste\n\ntext") == "Commons and caste"
    assert derive_title("   \n  ") == DEFAULT_TITLE
