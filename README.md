# Academic Humanizer

A conservative Python tool for revising AI-assisted academic prose, with a specific workflow for literature reviews.

## What it does

- removes generic AI-style framing without rewriting the argument
- reduces safe forms of wordiness
- preserves paragraph boundaries
- protects URLs, DOIs, parenthetical citations and quotations
- optionally softens a small set of categorical claims
- supports British academic English
- never adds fillers, emojis, fake personal opinions or rhetorical questions
- never randomly reorders sentences
- does not invent evidence, citations or interpretations

## Literature-review workflow

The intended workflow is:

1. Draft the paragraph yourself.
2. Run the conservative profile first.
3. Compare the output with your original.
4. Use standard only when the prose is unnecessarily formulaic or wordy.
5. Use polish only for a final language pass.
6. Manually check every citation, conceptual term and substantive claim.

The tool is a writing aid, not an authorship or source-checking system.

## Python usage

Basic:

```python
from humanize import HumanizeAI

editor = HumanizeAI()
result = editor.humanize_literature_review(text)
print(result)
```

Profiles:

```python
from advanced_humanize import AdvancedHumanizer

editor = AdvancedHumanizer()

conservative = editor.humanize_literature_review(text, "conservative")
standard = editor.humanize_literature_review(text, "standard")
polish = editor.humanize_literature_review(text, "polish")
```

The older names `light`, `medium`, and `heavy` are still accepted as aliases.

## What it deliberately does not do

This project does not try to make academic prose artificially conversational or to bypass AI-detection systems. Its purpose is to help an author remove formulaic language while retaining the author's argument, evidence, concepts and scholarly register.

## Repository files

- `humanize.py` — core conservative academic editor.
- `advanced_humanize.py` — literature-review profiles.
- `academic_analyser.py` — diagnostic checks for formulaic language, possible overclaims, repeated openings, long sentences, citations and paragraph structure.
- `test_academic_humanizer.py` — regression tests.

## Example for a literature review

Input:

> It is important to note that caste plays a crucial role in shaping agrarian relations. Furthermore, the relationship is multifaceted due to the fact that land relations vary across regions.

The standard profile is intended to produce more direct academic prose while leaving the substantive argument for the author to verify.

## Responsible use

The writer remains responsible for the argument, evidence, citations, interpretation and final wording. Always compare the revised version with the original before using it in a proposal, dissertation or publication.
