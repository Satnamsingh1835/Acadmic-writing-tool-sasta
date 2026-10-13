# Behavioral specification: Grammarly Free, QuillBot Free and ScholarFlow

**Status: template only. No live competitor observations are recorded here.**

Evidence classes:
- **Directly observed:** performed and recorded in the live public UI.
- **Publicly documented:** supported by current official help/documentation.
- **Inferred:** plausible interpretation, not directly confirmed.
- **Not tested:** not accessible or not run.

| Product / feature | Action and output | Controls and limits | Preservation checks | Evidence class | ScholarFlow implication | Uncertainty |
|---|---|---|---|---|---|---|
| Grammarly Free — correctness | Record synthetic input, visible suggestion category, replacement and explanation. | Record accept/dismiss/undo only if visible. | Citation, quotation, name, number, disciplinary term. | Not tested | Conservative rules plus researcher acceptance. | Do not assume all categories are Free. |
| QuillBot Free — paraphrase | Use identical synthetic text for each currently accessible free mode. | Record real word limit and controls. | Meaning, qualifiers, citations, quote, number, paragraphs. | Not tested | Side-by-side original/proposal and explicit acceptance. | Fluency is not proof of scholarly fidelity. |
| ScholarFlow — suggestion workflow | Internal product requirement, not a competitor claim. | Accept, reject, accept all, undo and history. | Preserve original text and protected spans. | Product decision | Stable IDs and auditable decisions. | Must be tested end to end. |
| ScholarFlow — evidence support | Search only passages indexed locally. | Source, page if reliably extracted, access status, limitations. | A match is a candidate passage, not proof of claim support. | Product decision | Show insufficient-evidence warning and source provenance. | Local results cannot prove a literature-wide absence. |

Add dated actions, official URLs and sanitized evidence references only after an actual investigation. Do not fill in guessed behavior.
