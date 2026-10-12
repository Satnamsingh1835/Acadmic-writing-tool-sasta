"""Optional provider-neutral LLM adapter.

Deterministic review remains the default. Credentials are read from the
environment and are never returned by the API.
"""

from __future__ import annotations

import os
from typing import Any


class LLMProvider:
    name = "base"

    def complete(self, prompt: str, **kwargs: Any) -> str:
        raise NotImplementedError


class OpenAICompatibleProvider(LLMProvider):
    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def complete(self, prompt: str, **kwargs: Any) -> str:
        import httpx

        messages = []
        system = kwargs.get("system")
        if system:
            messages.append({"role": "system", "content": str(system)})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.2),
        }
        if kwargs.get("max_tokens") is not None:
            payload["max_tokens"] = kwargs["max_tokens"]

        with httpx.Client(timeout=kwargs.get("timeout", 60)) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            response.raise_for_status()

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("The LLM provider returned an invalid response.") from exc
        if not isinstance(content, str):
            raise ValueError("The LLM provider returned non-text content.")
        return content


def configured_provider() -> LLMProvider | None:
    """Build the configured provider, or return ``None`` when it is disabled."""
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not api_key:
        return None
    return OpenAICompatibleProvider(
        os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        api_key,
        os.getenv("LLM_MODEL", "gpt-4o-mini"),
    )


def research_prompt(tool: str, text: str) -> str:
    tools = {
        "academic_improvement": (
            "Improve clarity, precision, hedging, and academic style without "
            "adding claims or citations."
        ),
        "literature_synthesis": (
            "Identify relationships, agreements, contrasts, gaps, and evidence "
            "limits among the sources."
        ),
        "research_questions": (
            "Suggest questions that the writer should answer; do not invent "
            "findings or references."
        ),
    }
    if tool not in tools:
        raise ValueError(f"Unknown research tool: {tool}")
    return f"{tools[tool]} Return suggestions for manual review.\n\nTEXT:\n{text}"
