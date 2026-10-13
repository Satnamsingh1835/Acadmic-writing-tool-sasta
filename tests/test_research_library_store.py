import json

from research_library.store import ResearchLibrary


def test_library_add_deduplicate_search_and_backup(tmp_path):
    library = ResearchLibrary(tmp_path / "library.sqlite3")
    first = library.add_work({
        "title": "Land and Caste Relations",
        "authors": ["A. Researcher"],
        "year": 2024,
        "doi": "https://doi.org/10.1234/EXAMPLE",
        "abstract": "Dalit claims over village common land",
        "subjects": ["Punjab", "commons"],
    })
    second = library.add_work({
        "title": "A differently formatted title",
        "doi": "10.1234/example",
        "authors": ["Different Author"],
    })
    assert first["created"] is True
    assert second["created"] is False
    assert second["id"] == first["id"]
    assert library.count_works() == 1
    assert library.get_work(first["id"])["doi"] == "10.1234/example"
    assert library.search_works(q="village common land")[0]["id"] == first["id"]
    assert library.search_works(subject="Punjab")[0]["id"] == first["id"]
    backup = library.create_backup(tmp_path / "backup.sqlite3")
    assert backup.exists()
    copied = ResearchLibrary(backup)
    assert copied.count_works() == 1


def test_matrix_and_settings_are_persistent(tmp_path):
    library = ResearchLibrary(tmp_path / "library.sqlite3")
    work = library.add_work({"title": "Synthetic title", "authors": ["Test Author"]})
    entry = library.add_matrix_entry({
        "work_id": work["id"],
        "research_question": "How is access governed?",
        "claim": "A candidate interpretation",
        "supporting_passage": "Synthetic passage",
        "page_number": 3,
        "evidence_level": "candidate",
    })
    assert entry["page_number"] == 3
    library.update_settings({"offline": True, "crossref_enabled": False})
    assert library.get_settings()["offline"] is True
    assert library.get_settings()["crossref_enabled"] is False
    assert len(library.list_matrix_entries()) == 1
