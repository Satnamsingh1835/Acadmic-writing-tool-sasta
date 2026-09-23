# Research Synthesist architecture
Existing academic_engine.py remains the language-review orchestrator. The new agent package is a modular research-analysis layer: parsing → extraction → structured records → synthesis → validation → exports. It does not replace the existing humanization modules.

PDF/TXT/MD → page-aware parser → SourceRecord[] → matrix/concepts/debates/history → gap engine → research questions → audits.

The deterministic layer is dependency-light. An LLM can later be added behind the structured interfaces, but model output must pass validation and preserve provenance.
