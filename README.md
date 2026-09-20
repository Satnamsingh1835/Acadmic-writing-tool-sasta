# Academic Humanizer

A conservative, rule-based Python tool for revising AI-like academic prose into clearer academic writing and diagnosing paragraph structure.

## Principles

- Preserve the author's argument and argumentative order.
- Do not invent evidence, claims, opinions, or citations.
- Do not add filler words, emojis, rhetorical questions, or fake personal voice.
- Protect URLs, DOI strings, parenthetical citations, and quoted text.
- Prefer precise and economical academic English.
- Use deterministic transformations.
- Treat paragraph analysis as heuristic diagnostics, not automated interpretation of the author's argument.

## Files

- humanize.py: conservative academic editor.
- advanced_humanize.py: conservative, standard, and polish profiles.
- academic_analyser.py: diagnostic analysis of prose and paragraph reasoning.
- test_academic_humanizer.py: regression tests.

## Paragraph analysis

AcademicAnalyzer does not rewrite text. It flags patterns for human review, including:

- formulaic academic/AI phrasing
- possible absolute or overconfident claims
- repeated sentence openings
- long sentences
- argument and transition signals
- citation count
- a heuristic paragraph structure: claim_or_context -> evidence -> explanation -> link

The claim/evidence/explanation/link detection is intentionally conservative. A sentence with a citation is treated as possible evidence, while phrases such as 'this suggests' or 'this indicates' are treated as possible explanation. These are prompts for revision, not claims that the software has understood the argument.

## Roadmap

- citation validation
- domain-aware vocabulary
- British academic English
- stronger claim-evidence-explanation diagnostics
- paragraph coherence checks
- optional analysis reports for a full proposal

## Responsible use

The writer remains responsible for the argument, evidence, citations, interpretation, and final wording. The tool supports revision; it does not substitute for authorship or source checking.