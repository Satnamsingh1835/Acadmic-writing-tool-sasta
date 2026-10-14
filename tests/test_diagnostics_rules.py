"""Rule-by-rule tests for the spelling, grammar, punctuation and clarity rules.

Each test names the exact text, the exact offsets and the exact replacement, so
a failure shows which rule changed rather than only that a count moved. The
false-positive tests are as important as the detection tests: a checker that
flags a researcher's caste term or a place name is worse than one that misses a
typo, so the protection rules are pinned here too.
"""

from __future__ import annotations

import pytest

from diagnostics import DiagnosticEngine, spelling_engine_available
from diagnostic_lexicon import PROTECTED_WORDS, is_protected_word, looks_like_acronym


@pytest.fixture(scope="module")
def engine() -> DiagnosticEngine:
    return DiagnosticEngine()


def rules(report: dict) -> set[str]:
    return {item["rule"] for item in report["diagnostics"]}


def only(report: dict, rule: str) -> dict:
    items = [item for item in report["diagnostics"] if item["rule"] == rule]
    assert items, f"{rule} did not fire; got {sorted(rules(report))}"
    return items[0]


def assert_offsets(text: str, report: dict) -> None:
    for item in report["diagnostics"]:
        assert text[item["start"]:item["end"]] == item["original"], item


# ---------------------------------------------------------------- misspelling


@pytest.mark.skipif(not spelling_engine_available(), reason="pyspellchecker is not installed")
def test_misspelling_is_distinguished_from_an_unknown_word(engine):
    """One edit from a dictionary word is a typo; no candidate is not an error."""
    typo = only(engine.analyse("A careful analysys of the interviews."), "spelling.misspelling")
    assert typo["original"] == "analysys"
    assert typo["replacement"] == "analysis"
    assert typo["kind"] == "error"
    assert typo["confidence"] == "high"

    unknown = only(engine.analyse("The vorsichtung of the record."), "spelling.unknown-word")
    assert unknown["original"] == "vorsichtung"
    assert unknown["replacements"] == [], "an unfamiliar word must not be rewritten"
    assert unknown["replacement"] is None
    assert unknown["confidence"] == "medium"


@pytest.mark.skipif(not spelling_engine_available(), reason="pyspellchecker is not installed")
def test_sentence_initial_typo_is_reported_cautiously(engine):
    item = only(engine.analyse("Teh data is inconclusive."), "spelling.misspelling")
    assert item["original"] == "Teh"
    assert item["replacement"] == "the"
    assert item["confidence"] == "medium", "a capitalised word could be a name"


@pytest.mark.skipif(not spelling_engine_available(), reason="pyspellchecker is not installed")
def test_proper_nouns_are_never_reported_as_spelling_problems(engine):
    """Names, communities, places, field terms and abbreviations are protected."""
    texts = [
        "Iqbal interviewed Deshpande about the survey.",
        "Dalit and Adivasi households in Karnataka were surveyed.",
        "Mahadalit families in Bihar reported jajmani ties.",
        "The Vokkaliga and Lingayat communities of Hubballi.",
        "Fieldwork in Chamarajanagar and Kalaburagi districts.",
        "An NFHS-5 round and the NSS-68 schedule, published by MoSPI.",
        "The Department of Sociology at Shivaji University.",
    ]
    for text in texts:
        report = engine.analyse(text)
        assert [
            item for item in report["diagnostics"] if item["category"] == "spelling"
        ] == [], text


@pytest.mark.skipif(not spelling_engine_available(), reason="pyspellchecker is not installed")
def test_a_word_the_author_capitalises_midsentence_is_protected(engine):
    """Consistent capitalisation is evidence of a name, not of a typo."""
    text = "The Heggodde family migrated. Later, Heggodde returned to the village."
    assert engine.analyse(text)["counts"]["by_category"]["spelling"] == 0


@pytest.mark.skipif(not spelling_engine_available(), reason="pyspellchecker is not installed")
def test_dictionary_words_are_never_flagged_and_personal_terms_silence_a_word(engine):
    person = DiagnosticEngine(personal_dictionary=["vorsichtung"])
    assert person.analyse("The vorsichtung of the record.")["counts"]["by_category"]["spelling"] == 0
    assert engine.analyse("The methodology was rigorous.")["counts"]["by_category"]["spelling"] == 0


@pytest.mark.skipif(not spelling_engine_available(), reason="pyspellchecker is not installed")
def test_spelling_classification_does_not_depend_on_position_in_the_document(engine):
    """The old suggestion budget reclassified late typos; it must not come back."""
    text = ("A long introduction with ordinary words follows here. " * 60) + " The analysys is."
    item = only(engine.analyse(text), "spelling.misspelling")
    assert item["original"] == "analysys"
    assert item["replacement"] == "analysis"


def test_lexicon_helpers_behave():
    assert is_protected_word("dalit")
    assert is_protected_word("bengaluru")
    assert not is_protected_word("teh")
    assert is_protected_word("heggadepur", capitalized=True)
    assert not is_protected_word("heggadepur"), "the suffix rule needs capitalisation"
    assert "karnataka" in PROTECTED_WORDS
    for token in ("SC", "NSSO", "NFHS-5", "MoSPI", "DOI"):
        assert looks_like_acronym(token), token
    for token in ("Karnataka", "teh", "caste"):
        assert not looks_like_acronym(token), token


# ------------------------------------------------------------------ articles


@pytest.mark.parametrize(
    "text,original,replacement",
    [
        ("It was a apple.", "a", "an"),
        ("She is an book author.", "an", "a"),
        ("A hour later the rain stopped.", "A", "An"),
        ("They found an unique pattern.", "an", "a"),
    ],
)
def test_article_errors_are_reported_with_the_correction(engine, text, original, replacement):
    item = only(engine.analyse(text), "grammar.article-an")
    assert item["original"] == original
    assert item["replacement"] == replacement
    assert text[item["start"]:item["end"]] == original
    assert item["kind"] == "error"


@pytest.mark.parametrize(
    "text",
    [
        "A university report.",
        "An hour of fieldwork.",
        "A European comparision.",  # spelling aside, the article is right
        "An MBA graduate joined the team.",
        "A UN report followed.",
        "An honest account of the survey.",
        "A one-off settlement.",
        "The data covers an area of 40 hectares.",
    ],
)
def test_correct_articles_are_left_alone(engine, text):
    report = engine.analyse(text)
    assert [item for item in report["diagnostics"] if item["rule"] == "grammar.article-an"] == []


# -------------------------------------------------------------- apostrophes


@pytest.mark.parametrize(
    "text,original,replacement",
    [
        ("I dont agree with the finding.", "dont", "don't"),
        ("They havent finished the coding.", "havent", "haven't"),
        ("It isnt clear from the data.", "isnt", "isn't"),
        ("The results werent significant.", "werent", "weren't"),
    ],
)
def test_missing_apostrophes_are_reported_once(engine, text, original, replacement):
    report = engine.analyse(text)
    item = only(report, "punctuation.missing-apostrophe")
    assert item["original"] == original
    assert item["replacement"] == replacement
    assert item["kind"] == "error"
    assert text[item["start"]:item["end"]] == original
    # The spelling pass must not also call the same word unknown.
    assert not [
        entry
        for entry in report["diagnostics"]
        if entry["category"] == "spelling" and entry["original"].lower() == original
    ], report["diagnostics"]


@pytest.mark.skipif(not spelling_engine_available(), reason="pyspellchecker is not installed")
def test_a_contraction_inside_a_quotation_is_left_alone(engine):
    text = 'As Gupta wrote, "I dont think caste is static", which the field disputes.'
    assert not [
        item for item in engine.analyse(text)["diagnostics"] if item["rule"].startswith("punctuation.missing-apostrophe")
    ]


# ---------------------------------------------------------------- usage rules


def test_mass_nouns_are_not_pluralised(engine):
    report = engine.analyse("The informations and equipments were catalogued.")
    items = [item for item in report["diagnostics"] if item["rule"] == "grammar.mass-noun-plural"]
    assert sorted(item["original"] for item in items) == ["equipments", "informations"]
    assert sorted(item["replacement"] for item in items) == ["equipment", "information"]


@pytest.mark.parametrize(
    "text,original,replacement",
    [
        ("They discuss about caste.", "discuss about", "discuss"),
        ("The authors emphasise on land.", "emphasise on", "emphasise"),
        ("She discussed about the survey.", "discussed about", "discussed"),
    ],
)
def test_redundant_prepositions_are_reported(engine, text, original, replacement):
    item = only(engine.analyse(text), "grammar.redundant-preposition")
    assert item["original"] == original
    assert item["replacement"] == replacement
    assert item["confidence"] == "medium"


def test_notes_about_are_not_rewritten(engine):
    """"notes about" is correct English; only the transitive verbs are listed."""
    report = engine.analyse("The report notes about land records in the district.")
    assert [item for item in report["diagnostics"] if item["rule"] == "grammar.redundant-preposition"] == []


# ------------------------------------------------------------------- clarity


def test_a_bare_this_shows_is_questioned_without_a_replacement(engine):
    item = only(engine.analyse("This shows that the pattern holds."), "clarity.ambiguous-this")
    assert item["original"] == "This"
    assert item["replacements"] == [], "the engine cannot know which noun the author means"
    assert item["kind"] == "style"
    assert item["confidence"] == "low"


def test_a_named_subject_is_not_questioned(engine):
    for text in (
        "This finding shows that the pattern holds.",
        "This pattern suggests a slower shift.",
        "The result shows that the pattern holds.",
    ):
        report = engine.analyse(text)
        assert [item for item in report["diagnostics"] if item["rule"] == "clarity.ambiguous-this"] == []


# ------------------------------------------------------------------ offsets


def test_offsets_hold_for_unicode_markdown_and_multiple_findings(engine):
    text = (
        "# Findings — a working draft\n\n"
        'The authors wrote, "caste is not static", and they dont say more.\n\n'
        "```\n"
        "teh code block must stay untouched\n"
        "```\n\n"
        "It was a apple, and the datas were incomplete.\n"
    )
    report = engine.analyse(text)
    assert_offsets(text, report)
    found = rules(report)
    assert "punctuation.missing-apostrophe" in found
    assert "grammar.article-an" in found
    assert "grammar.mass-noun-plural" in found
    # Markdown structure and the fenced block are preserved exactly.
    assert text[report["diagnostics"][0]["start"]:][:1] != "`"
    assert "teh code block" not in [item["original"] for item in report["diagnostics"]]
    assert text.startswith("# Findings — a working draft\n\n")


def test_repeated_adjacent_word_is_reported_as_an_error(engine):
    text = "The the sample was small."
    item = only(engine.analyse(text), "repetition.repeated-word")
    assert item["original"].lower() == "the"
    assert text[item["start"]:item["end"]] == item["original"]
    assert item["confidence"] == "high"
    # A word typed twice is an error, not an optional style preference.
    assert item["kind"] == "error"
    assert item["group"] == "repetition"


@pytest.mark.parametrize("word", ["had", "that", "very"])
def test_a_doubling_that_is_often_deliberate_stays_a_style_option(engine, word):
    text = f"The sample {word} {word} small effect reported."
    item = only(engine.analyse(text), "repetition.repeated-word")
    assert item["kind"] == "style"
    assert item["confidence"] == "medium"
    assert "deliberately" in item["explanation"]


# -------------------------------------------------------- performance bounds


def test_a_long_document_is_analysed_within_a_typing_budget(engine):
    """A full paper has to stay comfortably inside one debounce interval.

    The engine runs on the server thread while the writer keeps typing, so the
    budget is deliberately generous (the check fails only on a real regression
    such as the quadratic masking that a binary search replaced).
    """
    import time

    paragraph = (
        "The caste data was analysed carefully in this study (Gupta, 2000). "
        "It is important to note that the findings are inconclusive, and the "
        "authors dont agree about the mechanism.\n\n"
    )
    text = paragraph * 400  # ~120,000 characters, a long article
    started = time.perf_counter()
    report = engine.analyse(text)
    elapsed = time.perf_counter() - started
    assert report["characters"] == len(text)
    assert elapsed < 6.0, f"{len(text):,} characters took {elapsed:.2f}s"
    assert_offsets(text, report)


def test_adversarial_documents_stay_bounded_too(engine):
    """Nonsense, repetition and markup soup must not cost seconds."""
    import time

    cases = {
        "unknown words": " ".join(["zzqv"] * 20_000),
        "repeated typo": " ".join(["teh"] * 20_000),
        "many citations": " ".join(["(Gupta, 2000)"] * 5_000),
        "many code spans": " ".join(["`code`"] * 5_000),
        "many fences": "```\nprose\n```\n" * 500,
        "long URLs": " ".join(["https://example.org/a/b/c/d/e/f/g"] * 2_000),
        "no spaces": "x" * 50_000,
    }
    for name, text in cases.items():
        started = time.perf_counter()
        report = engine.analyse(text)
        elapsed = time.perf_counter() - started
        assert report["counts"]["total"] >= 0
        assert elapsed < 6.0, f"{name} took {elapsed:.2f}s"
        assert_offsets(text, report)


def test_the_report_says_when_it_stopped_early(engine):
    report = engine.analyse(" ".join(["zzqv"] * 5_000))
    assert report["truncated"] is True
    assert any("stopped examining" in note for note in report["notes"]), report["notes"]


# ------------------------------------------------------------- failure modes


def test_a_missing_dictionary_degrades_to_the_other_rules(engine, monkeypatch):
    """The engine must still check grammar and punctuation without the package."""
    import diagnostics

    def broken():
        raise ImportError("pyspellchecker is not installed")

    monkeypatch.setattr(diagnostics, "_spell_checker", broken)
    report = engine.analyse("The datas was unclear ,and the authors dont agree.")
    assert report["engine"]["spelling"] == "unavailable"
    assert report["engine"]["spelling_available"] is False
    rules_found = {item["rule"] for item in report["diagnostics"]}
    assert "punctuation.missing-apostrophe" in rules_found
    assert "grammar.mass-noun-plural" in rules_found
    assert any("dictionary is unavailable" in note for note in report["notes"]), report["notes"]


def test_an_unknown_category_or_a_non_string_is_rejected(engine):
    with pytest.raises(ValueError):
        engine.analyse("Some text.", categories=["spelling", "nonsense"])
    with pytest.raises(TypeError):
        engine.analyse(None)
    with pytest.raises(ValueError):
        engine.analyse("x" * 2_000_001)


# ------------------------------------------------- counts and overlapping


def test_several_findings_in_one_sentence_all_point_at_their_own_text(engine):
    # The bare-pronoun rule only claims a *sentence-opening* "This" (a mid-sentence
    # one is far too common to be worth reporting), so the sample opens a sentence.
    text = "Teh authors dont discuss about the datas. This shows a lot of problems.\n"
    report = engine.analyse(text)
    assert_offsets(text, report)
    found = rules(report)
    for expected in (
        "spelling.misspelling",
        "punctuation.missing-apostrophe",
        "grammar.redundant-preposition",
        "grammar.mass-noun-plural",
        "clarity.ambiguous-this",
        "tone.vague-quantifier",
    ):
        assert expected in found, (expected, sorted(found))
    starts = [item["start"] for item in report["diagnostics"]]
    assert starts == sorted(starts), "findings are ordered by position"


def test_overlapping_findings_are_both_kept(engine):
    """A long sentence that is also wordy reports both, with their own ranges."""
    text = "In order to clarify the matter, " + " ".join(["word"] * 60) + " and it continues.\n"
    report = engine.analyse(text)
    assert_offsets(text, report)
    long_sentence = [item for item in report["diagnostics"] if item["rule"] == "readability.long-sentence"]
    wordiness = [item for item in report["diagnostics"] if item["rule"] == "wordiness.longer-phrase"]
    assert long_sentence and wordiness
    assert wordiness[0]["start"] >= long_sentence[0]["start"]
    assert wordiness[0]["end"] <= long_sentence[0]["end"]


def test_citations_quotations_and_urls_are_not_prose(engine):
    text = (
        "Gupta (2000) argues that \"caste is not static\", as the DOI "
        "https://doi.org/10.1000/xyz123 and the report (Singh and Rao, 2019) show.\n"
    )
    report = engine.analyse(text)
    assert_offsets(text, report)
    for item in report["diagnostics"]:
        assert "doi.org" not in item["original"]
        assert item["original"] not in {"10.1000/xyz123"}
