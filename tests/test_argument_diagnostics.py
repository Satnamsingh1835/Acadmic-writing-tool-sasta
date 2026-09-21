from argument_diagnostics import ArgumentDiagnostics


def test_relationship_and_connection_signals():
    report = ArgumentDiagnostics().analyse(
        "Jodhka (2004) examines land relations. However, later work qualifies this argument. "
        "This study examines the unresolved regional variation."
    )

    assert report["relationships"]["contrast"] is True
    assert report["has_research_connection"] is True
    assert report["researcher_questions"] == []


def test_missing_synthesis_generates_researcher_question():
    report = ArgumentDiagnostics().analyse(
        "Jodhka (2004) examines land relations. Gupta (2000) examines caste."
    )

    assert report["has_explicit_relationship"] is False
    assert any("relationship between the studies" in q for q in report["researcher_questions"])


def test_empty_paragraph_rejected():
    try:
        ArgumentDiagnostics().analyse(" ")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError")
