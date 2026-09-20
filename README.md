# Academic Humanizer

A conservative Python toolkit for revising AI-assisted academic prose and diagnosing common literature-review structure signals. It is designed for authors who want language-level editing without outsourcing their argument.

## What it does

### Language editing

- removes generic AI-style framing
- reduces a small set of safe wordiness patterns
- optionally softens selected categorical claims
- supports British academic English
- preserves paragraph boundaries and sentence order
- protects URLs, DOIs, author-year citations and quoted text
- does not add evidence, citations, interpretations or substantive claims
- does not use fillers, emojis, rhetorical questions or random sentence reordering

### Literature-review diagnostics

- identifies likely sentence roles such as source/evidence, interpretation, synthesis, gap and author connection
- flags possible overclaims and long sentences
- detects common citation patterns and possible source claims without citations
- identifies explicit synthesis signals such as comparison, contrast, qualification and temporal reconfiguration
- flags possible multi-source listing when several studies appear without an explicit synthesis relationship
- provides neutral editorial questions rather than scholarly quality scores

These diagnostics are heuristic. They are prompts for the writer's review, not an assessment of whether an argument is theoretically or empirically correct.

## Recommended workflow

1. Draft the paragraph yourself.
2. Run the `conservative` profile first.
3. Compare the revised text with the original.
4. Use `standard` when the prose contains unnecessary wordiness.
5. Use `polish` only when you want the limited claim-softening pass.
6. Run the academic and literature-review analysers.
7. Manually verify every citation, conceptual term, substantive claim and interpretation.
8. Use `language_only_diagnostics()` to check paragraph, sentence and citation preservation.

## Python usage

### Humanize academic prose

```python
from humanize import HumanizeAI

editor = HumanizeAI()
revised = editor.humanize_literature_review(text)
print(revised)
```

### Use profiles

```python
from advanced_humanize import AdvancedHumanizer

editor = AdvancedHumanizer()

conservative = editor.humanize_literature_review(text, "conservative")
standard = editor.humanize_literature_review(text, "standard")
polish = editor.humanize_literature_review(text, "polish")
```

`light`, `medium`, and `heavy` remain accepted as backwards-compatible aliases.

### Analyse a literature review

```python
from literature_review import LiteratureReviewAnalyzer

analyzer = LiteratureReviewAnalyzer()
report = analyzer.analyse(text)
print(analyzer.summary(text))
```

### Check language-only safeguards

```python
from humanize import HumanizeAI

editor = HumanizeAI()
revised = editor.humanize_literature_review(text)
print(editor.language_only_diagnostics(text, revised))
```

## What it deliberately does not do

This project is not an AI-detector bypass, plagiarism tool, citation generator, source verifier or automatic scholarly-quality scorer. It does not determine whether an author's interpretation is correct. It only applies limited language transformations and reports heuristic signals for human review.

## Repository files

- `humanize.py` — core conservative academic editor and structural safeguards
- `advanced_humanize.py` — conservative, standard and polish profiles
- `academic_analyser.py` — sentence-level style, citation and literature-review signals
- `literature_review.py` — paragraph-level flow and synthesis diagnostics
- `test_academic_humanizer.py` — regression tests for the core editor and analyser
- `test_literature_review.py` — regression tests for paragraph-level diagnostics
- `test_example.py` — runnable demonstration

## Limitations

Regex- and heuristic-based checks can miss context, misclassify sentences, or recognise a rhetorical signal where no genuine synthesis exists. Structural safeguards cannot prove semantic preservation. The author must make the final judgement about wording, evidence, interpretation and argument.

## Responsible use

The writer remains responsible for the argument, evidence, citations, interpretation and final wording. Compare revised text with the original before using it in a proposal, dissertation or publication.