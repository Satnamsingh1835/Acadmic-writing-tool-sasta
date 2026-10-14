"""Unit tests for the deterministic diagnostics engine.

Every test states the text it checks and the exact offsets it expects, so a
failure shows which rule changed. Offsets are always asserted against
``text[start:end] == original`` — the contract the editor relies on.
"""

from __future__ import annotations

import time

import pytest

from diagnostics import (
    CATEGORY_INFO,
    CATEGORY_ORDER,
    MAX_DOCUMENT_CHARS,
    DiagnosticEngine,
    PersonalDictionary,
    _Mask,
    _british_equivalents,
    _dictionary_knows,
    _spell_checker,
    spelling_engine_available,
)


@pytest.fixture(scope="module")
def engine() -> DiagnosticEngine:
    return DiagnosticEngine()


def findings(report: dict, category: str | None = None, *, kind: str | None = None) -> list[dict]:
    items = report["diagnostics"]
    if category:
        items = [item for item in items if item["category"] == category]
    if kind:
        items = [item for item in items if item["kind"] == kind]
    return items


def check_offsets(text: str, report: dict) -> None:
    for item in report["diagnostics"]:
        assert text[item["start"]:item["end"]] == item["original"], item
        assert item["start"] < item["end"]
        assert item["id"].startswith(item["rule"] + "@")
        assert item["kind"] in {"error", "style"}
        assert item["severity"] == item["kind"]
        assert item["confidence"] in {"high", "medium", "low"}
        assert item["message"] and item["explanation"]
        if item["replacement"] is not None:
            assert item["replacement"] in item["replacements"]


def apply_first(text: str, item: dict) -> str:
    """Apply one finding the way the editor does: replace exactly the range."""
    return text[: item["start"]] + item["replacements"][0] + text[item["end"]:]


# ------------------------------------------------------------------ schema


def test_report_schema_and_counts(engine):
    text = "It is important to note that this is teh result. There is two problems."
    report = engine.analyse(text, document_id="doc-1", revision=4)
    assert report["document_id"] == "doc-1"
    assert report["revision"] == 4
    assert report["characters"] == len(text)
    assert len(report["text_sha256"]) == 64
    assert report["counts"]["total"] == len(report["diagnostics"])
    assert report["counts"]["error"] + report["counts"]["style"] == report["counts"]["total"]
    assert set(report["counts"]["by_category"]) == set(CATEGORY_ORDER)
    assert report["engine"]["external_services"] == "none"
    assert [item["id"] for item in report["categories"]] == list(CATEGORY_ORDER)
    check_offsets(text, report)


def test_categories_have_a_kind_and_only_language_error_families_are_errors():
    error_categories = {
        "spelling",
        "agreement",
        "punctuation",
        "capitalization",
        "fragment",
        "run_on",
    }
    for name, info in CATEGORY_INFO.items():
        assert info["kind"] in {"error", "style"}
        assert info["label"] and info["hint"]
        if name in error_categories:
            assert info["kind"] == "error"
        else:
            assert info["kind"] == "style", name


def test_analysis_is_deterministic(engine):
    text = "The data is unclear, and it is important to note that this is teh study."
    first = engine.analyse(text)
    second = engine.analyse(text)
    assert first["diagnostics"] == second["diagnostics"]
    assert first["counts"] == second["counts"]


def test_empty_and_whitespace_only_documents(engine):
    for text in ("", "   ", "\n\n  \n"):
        report = engine.analyse(text)
        assert report["diagnostics"] == []
        assert report["counts"]["total"] == 0
        assert any("empty" in note.lower() for note in report["notes"])


def test_clean_document_reports_a_clear_empty_state(engine):
    text = (
        "Caste shapes access to land in rural India (Gupta, 2000). "
        "This pattern persists where tenancy law is weakly enforced."
    )
    report = engine.analyse(text)
    assert report["diagnostics"] == []
    assert any("No findings" in note for note in report["notes"])


# --------------------------------------------------------------- categories


def test_spelling_category_reports_offsets_and_candidates(engine):
    text = "The methodology section describes the teh sample."
    report = engine.analyse(text)
    items = findings(report, "spelling")
    assert len(items) == 1
    item = items[0]
    assert item["original"] == "teh"
    assert text[item["start"]:item["end"]] == "teh"
    assert item["kind"] == "error"
    assert "the" in item["replacements"]
    # Stage 3 split the spelling family in two: a word one edit away from a
    # dictionary word is a *misspelling* (with a replacement), while a word with
    # no candidate is merely *unknown* (no replacement). "teh" has the candidate
    # "the", so it is the former. The offsets and the contract are unchanged.
    assert item["rule"] == "spelling.misspelling"
    assert item["confidence"] == "high"
    check_offsets(text, report)


def test_spelling_accepts_british_spellings_and_academic_terms(engine):
    text = (
        "The behaviour of the labour market is analysed through the organisation of "
        "caste and agrarian relations, using a methodology that emphasises hegemony."
    )
    report = engine.analyse(text)
    assert findings(report, "spelling") == []


def test_spelling_skips_names_citations_quotes_and_acronyms(engine):
    text = (
        "Zotero and ScholarFlow were used, as Ramachandran (2019) notes: "
        "\"the khethh sample was small\". The NGO reported FDI."
    )
    report = engine.analyse(text)
    assert findings(report, "spelling") == []


def test_spelling_accepts_a_personal_dictionary_word(engine):
    text = "The zamindariyy settlement shaped tenure."
    assert findings(engine.analyse(text), "spelling"), "expected the invented word to be flagged"
    forgiving = DiagnosticEngine(personal_dictionary=["zamindariyy"])
    assert findings(forgiving.analyse(text), "spelling") == []


def test_british_equivalents_cover_common_academic_forms():
    pairs = {
        "organise": "organize",
        "organised": "organized",
        "organisation": "organization",
        "behaviour": "behaviour",
        "labour": "labor",
        "centre": "center",
        "catalogue": "catalog",
        "modelled": "modeled",
        "defence": "defense",
        "programme": "program",
    }
    for british, _ in pairs.items():
        candidates = list(_british_equivalents(british))
        assert candidates, british


def test_agreement_category(engine):
    text = "There is two problems here. These is the results. Each of the studies are cited."
    report = engine.analyse(text)
    items = findings(report, "agreement")
    assert {item["original"] for item in items} >= {"is", "are"}
    assert all(item["kind"] == "error" for item in items if item["original"] != "data is")
    replacements = {item["original"]: item["replacements"] for item in items}
    assert "are" in replacements["is"]
    check_offsets(text, report)


def test_agreement_style_convention_is_never_an_error(engine):
    text = "The data is inconclusive because the criteria is unclear."
    report = engine.analyse(text)
    items = findings(report, "agreement")
    assert items, "the Latin-plural convention should still be mentioned"
    assert all(item["kind"] == "style" for item in items)
    assert all(item["replacement"] is None for item in items)


def test_agreement_ignores_singular_words_that_end_in_s(engine):
    text = "The analysis is clear and the status is stable."
    assert findings(engine.analyse(text), "agreement") == []


def test_punctuation_category(engine):
    text = "Land reform changed tenure ,moreover it reshaped credit markets.. It was uneven"
    report = engine.analyse(text)
    rules = {item["rule"] for item in findings(report, "punctuation")}
    assert "punctuation.space-before-mark" in rules
    assert "punctuation.missing-space" in rules
    assert "punctuation.doubled-mark" in rules
    check_offsets(text, report)


def test_punctuation_reports_unclosed_and_unmatched_brackets(engine):
    text = "The claim (as noted by Gupta is repeated here]. Another (clause is open."
    report = engine.analyse(text)
    rules = {item["rule"] for item in findings(report, "punctuation")}
    assert "punctuation.unmatched-bracket" in rules
    assert "punctuation.unclosed-bracket" in rules
    check_offsets(text, report)


def test_punctuation_leaves_abbreviations_and_decimals_alone(engine):
    text = "The sample (n = 42) was small, e.g. under 50. Figures show 3.5 percent growth."
    report = engine.analyse(text)
    assert findings(report, "punctuation") == []


def test_capitalization_category(engine):
    text = "the study is incomplete. english sources are missing. i disagree."
    report = engine.analyse(text)
    rules = {item["rule"] for item in findings(report, "capitalization")}
    assert "capitalization.sentence-start" in rules
    assert "capitalization.proper-adjective" in rules
    assert "capitalization.pronoun-i" in rules
    check_offsets(text, report)


def test_capitalization_accepts_lower_case_headings(engine):
    text = "## introduction\n\nThe section argues that caste shapes tenure."
    report = engine.analyse(text)
    assert findings(report, "capitalization") == []


def test_fragment_category(engine):
    text = "The sample was small. because the fieldwork ended early. Another full sentence follows."
    report = engine.analyse(text)
    items = findings(report, "fragment")
    assert len(items) == 1
    assert items[0]["original"] == "because the fieldwork ended early."
    assert items[0]["replacement"] is None
    check_offsets(text, report)


def test_run_on_category(engine):
    text = "Land reform changed tenure, moreover it reshaped credit markets."
    report = engine.analyse(text)
    items = findings(report, "run_on")
    assert len(items) == 1
    assert items[0]["original"] == ","
    assert ";" in items[0]["replacements"]
    check_offsets(text, report)


def test_run_on_ignores_coordinated_clauses(engine):
    text = "Land reform changed tenure, and it reshaped credit markets."
    assert findings(engine.analyse(text), "run_on") == []


def test_wordiness_category_uses_replacements(engine):
    text = "In order to measure tenure, the study used a number of indicators."
    report = engine.analyse(text)
    items = findings(report, "wordiness")
    assert {item["original"] for item in items} >= {"In order to", "a number of"}
    assert all(item["kind"] == "style" for item in items)
    assert all(item["replacement"] for item in items)
    check_offsets(text, report)


def test_wordiness_acceptance_keeps_the_rest_of_the_sentence(engine):
    text = "In order to measure tenure the study used a number of indicators."
    report = engine.analyse(text)
    item = next(item for item in findings(report, "wordiness") if item["original"].lower() == "in order to")
    updated = apply_first(text, item)
    assert updated == "To measure tenure the study used a number of indicators."


def test_formulaic_opener_removal_keeps_capitalisation(engine):
    text = "It is important to note that caste shapes tenure."
    report = engine.analyse(text)
    item = next(item for item in findings(report, "wordiness") if item["rule"] == "wordiness.formulaic-opener")
    updated = apply_first(text, item)
    assert updated == "Caste shapes tenure."


def test_repetition_category(engine):
    text = "The the outcome was studied. Outcomes, outcomes and outcomes were reported."
    report = engine.analyse(text)
    items = findings(report, "repetition")
    assert any(item["rule"] == "repetition.immediate" for item in items)
    assert all(item["kind"] == "style" for item in items)
    check_offsets(text, report)


def test_repetition_flags_an_overused_content_word(engine):
    text = (
        "Tenure shapes the tenure relationship that the tenure regime encodes, so tenure "
        "is contested."
    )
    report = engine.analyse(text)
    items = [item for item in findings(report, "repetition") if item["rule"] == "repetition.overused-word"]
    assert items
    assert all(item["kind"] == "style" for item in items)


def test_readability_reports_long_sentences_and_paragraphs(engine):
    long_sentence = " ".join(["tenure"] * 40) + "."
    report = engine.analyse(long_sentence)
    items = findings(report, "readability")
    assert items and items[0]["original"] == long_sentence
    assert items[0]["replacement"] is None

    paragraph = " ".join(["tenure"] * 230) + "."
    report = engine.analyse(paragraph)
    rules = {item["rule"] for item in findings(report, "readability")}
    assert "readability.long-paragraph" in rules


def test_readability_ignores_ordinary_sentences(engine):
    text = "Tenure reform changed rural credit, and land values rose."
    assert findings(engine.analyse(text), "readability") == []


def test_tone_category(engine):
    text = "It don't always hold that land reform obviously helped. A lot of studies disagree."
    report = engine.analyse(text)
    rules = {item["rule"] for item in findings(report, "tone")}
    assert "tone.contraction" in rules
    assert "tone.overclaim" in rules
    assert "tone.vague-quantifier" in rules
    assert all(item["kind"] == "style" for item in findings(report, "tone"))
    check_offsets(text, report)


def test_tone_never_offers_a_replacement_for_overclaims(engine):
    text = "The evidence always proves that tenure matters."
    report = engine.analyse(text)
    overclaims = [item for item in findings(report, "tone") if item["rule"] == "tone.overclaim"]
    assert overclaims
    assert all(item["replacement"] is None for item in overclaims)


def test_multiple_findings_in_one_sentence(engine):
    text = "It don't matter because the teh sample is unclear , and the data is weak."
    report = engine.analyse(text)
    assert len(report["diagnostics"]) >= 3
    categories = {item["category"] for item in report["diagnostics"]}
    assert {"tone", "spelling", "punctuation", "agreement"} <= categories
    check_offsets(text, report)


# ------------------------------------------------------------- offsets layer


def test_offsets_survive_unicode_text(engine):
    text = (
        "The analysis café naïve shows that कास्ते shapes tenure — and the em dash sits here. "
        "Curly “quoted text khethh here” stays untouched, and the ‘single quoted khethh’ too."
    )
    report = engine.analyse(text)
    check_offsets(text, report)
    for item in report["diagnostics"]:
        assert "कास्ते" not in item["original"]
        assert "khethh" not in item["original"]


def test_offsets_survive_devanagari_and_combining_marks(engine):
    text = "कास्ते and tenuré are field terms; the tenuré study продолжает."
    report = engine.analyse(text)
    check_offsets(text, report)


def test_markdown_structure_does_not_shift_offsets(engine):
    text = (
        "# Heading with teh typo\n\n"
        "- list item with teh typo\n"
        "- second item\n\n"
        "> quote with teh typo\n\n"
        "Regular paragraph with teh typo.\n\n"
        "| table | cell |\n| --- | --- |\n| teh | typo |\n"
    )
    report = engine.analyse(text)
    check_offsets(text, report)
    flagged = {item["original"] for item in findings(report, "spelling")}
    assert "teh" in flagged
    assert len(findings(report, "spelling")) >= 4


def test_code_blocks_and_inline_code_are_not_analysed(engine):
    text = (
        "Run `pytest --collect teh` on the project.\n\n"
        "```python\nprint('teh sample is not prose')\n```\n\n"
        "The prose after the fence is checked: teh sample."
    )
    report = engine.analyse(text)
    originals = [item["original"] for item in findings(report, "spelling")]
    assert originals == ["teh"]
    assert text[report["diagnostics"][0]["start"]:] .startswith("teh sample.")
    check_offsets(text, report)


def test_reference_list_is_not_spell_checked(engine):
    text = (
        "The paper cites earlier work.\n\n"
        "References\n\nGupta, A. (2000). Teh land question. Journal of Agrarian Studies.\n"
    )
    report = engine.analyse(text)
    assert findings(report, "spelling") == []
    check_offsets(text, report)


def test_front_matter_is_not_analysed(engine):
    text = "---\ntitle: teh draft\nauthor: x\n---\n\nBody text with teh typo."
    report = engine.analyse(text)
    assert [item["original"] for item in findings(report, "spelling")] == ["teh"]
    check_offsets(text, report)


def test_multiline_text_offsets_are_exact(engine):
    text = (
        "First line is clean.\n"
        "Second line has teh typo.\n"
        "Third line is clean.\n\n"
        "New paragraph: the sample is unclear. because it rained.\n"
    )
    report = engine.analyse(text)
    check_offsets(text, report)
    spelling = findings(report, "spelling")[0]
    assert spelling["original"] == "teh"
    line_start = text.index("Second line")
    assert spelling["start"] > line_start
    assert text.count("\n", 0, spelling["start"]) == 1


def test_crlf_text_keeps_offsets(engine):
    text = "First line.\r\nSecond line has teh typo.\r\n"
    report = engine.analyse(text)
    check_offsets(text, report)
    assert findings(report, "spelling")[0]["original"] == "teh"


def test_overlapping_diagnostics_are_all_returned(engine):
    # The space-before-comma finding spans the comma that the run-on rule also
    # reports, so the two findings overlap on purpose.
    text = "Land reform changed tenure , moreover it reshaped credit markets and teh values moved."
    report = engine.analyse(text)
    pairs = report["diagnostics"]
    overlaps = [
        (first, second)
        for first, second in zip(pairs, pairs[1:])
        if first["start"] < second["start"] < first["end"]
    ]
    assert overlaps, "expected at least one overlapping pair"
    check_offsets(text, report)
    ordered = sorted(pairs, key=lambda item: (item["start"], item["end"]))
    assert [(item["start"], item["end"]) for item in pairs] == [
        (item["start"], item["end"]) for item in ordered
    ]


def test_offsets_hold_across_a_chunk_boundary(engine):
    chunk = "Caste shapes tenure in this passage with no mistakes at all. " * 8
    text = chunk + "\n\n" + "Another paragraph with teh typo in it."
    report = engine.analyse(text)
    check_offsets(text, report)
    assert findings(report, "spelling")[0]["original"] == "teh"


def test_ids_are_stable_for_the_same_text_and_change_with_edits(engine):
    text = "There is two problems in teh draft."
    first = engine.analyse(text)["diagnostics"]
    second = engine.analyse(text)["diagnostics"]
    assert [item["id"] for item in first] == [item["id"] for item in second]
    edited = engine.analyse("There is two problems in the draft.")["diagnostics"]
    assert {item["id"] for item in edited} != {item["id"] for item in first}


# ------------------------------------------------------------ configuration


def test_category_filter_limits_the_result(engine):
    text = "There is two problems and teh typo"
    report = engine.analyse(text, categories=["spelling"])
    assert {item["category"] for item in report["diagnostics"]} == {"spelling"}
    assert report["counts"]["by_category"]["agreement"] == 0
    assert report["counts"]["error"] == report["counts"]["total"]


def test_unknown_category_is_rejected(engine):
    with pytest.raises(ValueError):
        engine.analyse("text", categories=["grammar"])


def test_text_longer_than_the_limit_is_rejected(engine):
    with pytest.raises(ValueError):
        engine.analyse("a " * (MAX_DOCUMENT_CHARS // 2 + 1))


def test_non_string_input_is_rejected(engine):
    with pytest.raises(TypeError):
        engine.analyse(b"bytes")  # type: ignore[arg-type]


def test_metrics_are_reported(engine):
    text = "Caste shapes tenure. The study argues this clearly."
    metrics = engine.analyse(text)["metrics"]
    assert metrics["words"] == 8
    assert metrics["sentences"] == 2
    assert metrics["paragraphs"] == 1
    assert 0 <= metrics["flesch_reading_ease"] <= 100
    assert metrics["average_sentence_words"] == 4.0


def test_findings_are_capped_for_very_long_documents(engine):
    text = "teh typo repeated. " * 400
    report = engine.analyse(text)
    assert report["truncated"] is True
    assert len(report["diagnostics"]) <= 600
    # A single rule cannot swamp the report or the marker layer.
    spelling = [
        item
        for item in report["diagnostics"]
        if item["rule"] in {"spelling.unknown-word", "spelling.misspelling"}
    ]
    assert len(spelling) <= 120
    assert any("first" in note for note in report["notes"])


# --------------------------------------------------------- markdown internals


def test_mask_marks_code_and_references():
    text = "Prose.\n\n```py\ncode\n```\n\nReferences\n\nGupta (2000). Teh.\n"
    mask = _Mask(text)
    assert mask.blocked(text.index("```"), text.index("```") + 3)
    assert mask.blocked(text.index("References"), len(text))
    assert not mask.blocked(0, 5)


def test_british_dictionary_helper():
    checker = _spell_checker()
    assert _dictionary_knows("behaviour", checker)
    assert _dictionary_knows("caste", checker)
    assert not _dictionary_knows("teh", checker)


def test_personal_dictionary_round_trip(tmp_path):
    dictionary = PersonalDictionary(tmp_path / "dict.json")
    assert dictionary.words() == []
    assert dictionary.add("zamindariyy") == ["zamindariyy"]
    assert dictionary.add("Zamindariyy") == ["zamindariyy"]
    assert dictionary.add("Jajmani") == ["Jajmani", "zamindariyy"]
    assert dictionary.remove("zamindariyy") == ["Jajmani"]
    assert PersonalDictionary(tmp_path / "dict.json").words() == ["Jajmani"]


def test_personal_dictionary_rejects_unsafe_words(tmp_path):
    dictionary = PersonalDictionary(tmp_path / "dict.json")
    for bad in ("", "   ", "two words", "semi;colon", "x" * 65, "1234"):
        with pytest.raises(ValueError):
            dictionary.add(bad)


def test_personal_dictionary_survives_a_corrupt_file(tmp_path):
    path = tmp_path / "dict.json"
    path.write_text("{not json", encoding="utf-8")
    assert PersonalDictionary(path).words() == []
    assert PersonalDictionary(path).add("Jajmani") == ["Jajmani"]


# -------------------------------------------------------------- performance


def test_long_document_is_analysed_quickly(engine):
    paragraph = (
        "Caste shapes access to land in rural India (Gupta, 2000). "
        "This pattern persists where tenancy law is weakly enforced, and it shapes credit."
    )
    text = "\n\n".join([paragraph] * 1400)
    assert len(text) > 180_000
    started = time.perf_counter()
    report = engine.analyse(text)
    elapsed = time.perf_counter() - started
    assert report["counts"]["total"] >= 0
    assert elapsed < 25, f"analysis took {elapsed:.1f}s"
    check_offsets(text, report)


def test_pathological_input_cannot_stall_the_analysis(engine):
    """ReDoS regression: the mask must not backtrack on adversarial text.

    The three patterns reported by CodeQL (a code fence line of spaces, a
    "references" heading with many tabs, and "there is" followed by repeated
    quantifier words) are exercised with input designed to blow up a
    backtracking engine. Each analysis must finish promptly.
    """
    cases = {
        "spaces after a fence": "```" + " " * 40_000 + "\nprose after\n",
        "reference heading with tabs": "References" + "\t" * 40_000 + "\n\nBody text.\n",
        "repeated quantifiers": "There is " + "numerous " * 20_000 + "studies here.",
        "fence-like lines": ("~~~" + " " * 5_000 + "\n") * 20,
        "tabs before a heading": "\t" * 20_000 + "References\n",
    }
    for name, text in cases.items():
        started = time.perf_counter()
        report = engine.analyse(text)
        elapsed = time.perf_counter() - started
        assert report["counts"]["total"] >= 0
        assert elapsed < 5, f"{name} took {elapsed:.2f}s: possible catastrophic backtracking"
        check_offsets(text, report)


@pytest.mark.skipif(not spelling_engine_available(), reason="pyspellchecker is not installed")
def test_spelling_engine_reports_its_provenance(engine):
    report = engine.analyse("A teh typo.")
    assert "pyspellchecker" in report["engine"]["spelling"]
    assert "MIT" in report["engine"]["spelling"]
