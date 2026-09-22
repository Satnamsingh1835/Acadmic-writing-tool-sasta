# Academic Literature Review Assistant

A researcher-controlled academic writing assistant for literature reviews, research proposals, dissertations, and PhD application writing.

The project combines a deterministic Python review engine with an R researcher workflow. It improves clarity, academic language, and literature-review reasoning without replacing the researcher's substantive judgement.

## What it does

- identifies formulaic academic phrasing and selected wordiness;
- flags long or repetitive sentences;
- identifies selected categorical claims that may need evidentiary checking;
- recognises common author-year and parenthetical citation patterns;
- provides paragraph-level literature-review prompts;
- identifies possible relationships between studies: agreement, extension, contrast, qualification, and temporal change;
- surfaces possible gaps and connections to the researcher's study;
- produces a conservative refined version;
- returns sentence-level suggestions with explanations;
- keeps suggestions under researcher control through pending / accept / modify / reject decisions.

Diagnostics are heuristic editorial prompts. They are not a scholarly-quality score and do not prove that a paragraph is missing an argument.

## Researcher control

The engine does not silently apply substantive revisions. The researcher can accept a proposed revision, modify it in their own words, reject it, or leave it pending.

The tool does not invent citations, evidence, literature, findings, interpretations, or theoretical arguments.

## Architecture

R researcher workflow -> HTTP client -> FastAPI -> AcademicWritingEngine -> language editor + literature-review diagnostics + argument diagnostics -> researcher decisions

The Python layer contains the domain logic. The R layer is the researcher-facing workflow.

### Python modules

- humanize.py — conservative language editing and safeguards
- advanced_humanize.py — editing profiles
- academic_analyser.py — sentence-level grammar/style/citation signals
- academic_suggestions.py — explainable sentence-level suggestions
- literature_review.py — literature-review diagnostics
- argument_diagnostics.py — paragraph-level argument prompts
- researcher_decisions.py — researcher-controlled decision logic
- academic_engine.py — orchestration layer
- api.py — HTTP interface for R and other clients
- copilot_auto_refiner.py — optional experimental automation; not part of the core researcher workflow

### R modules

- R/academic_review.R — call the review API and retrieve suggestions
- R/researcher_decisions.R — accept, modify, reject, or keep suggestions pending
- R/workspace.R — create a standard academic project workspace
- R/academic_workflow.R — researcher-facing helpers for health checks, reports, and saving drafts

## Use it now from R

1. From the repository root, install Python dependencies with: python -m pip install -r requirements.txt
2. Start the API with: python -m uvicorn api:app --reload
3. In R/RStudio, install httr2 once: install.packages("httr2")
4. Source the R helpers: source("R/academic_review.R"); source("R/researcher_decisions.R"); source("R/workspace.R"); source("R/academic_workflow.R")

Check the API:
academic_assistant_health()

Review text:
review <- academic_review("It is important to note that caste shapes land relations. Gupta (2000) identifies regional variation.", profile = "standard")
academic_print_review(review)

Review a file:
review <- academic_review_file("drafts/proposal.txt")
academic_print_review(review)

Save the deterministic refined text after inspecting safeguards:
academic_save_refined(review, "feedback/proposal_refined.txt")

Inspect suggestions:
suggestions <- academic_suggestions(review)
suggestions

Accept, modify, or reject a suggestion:
decision <- academic_decision(suggestions[[1]], decision = "accept")
academic_apply_decision(suggestions[[1]]$original, suggestions[[1]], decision)

For your own revision, use decision = "modify" and provide revised_text. A rejected or pending suggestion preserves the original.

## Editing profiles

- conservative — formulaic-phrase removal and British spelling
- standard — conservative editing plus selected wordiness reduction
- polish — standard editing plus limited claim softening

Aliases are also supported by the Python engine: light, medium, and heavy.

## API

The service exposes GET /health, POST /review, and POST /review/file. Interactive documentation is available at /docs while the API is running.

The API accepts pasted text and UTF-8 .txt uploads. Uploads are size-limited.

## Standard workspace

Create a new writing workspace with academic_workspace_create("my-project"). It creates drafts/, literature/, notes/, citations/, and feedback/.

## Testing

Python: run pytest from the repository root.
R: install testthat once with install.packages("testthat"), then run Rscript -e 'source("tests/testthat.R")' or testthat::test_dir("tests/testthat") in R.

The R GitHub Actions workflow installs the system libraries needed by the R HTTP/testing dependencies, then parses the R source files and runs the standalone testthat suite on pushes and pull requests to main.

## PhD-admission writing target

The project supports clearer, more precise, evidence-conscious academic prose suitable for serious PhD proposal development. It does not certify that a text is PhD level. Scholarly quality depends on the research question, engagement with literature, theoretical reasoning, evidence, originality, feasibility, and disciplinary expectations.

## What it is not

- not an AI detector or AI-detector bypass;
- not a plagiarism checker;
- not a citation generator;
- not a source verifier;
- not an automatic scholarly-quality scorer;
- not a system that fabricates literature-review arguments.

The researcher remains responsible for checking every substantive claim, citation, interpretation, conceptual distinction, and final revision.

## Roadmap

The repository is being developed through a controlled P1–P100 maintenance and research-engineering queue.

Current completed foundation work includes the hybrid Python + R architecture, researcher-controlled decisions, deterministic review orchestration, Python tests, and an R test workflow. The next phases focus on shared parsing, citation safeguards, literature-review diagnostics, evaluation, integrations, and safety.

Planned capabilities include:
- stronger shared parsing for paragraphs, sentences, citations, quotations, and headings;
- expanded multilingual and citation/footnote safeguards;
- stronger R/API integration testing;
- benchmark and regression evaluation;
- optional LLM assistance kept separate from the deterministic engine.