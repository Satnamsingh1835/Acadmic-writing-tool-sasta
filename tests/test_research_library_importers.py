from research_library.importers import import_csl_records
from research_library.store import ResearchLibrary


def test_csl_import_is_idempotent_and_normalizes_metadata(tmp_path):
    library = ResearchLibrary(tmp_path / "library.sqlite3")
    item = {
        "id": "synthetic-ref",
        "type": "article-journal",
        "title": "Synthetic land and caste study",
        "author": [{"given": "Asha", "family": "Example"}],
        "issued": {"date-parts": [[2024]]},
        "DOI": "10.5555/synthetic.record",
        "container-title": "Synthetic Social Science",
    }
    first = import_csl_records(library, [item])
    second = import_csl_records(library, [item])
    assert first == {"imported": 1, "duplicates": 0, "skipped": 0}
    assert second == {"imported": 0, "duplicates": 1, "skipped": 0}
    stored = library.search_works(q="synthetic land")
    assert stored[0]["authors"] == ["Asha Example"]
    assert stored[0]["year"] == 2024


def test_invalid_record_is_skipped(tmp_path):
    library = ResearchLibrary(tmp_path / "library.sqlite3")
    result = import_csl_records(library, [{"title": ""}, "invalid"])
    assert result == {"imported": 0, "duplicates": 0, "skipped": 2}
