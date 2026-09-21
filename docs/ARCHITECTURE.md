# Academic Writing Assistant Architecture

The project uses a small hybrid architecture rather than forcing every task into one language.

## Design

```
R research workflow
      |
      v
academic_review.R
      |
      | HTTP
      v
Python academic engine
      |
      +--> AcademicAnalyzer
      +--> AcademicSuggestionEngine
      +--> AdvancedHumanizer
      +--> LiteratureReviewAnalyzer
      |
      v
structured review result
```

R is the researcher-facing layer. Python is used where the existing text-analysis and API implementation is strongest.

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
