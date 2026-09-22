# Engineering Inventory — P6–P10

Date: 2026-09-22

## P6 — Python dependency audit

Runtime dependencies are intentionally small:
- FastAPI for the HTTP API.
- Uvicorn for serving the API.
- python-multipart for file uploads.
- httpx for HTTP/API testing and the optional OpenAI-compatible LLM adapter.

The deterministic analytical engine does not require an external model.

## P7 — R dependency audit

The R researcher interface currently requires httr2 for HTTP requests and testthat for the R test suite.
The R layer is intentionally thin: it sends research text to the Python API and handles researcher-facing decisions and workspace operations.

## P8 — Canonical architecture

R researcher workflow → HTTP API → Python analytical engine → structured diagnostics → researcher decision.
Python is the authoritative analytical implementation. R-native analytical code should not silently become a second source of analytical truth.

## P9 — Module ownership

| Area | Owner |
|---|---|
| API transport and validation | api.py |
| Workflow orchestration | academic_engine.py |
| Sentence/citation/text parsing | text_parser.py |
| Academic diagnostics | academic_analyser.py |
| Editorial suggestions | academic_suggestions.py |
| Literature-review structure | literature_review.py |
| Argument prompts | argument_diagnostics.py |
| Language-only refinement | humanize.py, advanced_humanize.py |
| Researcher decisions | researcher_decisions.py |
| R researcher interface | R/*.R |
| Optional LLM adapter | llm_tools.py |
| Optional Google Docs integration | google_docs.py |

The shared parser is the single source for sentence, paragraph, word, and author-year citation boundary logic.

## P10 — Regression strategy

The parser has regression coverage for academic abbreviations, et al., decimal numbers, quotations, paragraph boundaries, Unicode text, narrative author-year citations, parenthetical author-year citations, and duplicate citation suppression.

Existing engine and literature-review tests remain unchanged in this pass. Subsequent analytical refactors should add regression cases before changing signal semantics.

## Deferred boundary decisions

- The R-native AcademicAnalyzer should be reviewed in P69 before removal or further expansion.
- The optional LLM adapter remains outside the deterministic review path.
- Google Docs remains optional and is not required for core tests.