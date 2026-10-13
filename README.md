# Research Synthesist — Caste, Land, Commons & Social Boycott

A researcher-controlled literature-synthesis agent integrated with the repository's existing academic-writing system. It is designed for sociology, anthropology, political economy, agrarian studies, caste studies, commons studies, Dalit studies and rural studies.

## Purpose

The system turns a corpus into an evidence-weighted map of arguments, concepts, mechanisms, evidence, disagreements, historical change, limitations, gaps and researchable questions. It is not a paper summariser: cross-source relationships are a first-class output.

The configured research architecture covers:

1. LAND AND CASTE RELATIONS IN INDIA
2. COMMONS AND CASTE
3. CONCEPTUALISING SOCIAL BOYCOTT
4. LAND STRUGGLES IN PUNJAB

A source can belong to multiple clusters. Classification is descriptive, not a forced taxonomy.

## Evidence discipline

Every important synthesis claim uses one of five levels:

- **A — DIRECT EVIDENCE:** explicitly stated or directly demonstrated by a source.
- **B — STRONG INTERPRETATION:** a close interpretation strongly supported by source evidence.
- **C — CROSS-SOURCE SYNTHESIS:** an insight produced by comparing sources.
- **D — ANALYTICAL POSSIBILITY:** plausible but requiring investigation.
- **E — SPECULATION:** insufficiently supported.

Academic prose generated from the corpus should normally use A–C. D–E remain explicitly labelled.

The system never fabricates pages, quotations, citations, findings, theoretical positions or consensus. Page numbers are accepted only when present in PDF page markers or supplied source records.

## Architecture

```
PDF / TXT / Markdown
        |
        v
page-aware parsing
        |
        v
SourceRecord[]
        |
        +--> literature matrix
        +--> concept dictionary
        +--> debate map
        +--> historical map
        +--> gap analysis
        +--> research questions
        +--> citation / argument audits
        |
        v
optional provenance-constrained LLM synthesis
        |
        v
validation + DECISION REQUIRED
```

The new `agent/` package is deliberately separate from the existing `academic_engine.py`, `humanize.py`, `literature_review.py`, researcher-decision layer and R workflow. Existing language editing is reused rather than replaced.

## Installation

Core system:

```bash
python -m pip install -r requirements.txt
```

PDF extraction:

```bash
python -m pip install -r requirements-research.txt
```

Optional model-assisted synthesis requires the existing LLM environment variables in `.env.example`:

```
LLM_API_KEY=
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

## ScholarFlow web editor

The repository includes a browser-based academic editor with side-by-side
revision, three editing profiles, sentence-level suggestions, literature-review
structure diagnostics, citation safeguards, revision-receipt export, text upload,
copy and download. The deterministic local editor is the default.

Start it with:

```bash
uvicorn api:app --reload
```

Then open `http://127.0.0.1:8000`. API documentation remains available at
`/docs`.

Optional model-assisted rewriting is enabled only when `LLM_API_KEY` is set.
When the **AI enhance** switch is off, no passage is sent to an external model.
When it is on, model output is rejected if it removes, changes, or introduces
citation markers; provider failures fall back to the local revision.

The editor endpoint is also available directly:

```bash
curl -X POST http://127.0.0.1:8000/editor/rewrite \
  -H 'Content-Type: application/json' \
  -d '{"text":"Your academic passage.","profile":"standard","use_llm":false}'
```

## Research-synthesis CLI

Analyse one source:

```bash
python -m agent.cli source literature/paper.pdf --id S1 -o outputs/S1.json
```

Build the comparative matrix:

```bash
python -m agent.cli matrix literature/*.pdf --format csv -o outputs/matrix.csv
```

Available workflows:

```bash
python -m agent.cli debate-map literature/*.pdf
python -m agent.cli concept-map literature/*.pdf
python -m agent.cli historical-synthesis literature/*.pdf
python -m agent.cli gap-analysis literature/*.pdf
python -m agent.cli research-questions literature/*.pdf
python -m agent.cli audit literature/*.pdf --text drafts/review.txt
python -m agent.cli citation-audit literature/*.pdf --text drafts/review.txt
python -m agent.cli paragraph-audit --paragraph "Your paragraph here"
python -m agent.cli human-edit drafts/review.txt --profile standard
python -m agent.cli suggest drafts/review.txt --profile standard
```

For connected academic prose, configure `LLM_API_KEY` and run:

```bash
python -m agent.cli synthesize literature/*.pdf -o outputs/literature_synthesis.json
```

The model receives only structured source records and their provenance. Its output is then validated. The deterministic pipeline remains usable without a model.

## Source record

The schema tracks author, year, title, publication, discipline, geography, historical period, research question/problem, main and secondary arguments, concepts and definitions, theoretical framework, methodology/methods/data, case, evidence, mechanisms, actors, institutions, causal and historical claims, counterarguments, limitations, findings, contribution, explicit/implicit gaps, quotations, keywords, literature sections, relevance and uncertainty.

Plain-text extraction is conservative and intentionally leaves many fields unknown. Researchers can enrich the JSON record before synthesis.

## Commons analysis

Commons are decomposed into resource, institution, property regime, access, use, governance, rules, authority, boundaries, exclusion, commoning, social relations, power, caste, gender, class, state and market.

The system does not assume that a commons is egalitarian, that community is homogeneous, or that collective ownership implies equal access.

## Social boycott analysis

The configured dimensions distinguish economic, labour and market exclusion; water, land and common-space access; social interaction; marriage; ritual and religious participation; village institutions; mobility; services; credit; everyday dignity; collective punishment; informal/formal enforcement; and state response.

Legal definition, sociological definition, empirical practice and institutional mechanism must remain distinct.

## Punjab evidence map

The configuration tracks shamlat and panchayat land, redistribution, leasing, auction and dummy-bidding practices, Dalit mobilisation, dominant-caste resistance, village institutions, police, administration, courts, boycott, labour relations and agrarian movements. These are evidence categories, not predetermined causal relationships.

## Research-gap method

A gap is not accepted merely because a source says that more research is needed.

The gap engine distinguishes empirical, conceptual, theoretical, methodological, geographical, historical, institutional, relational, process and scale gaps. Relational gaps are deliberately conservative: the system labels them analytical possibilities and asks for broader literature verification.

## Human-in-the-loop

Major interpretation choices must be surfaced as:

```
DECISION REQUIRED
Question:
Evidence:
Possible interpretations:
Why it matters:
```

The agent does not silently choose between materially different interpretations.

## Exports

Literature matrices support JSON, CSV, Markdown and SQLite. Source records and synthesis claims are JSON-serialisable. Generated outputs belong in `outputs/`.

## Directory structure

```
agent/                 core extraction, synthesis, validation and CLI
config/                editable research configuration
prompts/               extraction and synthesis instructions
schemas/               machine-readable record schemas
workflows/             thin command wrappers
data/                  researcher-owned source-data area
outputs/               generated research artefacts
tests/                 regression and quality-control tests
docs/                   architecture and workflow documentation
```

## Testing

Install test tooling and run:

```bash
python -m pip install -r requirements-dev.txt
pytest -q
python -m compileall -q .
python -m tools.repository_check
```

The repository checker validates each source file individually: Python is
compiled, JSON and YAML are parsed, and remaining tracked text files are checked
for UTF-8 readability. R behavioural tests still require an R installation.

CI also runs the existing R suite and Python suite. The new tests cover provenance, duplicate-source detection, invalid pages, citation mismatch, overclaiming, concept variation, relational-gap labelling and configuration loading.

## What it does not do

It does not certify truth, replace scholarly judgement, invent literature, create unsupported research gaps, decide whether a debate exists, or silently rewrite substantive arguments.

Copyrighted papers should not be committed to the repository without permission.

## Git workflow

Work is developed on the `research-synthesist` branch. Review the diff and CI results before merging to `main`. No automatic push or merge is performed by the agent.

## Researcher-facing principle

**Make the literature's reasoning visible, preserve provenance, connect sources carefully, and leave substantive interpretation with the researcher.**


## Local research library

Open `http://127.0.0.1:8000/library` after starting the app. The local catalogue stores normalized records and locally indexed document passages in SQLite under the user's application-data directory (or `SCHOLARFLOW_DATA_DIR`). It supports CSL JSON import, read-only Zotero import, local document indexing, Crossref/OpenAlex metadata discovery, passage search, an evidence-brief endpoint, and a candidate literature matrix.

Install optional document extractors with:

```powershell
python -m pip install -r requirements-research.txt
```

PDF/DOCX extraction needs the optional dependencies. OCR for image-only scans is not bundled. A record returned by Crossref/OpenAlex is metadata, not proof it supports a claim. Zotero import is read-only. Private Web API imports require `ZOTERO_USER_ID` and `ZOTERO_API_KEY` in the local environment; never commit credentials.

## Windows desktop package

Build the native pywebview one-folder distribution on Windows 11 with Python 3.12 and Microsoft Edge WebView2 Runtime:

```powershell
.\scripts\build_windows_desktop.ps1
```

The output is `dist\ScholarFlow\ScholarFlow.exe`. The app starts the existing FastAPI backend on loopback and stops it when its window closes. The GitHub Actions workflow builds an artifact on Windows, but the target PC still requires a manual launch/close test. See [Windows desktop and REA runbook](docs/REA_WINDOWS_RUNBOOK.md).

## REA readiness and behavioral study

Read [REA provenance](docs/REA_PIN.md) and the [Windows runbook](docs/REA_WINDOWS_RUNBOOK.md). The readiness script is dry-run by default:

```powershell
.\scripts\rea-readiness.ps1
```

Actual Grammarly Free / QuillBot Free observations must be performed in a supported local coding-agent/browser environment using synthetic text from `docs/rea-study/fixtures.md`. The observation templates explicitly remain NOT TESTED until actual evidence is recorded.
