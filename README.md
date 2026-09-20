# Academic Humanizer

A conservative, rule-based Python tool for revising AI-like academic prose into clearer academic writing.

## Principles

- Preserve the author's argument and argumentative order.
- Do not invent evidence, claims, opinions, or citations.
- Do not add filler words, emojis, rhetorical questions, or fake personal voice.
- Protect URLs, DOI strings, parenthetical citations, and quoted text.
- Prefer precise and economical academic English.
- Use deterministic transformations.

## Files

- humanize.py: conservative academic editor.
- advanced_humanize.py: conservative, standard, and polish profiles.
- test_academic_humanizer.py: regression tests.

## Usage

Run `python humanize.py`, `python advanced_humanize.py`, or `python -m unittest test_academic_humanizer.py`.

The advanced editor accepts conservative, standard, and polish. Legacy light, medium, and heavy names remain supported.

## Roadmap

Next: paragraph-level argument analysis, overclaim flags, repetitive sentence-opening detection, claim-evidence-explanation analysis, citation validation, domain-aware vocabulary, and British academic English.

## Responsible use

The writer remains responsible for the argument, evidence, citations, interpretation, and final wording. The tool supports revision; it does not substitute for authorship or source checking.
