# Academic Writing Assistant Architecture

The project uses a small hybrid architecture rather than forcing every task into one language.

## Design

```
ScholarFlow web editor       R research workflow
          |                         |
          | JSON / HTTP             v
          +-----------------> academic_review.R
          |                         |
          +------------+------------+
                       |
                       v
              FastAPI application
                       |
                       v
              AcademicEditorService
                       |
          +------------+-------------------+
          |            |                   |
          v            v                   v
  AcademicAnalyzer  AdvancedHumanizer  LiteratureReviewAnalyzer
          |            |                   |
          +------------+-------------------+
                       |
                       v
            structured review result
                       |
             optional safeguarded LLM
```

The browser and R workflows are researcher-facing layers. Python provides the
text-analysis, orchestration, API, and optional provider integration. The web
surface contains no editing logic; it renders structured results from the
application service.

## Web editor and optional model use

`AcademicEditorService` always runs the deterministic engine first. If model
enhancement is requested and configured, the local draft is sent through the
provider-neutral adapter. Empty responses, excessive expansion, provider
errors, and citation changes are rejected, so a valid local result is always
available as the fallback. Credentials remain server-side.

## Core principle

The system should **support the researcher's judgement rather than replace it**.

The literature-review workflow is:

```
source / evidence
       |
       v
interpretation
       |
       v
comparison / synthesis
       |
       v
gap
       |
       v
connection to research question
```

These are editorial diagnostics, not claims that a passage has achieved a particular scholarly quality.

## Workspace

The R layer can create:

- `drafts/`
- `literature/`
- `notes/`
- `citations/`
- `feedback/`

The workspace is deliberately simple. Future document integrations can be added without putting storage logic into the analysis modules.

## Why hybrid?

A language should not be selected for ideological reasons. R is valuable for research workflows, reproducible analysis and integration with the user's academic environment. Python already provides the mature text-analysis and API components in this repository.

The architecture therefore keeps the specialist analysis modules independent of the user interface. If a future R-native implementation becomes preferable, individual components can be replaced without redesigning the whole system.

## Octop-inspired principles

The architecture takes inspiration from the public TencentCloud Octop project:

- separate interface/surface code from domain logic;
- keep specialist capabilities modular;
- use an orchestration layer instead of putting all logic into one entry point;
- keep components independently testable;
- maintain a persistent project/workspace concept.

This repository does **not** copy Octop's general-purpose assistant implementation. It adapts these architectural principles to academic writing.

## Researcher decision layer

Every generated revision is treated as a proposal. The API exposes a stable
`suggestion_id` and a `decision` state (`pending`, `accept`, `modify`, or
`reject`). A researcher can inspect the original, accept the proposal, modify
it in their own words, or reject it and preserve the original.

The system does not silently apply these decisions. Researcher judgement is an
explicit part of the workflow.
