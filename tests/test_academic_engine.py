from academic_engine import AcademicWritingEngine


def test_engine_reviews_literature_text():
    engine = AcademicWritingEngine()
    result = engine.review(
        "Several studies examine caste and land relations in India (Jodhka, 2004)."
    )

    assert result.refined_text
    assert isinstance(result.suggestions, list)
    assert isinstance(result.grammar_and_style, dict)
    assert isinstance(result.literature_review, dict)
    assert isinstance(result.safeguards, dict)


def test_engine_supports_profile_aliases():
    engine = AcademicWritingEngine()

    assert engine.normalize_profile("light") == "conservative"
    assert engine.normalize_profile("medium") == "standard"
    assert engine.normalize_profile("heavy") == "polish"


def test_engine_rejects_unknown_profile():
    engine = AcademicWritingEngine()

    try:
        engine.normalize_profile("unknown")
    except ValueError as exc:
        assert "Unknown profile" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_engine_can_omit_refined_text():
    result = AcademicWritingEngine().review(
        "Caste shapes access to land.",
        include_refined_text=False,
    )

    assert result.refined_text is None


def test_engine_does_not_drop_diagnostics_for_unmatched_paragraphs():
    class EmptyLiteratureReviewAnalyzer:
        def analyse(self, text, analysis=None):
            return {"paragraph_count": 0, "paragraphs": []}

    result = AcademicWritingEngine(
        literature_review_analyser=EmptyLiteratureReviewAnalyzer()
    ).review("First paragraph.\n\nSecond paragraph.")

    paragraphs = result.literature_review["paragraphs"]
    assert result.literature_review["paragraph_count"] == 2
    assert [item["paragraph"] for item in paragraphs] == [1, 2]
    assert all("argument_diagnostics" in item for item in paragraphs)
