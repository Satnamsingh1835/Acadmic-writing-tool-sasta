from revision_receipt import build_revision_receipt, text_digest


def receipt(**overrides):
    values = {
        "original_text": "Original private passage.",
        "refined_text": "Refined private passage.",
        "profile": "standard",
        "provider": "deterministic-local",
        "llm_requested": False,
        "llm_used": False,
        "safeguards": {
            "citations_preserved": True,
            "sentence_count_preserved": True,
        },
        "grammar_and_style": {
            "citation_diagnostics": {"possible_uncited_source_claims": []}
        },
        "literature_review": {"paragraphs": []},
        "notices": [],
    }
    values.update(overrides)
    return build_revision_receipt(**values)


def test_text_digest_is_stable_and_prefixed():
    assert text_digest("same") == text_digest("same")
    assert text_digest("same").startswith("sha256:")
    assert text_digest("same") != text_digest("different")


def test_receipt_is_deterministic_and_does_not_contain_manuscript_text():
    first = receipt()
    second = receipt()

    assert first == second
    serialized = str(first)
    assert "Original private passage" not in serialized
    assert "Refined private passage" not in serialized
    assert first["receipt_id"].startswith("revision:")
    assert first["input_digest"].startswith("sha256:")


def test_receipt_identity_changes_when_revision_changes():
    first = receipt()
    second = receipt(refined_text="A different revision.")

    assert first["receipt_id"] != second["receipt_id"]
    assert first["output_digest"] != second["output_digest"]


def test_receipt_records_fallback_and_failed_safeguard():
    result = receipt(
        llm_requested=True,
        safeguards={"citations_preserved": False},
        notices=["Provider failed; local revision returned."],
    )

    model_operation = next(
        operation
        for operation in result["operations"]
        if operation["name"] == "model-enhancement"
    )
    assert model_operation["status"] == "fallback"
    assert any(
        unknown["unknown_id"] == "safeguard:citations_preserved"
        for unknown in result["residual_unknowns"]
    )


def test_receipt_surfaces_diagnostic_unknowns_without_inventing_content():
    result = receipt(
        grammar_and_style={
            "citation_diagnostics": {"possible_uncited_source_claims": [2]}
        },
        literature_review={
            "paragraphs": [
                {
                    "paragraph": 1,
                    "missing": ["comparison_or_synthesis", "gap"],
                }
            ]
        },
    )

    identifiers = {
        unknown["unknown_id"] for unknown in result["residual_unknowns"]
    }
    assert "diagnostic:possible-uncited-claims" in identifiers
    assert "diagnostic:literature-flow" in identifiers
