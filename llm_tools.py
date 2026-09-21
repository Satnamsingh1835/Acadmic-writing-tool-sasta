"""Optional, provider-neutral LLM adapter. Deterministic review remains the default."""
from __future__ import annotations
import os
from typing import Dict

class LLMProvider:
    name = "base"
    def complete(self, prompt: str, **kwargs) -> str:
        raise NotImplementedError

class OpenAICompatibleProvider(LLMProvider):
    name = "openai-compatible"
    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url, self.api_key, self.model = base_url.rstrip("/"), api_key, model
    def complete(self, prompt: str, **kwargs) -> str:
        import httpx
        response = httpx.post(f"{self.base_url}/chat/completions", headers={"Authorization": f"Bearer {self.api_key}"}, json={"model": self.model, "messages":[{"role":"user","content":prompt}], "temperature": kwargs.get("temperature", 0.2)}, timeout=kwargs.get("timeout", 60))
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

def configured_provider() -> LLMProvider | None:
    key = os.getenv("LLM_API_KEY")
    if not key: return None
    return OpenAICompatibleProvider(os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"), key, os.getenv("LLM_MODEL", "gpt-4o-mini"))

def research_prompt(tool: str, text: str) -> str:
    tools: Dict[str, str] = {"academic_improvement":"Improve clarity, precision, hedging, and academic style without adding claims or citations.", "literature_synthesis":"Identify relationships, agreements, contrasts, gaps, and evidence limits among the sources.", "research_questions":"Suggest questions that the writer should answer; do not invent findings or references."}
    if tool not in tools: raise ValueError(f"Unknown research tool: {tool}")
    return f"{tools[tool]} Return suggestions for manual review.\n\nTEXT:\n{text}"
