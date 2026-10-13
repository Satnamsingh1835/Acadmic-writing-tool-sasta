from research_library.documents import DocumentIndexError, index_document
from research_library.store import ResearchLibrary


def test_text_document_is_stored_and_passage_is_searchable(tmp_path):
    library = ResearchLibrary(tmp_path / "library.sqlite3")
    work = library.add_work({"title": "Synthetic research source", "authors": ["Example Author"]})
    result = index_document(
        library,
        "synthetic.txt",
        b"Social boycott can restrict access to labour and village common land.\n\n"
        b"This is a synthetic test passage.",
        work_id=work["id"],
        licence="synthetic test fixture",
    )
    assert result["passages_indexed"] == 2
    matches = library.search_passages("village common land")
    assert matches
    assert matches[0]["work_id"] == work["id"]
    assert matches[0]["page_number"] is None


def test_upload_rejects_unsupported_types_and_invalid_utf8(tmp_path):
    library = ResearchLibrary(tmp_path / "library.sqlite3")
    try:
        index_document(library, "bad.exe", b"not a document")
    except DocumentIndexError as error:
        assert "Supported formats" in str(error)
    else:
        raise AssertionError("unsupported document type was accepted")
    try:
        index_document(library, "bad.txt", b"\xff")
    except DocumentIndexError as error:
        assert "UTF-8" in str(error)
    else:
        raise AssertionError("invalid UTF-8 should fail")
