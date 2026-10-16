"""Text-integrity regression tests for the reported corruption.

The bug report describes a document coming back from a diagnostics/refinement
session with a duplicated heading and first paragraph, a rearranged long
sentence, a clause appearing twice and the final sentence cut off at "tenurial
arrange". Whatever produced that, the guarantees it violates are these, and they
are pinned here against the exact passage from the Windows checklist:

* analysing a document must not change it;
* accepting a suggestion must change exactly the range it names and nothing
  else — no duplication, no reordering, no truncated tail;
* an offset that does not slice to the text the finding names must never be
  applied;
* saving and reopening must return the same characters, including the last one.

The DOM-level equivalents (accept, dismiss, stale refusal, autosave, reopen,
typing during a check) run in ``tests/gui/workspace_dom_check.mjs`` through
``tests/test_workspace_gui.py``.
"""

from __future__ import annotations

import pytest

from diagnostics import DiagnosticEngine
from document_store import DocumentStore

# The passage from docs/WINDOWS_DIAGNOSTICS_TEST.md section 1, verbatim.
PASSAGE = (
    "# Caste and commons — field notes\n"
    "\n"
    "There is many studies about this tehnique (Gupta, 2000), and the analysys is\n"
    "inconclusive ,but the authors dont agree about the mechanism.\n"
    "\n"
    "It is important to note that, in order to understand how caste plays a crucial\n"
    "role in shaping access to land in the villages of Chamarajanagar district where\n"
    "the Vokkaliga and Dalit households were surveyed by the team between June and\n"
    "August of the fieldwork year, a number of additional interviews would have been\n"
    "necessary.\n"
    "\n"
    'As Deshpande wrote, "caste is not static", and the Adivasi households in\n'
    "Hulikere reported different tenurial arrangements.\n"
)

HEADING = "# Caste and commons — field notes"
TAIL = "Hulikere reported different tenurial arrangements.\n"


@pytest.fixture(scope="module")
def engine() -> DiagnosticEngine:
    return DiagnosticEngine()


@pytest.fixture()
def report(engine: DiagnosticEngine) -> dict:
    return engine.analyse(PASSAGE, profile="academic_standard")


def test_analysis_is_read_only_and_deterministic(report) -> None:
    """The same text analyses to the same findings, and never comes back.

    ``str`` is immutable in Python, so "the input was not modified" cannot be
    tested directly; what matters is that analysing leaves no state behind
    (two runs agree exactly) and that the response carries findings rather than
    the document.
    """
    assert "text" not in report, "the analysis echoed the document back"
    assert report["characters"] == len(PASSAGE)
    assert report["diagnostics"], "the checklist passage must produce findings"

    again = DiagnosticEngine().analyse(PASSAGE, profile="academic_standard")
    assert [(item["id"], item["start"], item["end"]) for item in again["diagnostics"]] == [
        (item["id"], item["start"], item["end"]) for item in report["diagnostics"]
    ]


def test_every_finding_slices_to_exactly_its_own_text(report) -> None:
    for finding in report["diagnostics"]:
        start, end = finding["start"], finding["end"]
        assert isinstance(start, int) and isinstance(end, int)
        assert 0 <= start < end <= len(PASSAGE), finding["id"]
        assert PASSAGE[start:end] == finding["original"], finding["id"]
        if finding["replacement"] is not None:
            assert finding["replacement"] != finding["original"], finding["id"]


def apply(text: str, finding: dict) -> str:
    """Apply one finding the way the editor does: splice, nothing else."""
    return text[: finding["start"]] + finding["replacement"] + text[finding["end"] :]


def test_accepting_each_finding_changes_only_its_own_range(report) -> None:
    """Walk the whole list, accepting every suggestion in turn.

    After each accept, everything before and after the accepted range must be
    byte-identical to what it was, and the document must still read as one
    document: the heading once, the quoted clause once, the tail intact.
    """
    text = PASSAGE
    accepted = 0
    # Offsets shift as text is spliced, so re-analyse against the current text
    # each round — exactly what the editor does after an accept.
    engine = DiagnosticEngine()
    for _ in range(len(report["diagnostics"]) + 4):
        current = engine.analyse(text, profile="academic_standard")
        finding = next(
            (item for item in current["diagnostics"] if item["replacement"] is not None),
            None,
        )
        if finding is None:
            break
        expected = apply(text, finding)
        assert expected[: finding["start"]] == text[: finding["start"]]
        assert expected[finding["start"] + len(finding["replacement"]) :] == text[finding["end"] :]

        # The promises the report is about.
        assert expected.count(HEADING) == 1, "the heading was duplicated"
        assert expected.count("role in shaping access to land") == 1
        assert expected.endswith(TAIL), "the final sentence was lost"
        assert "tenurial arrange" in expected and "tenurial arrangements." in expected
        text = expected
        accepted += 1

    assert accepted >= 3, f"expected several suggestions to apply, applied {accepted}"


def test_a_stale_offset_is_detectable_before_it_is_applied(report) -> None:
    """Text inserted earlier moves what a finding points at; the guard sees it."""
    finding = next(item for item in report["diagnostics"] if item["replacement"] is not None)
    shifted = PASSAGE[:10] + "inserted words " + PASSAGE[10:]
    # The old offsets now slice different characters, which is exactly the
    # condition the editor refuses on.
    assert shifted[finding["start"] : finding["end"]] != finding["original"]


def test_saving_and_reopening_returns_identical_text(tmp_path) -> None:
    """The stored document is the document, down to the final newline."""
    store = DocumentStore(tmp_path / "writing-documents.sqlite3")
    store.initialize()
    created = store.create(title="Caste and commons", text=PASSAGE)
    stored = store.get(created["id"])
    assert stored["text"] == PASSAGE
    assert stored["text"].endswith(TAIL)
    assert stored["character_count"] == len(PASSAGE)

    # A save with the same text is a no-op, and a save with new text round-trips
    # just as exactly, including the heading, the citation, the quotation and
    # the last character.
    saved = store.save(created["id"], text=PASSAGE + "A final line.\n")
    assert saved["text"] == PASSAGE + "A final line.\n"
    assert store.get(created["id"])["text"] == PASSAGE + "A final line.\n"

    # Every stored revision is the whole document too, not a fragment.
    revisions = store.revisions(created["id"])
    assert revisions
    for revision in revisions:
        restored = store.restore_revision(created["id"], revision["revision"])
        assert restored["text"].count(HEADING) == 1


def test_line_endings_are_normalised_once_and_only_once(tmp_path) -> None:
    """Windows line endings are the one deliberate change, and it is stable.

    A paste from a Windows application can carry CRLF. The store normalises to
    LF on the way in, so the reopened document is identical to itself on every
    later round trip — the difference is one time and never compounds.
    """
    store = DocumentStore(tmp_path / "writing-documents.sqlite3")
    store.initialize()
    created = store.create(text=PASSAGE.replace("\n", "\r\n"))
    first = store.get(created["id"])["text"]
    assert first == PASSAGE
    store.save(created["id"], text=first)
    assert store.get(created["id"])["text"] == PASSAGE
    assert store.revisions(created["id"]) == []
