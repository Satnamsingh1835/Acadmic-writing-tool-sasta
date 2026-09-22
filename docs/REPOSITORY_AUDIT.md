# Repository Audit — P1–P5

Date: 2026-09-22

## Scope

This audit covers the repository structure, CI configuration, test layout, API documentation, and the boundary between the R researcher workflow and the Python analytical engine.

## Current structure

### Python analytical layer

- `academic_engine.py` — orchestration
- `academic_analyser.py` — sentence-level diagnostics
- `academic_suggestions.py` — sentence-level suggestions
- `advanced_humanize.py` — editing profiles
- `humanize.py` — conservative language editing and safeguards
- `literature_review.py` — literature-review diagnostics
- `argument_diagnostics.py` — paragraph-level argument prompts
- `researcher_decisions.py` — researcher-controlled decisions
- `api.py` — FastAPI interface

### R researcher layer

- `R/academic_review.R` — API client
- `R/researcher_decisions.R` — decision workflow
- `R/workspace.R` — project workspace
- `R/academic_workflow.R` — researcher-facing helpers

### Tests

Python tests are currently distributed across the repository root and the `tests/` directory. This remains functional for pytest discovery, but is a consistency issue for later cleanup.

R tests use `tests/testthat.R` as the explicit entry point and live under `tests/testthat/`.

## Findings resolved by P1–P5

### P1 — R CI

The R workflow now installs the Ubuntu system libraries required to build transitive dependencies used by `httr2` and `testthat`. The workflow also uses only the intended `main` push and pull-request triggers.

The previous CI failure had moved past dependency installation and failed because an R test referenced the removed `R/academic_analyser.R` module. That stale test was removed as part of the P4 test-suite cleanup.

### P2 — API/documentation consistency

README documentation now describes the actual API surface:

- `GET /health`
- `POST /review`
- `POST /review/file`

It also documents UTF-8 `.txt` uploads, size limits, the current R-first workflow, and the researcher-controlled decision model without implying automatic scholarly evaluation.

### P3 — CI/configuration cleanup

The empty `.github/workflows/main.yml` file was removed.

The active Python workflow is retained because it is functional; its filename still contains the historical `conda` name even though the workflow now uses `actions/setup-python`. Renaming it is intentionally deferred so that this maintenance pass does not unnecessarily change a functioning workflow identity.

The root `environment.yml` is retained as an optional Conda environment definition rather than treated as a CI workflow.

### P4 — Test-suite standardisation

The R test entry point now contains only tests for currently supported R modules. The obsolete test for the removed R-native analyser was removed.

Python remains pytest-discoverable, including both root-level tests and tests under `tests/`.

A future cleanup task should consolidate Python test locations once the core analytical refactors are complete.

### P5 — Repository audit

This document records the current boundaries and deferred cleanup decisions so later tasks can distinguish intentional architecture from technical debt.

## Known deferred work

1. Build a shared parsing/signal layer before moving duplicated parsing logic.
2. Improve sentence segmentation and citation detection.
3. Consolidate Python test placement.
4. Add stronger R-to-API integration tests.
5. Audit Google Docs integration.
6. Add multilingual and quotation regression cases.
7. Define evaluation benchmarks.
8. Revisit the experimental Copilot automation with stronger researcher-control safeguards.

## Design invariant

The repository should preserve this boundary:

`R researcher workflow → HTTP API → Python analytical engine → structured diagnostics → researcher decision`

The analytical engine may propose diagnostics or language-level revisions, but substantive scholarly judgement remains with the researcher.
