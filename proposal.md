# Project Proposal: Academic Literature Review Assistant

## Purpose

The repository is being redesigned from a generic humanisation utility into a
research-writing assistant focused on literature reviews. The central use case
is a researcher working with a proposal or PhD application who wants to read
their own draft, identify language problems, understand paragraph-level
literature-review structure, and refine the prose without outsourcing the
researcher's intellectual work.

## Research-writing problem

Literature-review drafts often combine several different tasks in the same
paragraph: reporting what a source says, interpreting its significance,
comparing it with other studies, identifying an unresolved issue, and connecting
that issue to the proposed research. Grammar correction alone cannot identify
these transitions.

The project therefore separates two layers:

1. language editing; and
2. literature-review reasoning prompts.

This separation is important because a tool should not silently turn a grammar
editor into an argument generator.

## Intended workflow

The intended workflow is:

1. Read the writer's text file.
2. Identify sentence-level grammar and academic-language issues.
3. Identify source/evidence, interpretation, synthesis, gap, and study-connection
   signals.
4. Show possible missing relationships as questions.
5. Produce a conservative refined text.
6. Compare the refined text with the original.
7. Manually verify citations, evidence, concepts, interpretations, and claims.
8. Revise the researcher's argument separately where necessary.

## PhD proposal target

The project uses "PhD-admission level" as a writing-development target rather
than a quality score. The assistant should encourage prose that is precise,
analytical, evidence-conscious, and appropriately qualified.

It must not claim that a proposal is ready for admission merely because the
language has been polished. Scholarly quality also depends on originality,
research design, theoretical engagement, literature coverage, evidence, and
feasibility.

## API design

The first API supports:

- GET /health
- POST /review for pasted text
- POST /review/file for UTF-8 text files

The review response separates:

- refined_text;
- grammar_and_style;
- literature_review;
- safeguards.

The HTTP layer is deliberately simple so it can be called from R, Python, or
other research workflows.

## R use case

The intended R workflow is:

R reads a proposal text file
-> sends text to the local API
-> receives diagnostics and refined text
-> saves the revised draft
-> researcher reviews the changes.

A later R helper package can wrap these calls, but the HTTP API should remain
the stable interface.

## Future development

### Phase 1: API stability

Add tests for API validation, file upload, profiles, empty files, and response
schemas.

### Phase 2: Better language feedback

Return explicit sentence-level suggestions:

- original sentence;
- issue type;
- reason for the suggestion;
- suggested revision;
- confidence/uncertainty.

The system should distinguish grammar, clarity, concision, and academic-style
suggestions rather than calling every stylistic preference a grammar error.

### Phase 3: Better literature-review assistance

Develop diagnostics for:

- source reporting versus interpretation;
- comparison across authors;
- theoretical disagreement;
- empirical versus conceptual claims;
- temporal change;
- geographical variation;
- gap statements;
- connection between the literature gap and research questions.

The system should ask the writer to supply missing reasoning rather than
fabricating it.

### Phase 4: Document support

Add DOCX and PDF extraction with tests for headings, footnotes, references,
quotations, and page structure.

### Phase 5: Optional model-assisted refinement

An optional LLM endpoint may later provide deeper sentence and paragraph
revision. It must be clearly separated from deterministic safeguards and must
never silently invent sources or citations.

## Non-goals

The project is not intended to:

- detect AI-generated text;
- bypass AI detectors;
- measure how "human" a passage sounds;
- generate fake citations;
- fabricate literature;
- replace the researcher's interpretation;
- certify PhD admission quality.

## Success criteria

The project will be considered successful when a researcher can take a draft
literature review, receive useful and explainable language suggestions, see
where the paragraph's reasoning may be incomplete, obtain a conservative
refined version, and continue the intellectual revision themselves.

The core principle is:

**Improve the writing and make the reasoning visible; do not replace the
researcher.**
