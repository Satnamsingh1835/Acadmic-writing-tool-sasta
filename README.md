# Academic Literature Review Assistant / Research Synthesist

This repository now contains a modular Research Synthesist — Caste, Land, Commons & Social Boycott layer integrated with the existing researcher-controlled academic-writing system. It is designed for literature reviews and proposal development in sociology, anthropology, agrarian studies, caste studies, commons studies, Dalit studies, and rural political economy.

## What it does

- extracts structured source records from TXT/Markdown and optionally PDF;
- preserves page-level provenance when PDF text is available;
- builds comparative literature matrices;
- maps concepts and source-specific definitions;
- maps source positions without manufacturing disagreement;
- tracks historical-period evidence without flattening change and continuity;
- identifies explicit source-level gaps and labels cross-cluster relational gaps as analytical possibilities requiring verification;
- generates researchable questions from documented gaps;
- audits source traceability, page/quotation risks, citation mismatch, and overclaiming;
- exports matrices as JSON, CSV, Markdown, or SQLite.

It does not invent citations, page numbers, quotations, findings, theoretical positions, consensus, causal mechanisms, or research gaps.

## Existing-system integration

The existing Python/R academic-writing architecture remains intact. The new agent/ package is a research-analysis layer alongside academic_engine.py; language humanisation and researcher decision workflows are not replaced.

## Install

Core runtime: python -m pip install -r requirements.txt

PDF support: python -m pip install -r requirements-research.txt

## Commands

    python -m agent.cli source sources/paper.pdf --id S1
    python -m agent.cli matrix sources/*.pdf --format csv -o outputs/matrix.csv
    python -m agent.cli debate-map sources/*.pdf
    python -m agent.cli concept-map sources/*.pdf
    python -m agent.cli historical-synthesis sources/*.pdf
    python -m agent.cli gap-analysis sources/*.pdf
    python -m agent.cli research-questions sources/*.pdf
    python -m agent.cli audit sources/*.pdf --text drafts/review.txt

The CLI is deterministic. A later model-assisted layer can be added behind the structured records, but model output must retain provenance and pass validation.

## Evidence levels

A = direct evidence; B = strong interpretation; C = cross-source synthesis; D = analytical possibility; E = speculation. Generated academic prose should normally use A–C. D–E must remain explicitly labelled.

## Literature architecture

Configured clusters: LAND AND CASTE RELATIONS IN INDIA; COMMONS AND CASTE; CONCEPTUALISING SOCIAL BOYCOTT; LAND STRUGGLES IN PUNJAB. Sources may be cross-cutting rather than forced into one category.

## Human-in-the-loop

Major interpretive choices must be surfaced as DECISION REQUIRED with evidence and alternative interpretations. Researchers remain responsible for verifying source records and accepting substantive interpretations.

## Testing

Run pytest. CI continues to run the existing Python and R suites. New tests cover page provenance, candidate relational-gap labelling, traceability failures, invalid pages, citation mismatch, overclaiming, and editable configuration.
