from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_rea_fixture_covers_academic_preservation_cases():
    text = (ROOT / "docs" / "rea-study" / "fixtures.md").read_text(encoding="utf-8")
    for phrase in ("Agreement", "Citation and quotation", "Disciplinary terms", "DOI-shaped string"):
        # Allow the corpus heading text to vary while requiring all test themes.
        if phrase == "Disciplinary terms":
            assert "disciplinary terms" in text.casefold()
        else:
            assert phrase.casefold() in text.casefold()


def test_competitor_reports_do_not_claim_observations_before_testing():
    for filename in ("grammarly-free.md", "quillbot-free.md"):
        text = (ROOT / "docs" / "rea-study" / filename).read_text(encoding="utf-8")
        assert "NOT TESTED" in text


def test_readiness_script_is_dry_run_by_default():
    text = (ROOT / "scripts" / "rea-readiness.ps1").read_text(encoding="utf-8")
    assert "$RunSetup" in text
    assert "RUN_SETUP" in text
    assert "npx --yes rea-agents@6.4.0 setup" in text
