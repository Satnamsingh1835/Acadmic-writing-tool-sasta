"""Deterministic, privacy-conscious receipts for academic revisions.

A receipt records what the editor did, the checks it performed, and what remains
unknown. It stores text digests rather than manuscript content so it can be
exported without duplicating the passage.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Literal

RECEIPT_SCHEMA_VERSION = "1.0"
Confidence = Literal["observed", "derived", "heuristic"]
OperationStatus = Literal["completed", "fallback", "not-requested"]


@dataclass(frozen=True)
class ReceiptOperation:
    name: str
    status: OperationStatus
    confidence: Confidence
    detail: str


@dataclass(frozen=True)
class ResidualUnknown:
    unknown_id: str
    question: str
    severity: Literal["low", "medium", "high"]
    evidence: tuple[str, ...]
    recommended_action: str


def text_digest(text: str) -> str:
    """Return a prefixed SHA-256 digest without retaining the supplied text."""
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _semantic_id(document: dict[str, object]) -> str:
    canonical = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"revision:{digest}"


def _safeguard_unknowns(safeguards: dict) -> list[ResidualUnknown]:
    unknowns = []
    for name, passed in safeguards.items():
        if isinstance(passed, bool) and not passed:
            label = name.replace("_", " ")
            unknowns.append(
                ResidualUnknown(
                    unknown_id=f"safeguard:{name}",
                    question=f"Why did the {label} safeguard fail?",
                    severity="high",
                    evidence=(f"{name}=false",),
                    recommended_action=(
                        "Compare the original and revised passages before using "
                        "the revision."
                    ),
                )
            )
    return unknowns


def _diagnostic_unknowns(
    grammar_and_style: dict,
    literature_review: dict,
) -> list[ResidualUnknown]:
    unknowns = []
    citation_diagnostics = grammar_and_style.get("citation_diagnostics", {})
    uncited = citation_diagnostics.get("possible_uncited_source_claims", [])
    if uncited:
        unknowns.append(
            ResidualUnknown(
                unknown_id="diagnostic:possible-uncited-claims",
                question="Are the flagged source-like claims adequately supported?",
                severity="high",
                evidence=(f"sentence_numbers={list(uncited)}",),
                recommended_action=(
                    "Check the source passage and add only citations that you have "
                    "personally verified."
                ),
            )
        )

    incomplete = []
    for paragraph in literature_review.get("paragraphs", []):
        missing = paragraph.get("missing", [])
        if missing:
            incomplete.append(
                {
                    "paragraph": paragraph.get("paragraph"),
                    "missing": list(missing),
                }
            )
    if incomplete:
        preview = incomplete[:10]
        unknowns.append(
            ResidualUnknown(
                unknown_id="diagnostic:literature-flow",
                question=(
                    "Do the flagged paragraphs need additional interpretation, "
                    "synthesis, gap framing, or connection to the research question?"
                ),
                severity="medium",
                evidence=(
                    f"flagged_paragraphs={json.dumps(preview, sort_keys=True)}",
                    f"total_flagged={len(incomplete)}",
                ),
                recommended_action=(
                    "Treat the prompts as questions for the researcher, not as a "
                    "requirement to manufacture missing content."
                ),
            )
        )
    return unknowns


def build_revision_receipt(
    *,
    original_text: str,
    refined_text: str,
    profile: str,
    provider: str,
    llm_requested: bool,
    llm_used: bool,
    safeguards: dict,
    grammar_and_style: dict,
    literature_review: dict,
    notices: list[str],
) -> dict[str, object]:
    """Build a deterministic receipt for one completed editor request."""
    if llm_used:
        llm_operation = ReceiptOperation(
            name="model-enhancement",
            status="completed",
            confidence="derived",
            detail=(
                f"Output from {provider} passed citation-marker and expansion checks."
            ),
        )
    elif llm_requested:
        llm_operation = ReceiptOperation(
            name="model-enhancement",
            status="fallback",
            confidence="observed",
            detail=notices[-1] if notices else "The deterministic result was retained.",
        )
    else:
        llm_operation = ReceiptOperation(
            name="model-enhancement",
            status="not-requested",
            confidence="observed",
            detail="No external model provider was called.",
        )

    operations = (
        ReceiptOperation(
            name="deterministic-language-revision",
            status="completed",
            confidence="observed",
            detail=f"Applied the {profile} editing profile.",
        ),
        ReceiptOperation(
            name="academic-style-diagnostics",
            status="completed",
            confidence="heuristic",
            detail="Detected wording, citation, and sentence-level signals.",
        ),
        ReceiptOperation(
            name="literature-flow-diagnostics",
            status="completed",
            confidence="heuristic",
            detail="Detected rhetorical roles and generated researcher prompts.",
        ),
        llm_operation,
    )

    residual_unknowns = [
        ResidualUnknown(
            unknown_id="review:semantic-equivalence",
            question=(
                "Does the revision preserve the author's intended meaning, "
                "emphasis, and disciplinary terminology?"
            ),
            severity="high",
            evidence=("Automated structural checks cannot prove semantic equivalence.",),
            recommended_action=(
                "Read the original and revision side by side and modify or reject "
                "any unsuitable wording."
            ),
        ),
        *_safeguard_unknowns(safeguards),
        *_diagnostic_unknowns(grammar_and_style, literature_review),
    ]

    safeguard_results = {
        name: value
        for name, value in safeguards.items()
        if isinstance(value, bool)
    }
    body: dict[str, object] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "input_digest": text_digest(original_text),
        "output_digest": text_digest(refined_text),
        "profile": profile,
        "provider": provider,
        "llm_requested": llm_requested,
        "llm_used": llm_used,
        "operations": [asdict(operation) for operation in operations],
        "safeguards": safeguard_results,
        "limitations": [
            "Language diagnostics are heuristics, not evaluations of scholarship.",
            "Citation preservation does not verify that a source supports a claim.",
            "Structural checks cannot prove semantic equivalence.",
            "No source, quotation, fact, or interpretation is independently verified.",
        ],
        "residual_unknowns": [asdict(unknown) for unknown in residual_unknowns],
    }
    return {"receipt_id": _semantic_id(body), **body}
