"""Tests for the diagnostic contract: versions, taxonomy, groups and profiles.

The request asks for a structured, versioned diagnostic model and for academic
profiles that enable, disable or reprioritise style rules without ever changing
document text. These tests pin the parts a client depends on.
"""

from __future__ import annotations

import pytest

from diagnostics import (
    CATEGORY_GROUP,
    CATEGORY_ORDER,
    DEFAULT_RULE_VERSION,
    DIAGNOSTIC_GROUPS,
    ENGINE_VERSION,
    ERROR_CATEGORIES,
    GROUP_ORDER,
    PROFILES,
    RULESET_VERSION,
    STYLE_CATEGORIES,
    DiagnosticEngine,
    normalize_profile,
    rule_version,
)


@pytest.fixture(scope="module")
def engine() -> DiagnosticEngine:
    return DiagnosticEngine()


REQUIRED_DIAGNOSTIC_FIELDS = {
    "id",
    "rule",
    "rule_version",
    "engine_version",
    "ruleset_version",
    "category",
    "category_label",
    "group",
    "group_label",
    "kind",
    "severity",
    "confidence",
    "priority",
    "message",
    "explanation",
    "start",
    "end",
    "original",
    "replacement",
    "replacements",
}

TEXT = (
    "Teh study was very very wordy and it is important to note that the results "
    "is inconclusive , and This shows that caste does not matters.\n"
)

PROFILES_TO_CHECK = ("academic_standard", "formal_academic", "concise_academic")


def test_every_diagnostic_carries_the_full_contract(engine):
    report = engine.analyse(TEXT)
    assert report["diagnostics"], "the sample text should produce findings"
    for item in report["diagnostics"]:
        assert REQUIRED_DIAGNOSTIC_FIELDS <= set(item), sorted(
            REQUIRED_DIAGNOSTIC_FIELDS - set(item)
        )
        assert item["engine_version"] == ENGINE_VERSION
        assert item["ruleset_version"] == RULESET_VERSION
        assert item["rule_version"] == rule_version(item["rule"])
        assert item["severity"] == item["kind"] in {"error", "style"}
        assert item["confidence"] in {"high", "medium", "low"}
        assert isinstance(item["priority"], int)
        assert item["category"] in set(CATEGORY_ORDER)
        assert item["group"] in DIAGNOSTIC_GROUPS
        assert item["group_label"] == DIAGNOSTIC_GROUPS[item["group"]]["label"]
        assert item["category_label"]
        assert item["message"] and item["explanation"]
        assert item["start"] < item["end"]
        assert item["replacement"] == (item["replacements"][0] if item["replacements"] else None)


def test_the_requested_taxonomy_is_complete_and_used():
    assert set(DIAGNOSTIC_GROUPS) == {
        "spelling",
        "grammar",
        "punctuation",
        "sentence_structure",
        "clarity",
        "concision",
        "academic_style",
        "repetition",
    }
    assert set(CATEGORY_GROUP) == set(CATEGORY_ORDER), "every category needs a group"
    assert set(CATEGORY_GROUP.values()) <= set(DIAGNOSTIC_GROUPS)
    assert CATEGORY_ORDER and GROUP_ORDER


def test_versions_are_declared_and_monotonic_in_shape():
    assert ENGINE_VERSION.count(".") == 2
    assert RULESET_VERSION
    assert DEFAULT_RULE_VERSION
    for name in CATEGORY_ORDER:
        assert name in CATEGORY_GROUP


@pytest.mark.parametrize("profile", PROFILES_TO_CHECK)
def test_error_rules_run_in_every_profile(engine, profile):
    """Spelling and the reliable grammar rules must never be switched off."""
    text = "Teh data was collected. The results is clear. Students was asked.\n"
    report = engine.analyse(text, profile=profile)
    rules = {item["rule"] for item in report["diagnostics"]}
    assert "spelling.unknown-word" in rules or "spelling.misspelling" in rules, sorted(rules)
    assert any(
        item["category"] in {"agreement", "capitalization"} for item in report["diagnostics"]
    ), sorted(rules)
    checked = set(report["engine"]["checked_categories"])
    error_categories = {item["id"] for item in DiagnosticEngine.categories() if item["kind"] == "error"}
    for category in error_categories:
        if category not in checked:
            pytest.fail(f"{category} was not checked in profile {profile}")


@pytest.mark.parametrize("profile", PROFILES_TO_CHECK)
def test_style_rules_follow_the_profile(engine, profile):
    """A style category the profile leaves out must not appear in its report."""
    text = (
        "It is important to note that in order to understand caste, a number of "
        "authors have argued that this is a very very significant point, and it "
        "is worth noting that the field is kind of fragmented.\n"
    )
    report = engine.analyse(text, profile=profile)
    style_categories = {item["category"] for item in report["diagnostics"] if item["kind"] == "style"}
    allowed = set(PROFILES[profile].style_categories)
    assert style_categories <= allowed, (profile, sorted(style_categories - allowed))


def test_profiles_change_which_style_categories_are_reported(engine):
    text = (
        "It is important to note that a number of scholars don't agree, and the "
        "argument is kind of weak.\n"
    )
    standard = {
        item["category"] for item in engine.analyse(text, profile="academic_standard")["diagnostics"]
    }
    formal = {
        item["category"] for item in engine.analyse(text, profile="formal_academic")["diagnostics"]
    }
    concise = {
        item["category"] for item in engine.analyse(text, profile="concise_academic")["diagnostics"]
    }
    # Standard is the superset; formal keeps register, concise keeps brevity.
    assert formal <= standard and concise <= standard
    assert "wordiness" in standard and "wordiness" not in formal
    assert "tone" not in concise


def test_profiles_reprioritise_rather_than_rewrite(engine):
    text = "In order to be concise, the authors don't say much.\n"
    standard = engine.analyse(text, profile="academic_standard")
    concise = engine.analyse(text, profile="concise_academic")
    # Same text in, same text out: analysis never edits the document.
    assert standard["text_sha256"] == concise["text_sha256"]
    standard_wordiness = [
        item["priority"] for item in standard["diagnostics"] if item["category"] == "wordiness"
    ]
    concise_wordiness = [
        item["priority"] for item in concise["diagnostics"] if item["category"] == "wordiness"
    ]
    assert standard_wordiness and concise_wordiness
    assert concise_wordiness[0] < standard_wordiness[0]


def test_concise_profile_questions_longer_sentences_sooner(engine):
    sentence = " ".join(["word"] * 30) + " and the argument continues here.\n"
    formal = engine.analyse(sentence, profile="formal_academic")
    concise = engine.analyse(sentence, profile="concise_academic")
    assert not [
        item for item in formal["diagnostics"] if item["rule"] == "readability.long-sentence"
    ]
    assert [
        item for item in concise["diagnostics"] if item["rule"] == "readability.long-sentence"
    ], "the concise profile should question a 30-word sentence"


def test_profile_aliases_resolve_to_the_canonical_profiles():
    for alias, expected in {
        "standard": "academic_standard",
        "medium": "academic_standard",
        "polish": "concise_academic",
        "Concise": "concise_academic",
        "formal_academic": "formal_academic",
        "conservative": "formal_academic",
        "Concise-Academic": "concise_academic",
    }.items():
        assert normalize_profile(alias).id == expected
    assert normalize_profile(None).id == "academic_standard"


def test_unknown_profile_is_rejected_with_the_choices():
    with pytest.raises(ValueError) as error:
        normalize_profile("aggressive")
    assert "Unknown profile" in str(error.value)
    assert "academic_standard" in str(error.value)


def test_profiles_endpoint_payload_shape(engine):
    payload = engine.profiles()
    assert [item["id"] for item in payload] == list(PROFILES)
    for item in payload:
        assert set(item) >= {
            "id",
            "label",
            "summary",
            "style_categories",
            "thresholds",
            "always_on_categories",
        }
        assert item["style_categories"]
        assert item["always_on_categories"]
        assert set(item["always_on_categories"]) <= set(CATEGORY_ORDER)


def test_counts_are_reported_by_group_as_well_as_category(engine):
    report = engine.analyse(TEXT)
    by_group = report["counts"]["by_group"]
    assert set(by_group) == set(DIAGNOSTIC_GROUPS)
    assert sum(by_group.values()) == report["counts"]["total"]
    assert report["counts"]["total"] == (
        report["counts"]["error"] + report["counts"]["style"]
    )


def test_style_categories_are_exactly_the_style_kinds():
    for item in DiagnosticEngine.categories():
        assert (item["id"] in STYLE_CATEGORIES) == (item["kind"] == "style")
        assert item["group"] == CATEGORY_GROUP[item["id"]]
