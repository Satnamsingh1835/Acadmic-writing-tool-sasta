# Academic Literature Review Assistant

This project is now an **academic literature-review writing assistant**, not an AI detector or AI-detector bypass.

It is designed for a researcher who is reading and drafting a literature review for a research proposal, dissertation, or PhD application. The system reads the writer's text, identifies possible grammar and academic-language problems, diagnoses paragraph-level literature-review structure, and produces a conservative refined version.

## What the assistant does

### Read your text

The API currently accepts UTF-8 .txt files and pasted text. It preserves paragraph and sentence order.

### Grammar and academic-language review

It flags or edits:

- formulaic academic phrasing;
- selected wordiness;
- long sentences;
- repeated sentence openings;
- selected categorical claims that deserve evidentiary checking;
- British academic spelling;
- possible source-based claims without a nearby citation.

These are editorial signals, not automatic declarations that a sentence is wrong.

### Literature-review reasoning

The analyser looks for the following possible functions:

**source/evidence -> interpretation -> comparison/synthesis -> gap -> connection to the study**

This is not a rigid template. A paragraph does not need every function in every case. Missing signals produce questions for the researcher rather than invented prose.

It also looks for relationships between sources, including:

- agreement or extension;
- contrast or tension;
- qualification or conditionality;
- temporal reconfiguration;
- explicit debate language.

### Conservative text refinement

The editor can:

- remove formulaic phrasing;
- simplify selected wordiness;
- use British English spelling;
- optionally soften a small set of categorical expressions.

It does not invent citations, evidence, literature, interpretations, research findings, or theoretical arguments.

## PhD-admission writing target

The project is intended to help produce **clearer, more precise, evidence-conscious academic prose suitable for serious PhD proposal development**.

It does not certify that a text is "PhD level". Admission quality depends on the substance of the research question, engagement with literature, theoretical reasoning, evidence, originality, feasibility, and disciplinary expectations. The tool therefore separates language refinement from scholarly judgement.

## API

Install dependencies:

    python -m pip install -r requirements.txt

Run the API:

    python -m uvicorn api:app --reload

The interactive API documentation is available from the running server at /docs.

### Health check

    GET /health

### Review pasted text

    POST /review

Example JSON:

    {
      "text": "Jodhka (2004) examines caste and land relations. However, Gupta (2000) identifies regional variation.",
      "profile": "standard",
      "include_refined_text": true
    }

### Review a text file

    POST /review/file

Upload a UTF-8 .txt file as multipart form data.

Profiles:

- conservative — formulaic-phrase removal and British spelling;
- standard — conservative editing plus selected wordiness reduction;
- polish — standard editing plus limited claim softening.

The response contains:

- refined_text;
- suggestions — sentence-level issue, explanation, suggested revision, and confidence;
- grammar_and_style;
- literature_review;
- safeguards.

## Using it from R

The API is intentionally HTTP-based so that an R workflow can call the same service.

Example with httr2:

    library(httr2)

    text <- paste(readLines("proposal.txt", encoding = "UTF-8"), collapse = "\n")

    result <- request("http://127.0.0.1:8000/review") |>
      req_method("POST") |>
      req_body_json(list(
        text = text,
        profile = "standard",
        include_refined_text = TRUE
      )) |>
      req_perform() |>
      resp_body_json()

    cat(result$refined_text)

For a file, use the /review/file endpoint with multipart upload.

## Project architecture

    text file / pasted text
            |
            v
       API layer
            |
      +-----+-----+
      |           |
      v           v
    language   literature-review
     editor       analyser
      |           |
      +-----+-----+
            |
            v
       review response
       / refined text

The current modules are:

- humanize.py — conservative language editing and structural safeguards
- advanced_humanize.py — editing profiles
- academic_analyser.py — sentence-level grammar/style/citation signals
- academic_suggestions.py — explainable sentence-level suggestions
- literature_review.py — paragraph-level literature-review diagnostics
- api.py — HTTP API for R and other clients
- test_api.py — API regression tests
- test_academic_humanizer.py — core regression tests
- test_literature_review.py — literature-review regression tests
- proposal.md — project design and roadmap

## What it is not

This is not:

- an AI detector;
- an AI-detector bypass;
- a plagiarism checker;
- a citation generator;
- a source verifier;
- an automatic scholarly-quality scorer;
- a system that fabricates literature-review arguments.

The writer remains responsible for checking every substantive claim, citation, interpretation, conceptual distinction, and final revision.

## Roadmap

1. Stabilise the API and regression tests. ✓
2. Return explicit sentence-level grammar/style suggestions with before/after explanations. ✓
3. Add paragraph-level revision prompts tied to the writer's own argument.
4. Add DOCX and PDF text extraction.
5. Add an optional LLM-assisted refinement endpoint, clearly separated from deterministic editing.
6. Add a small R client package/functions.
7. Expand tests for citations, quotations, footnotes, headings, and multilingual text.
