from __future__ import annotations
import json
import re
from typing import Any
from llm_tools import configured_provider

SYSTEM_RULES = """
You are a research-literature synthesist. Return JSON only.
Never invent citations, page numbers, quotations, findings, methods, arguments, or gaps.
Every substantive claim must cite one or more supplied source_ids. Use pages only when those exact pages occur in the supplied evidence.
Separate source-reported evidence (A), strong interpretation (B), cross-source synthesis (C), analytical possibility (D), and speculation (E).
Do not manufacture disagreement or consensus. If the evidence is insufficient, say so.
For relational gaps, use D and explicitly say that broader literature verification is required.
"""

def _json(text: str) -> dict[str, Any]:
    match=re.search(r"\{.*\}",text,re.S)
    if not match: raise ValueError("LLM response did not contain a JSON object.")
    return json.loads(match.group(0))

def structured_synthesis(sources: list[dict[str,Any]]) -> dict[str,Any]:
    provider=configured_provider()
    if provider is None:
        raise RuntimeError("LLM_API_KEY is not configured.")
    payload=json.dumps(sources,ensure_ascii=False)
    prompt=SYSTEM_RULES+"""
Create a literature-review synthesis from the supplied source records.
Return:
{"prose": "...", "claims":[{"claim":"","evidence_level":"A|B|C|D|E","source_ids":[],"pages":[],"snippets":[],"confidence":"high|medium|low","status":"supported|uncertain","notes":""}], "decision_required": null or {"question":"","evidence":[],"possible_interpretations":[],"why_it_matters":""}}
Write connected prose using claim -> evidence -> reasoning -> qualification -> connection -> next claim.
Do not force the four configured literature sections. Cross-cutting sources are allowed.
"""+"\nSOURCE RECORDS:\n"+payload
    return _json(provider.complete(prompt,temperature=0.1))
