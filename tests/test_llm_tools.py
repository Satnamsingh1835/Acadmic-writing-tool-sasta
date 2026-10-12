import httpx
import pytest

from llm_tools import OpenAICompatibleProvider, configured_provider


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    response_payload = {"choices": [{"message": {"content": "Refined text."}}]}
    last_request = None

    def __init__(self, timeout):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def post(self, url, headers, json):
        type(self).last_request = {
            "url": url,
            "headers": headers,
            "json": json,
            "timeout": self.timeout,
        }
        return FakeResponse(type(self).response_payload)


def test_configured_provider_requires_nonempty_key(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "   ")

    assert configured_provider() is None


def test_configured_provider_uses_environment(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "secret")
    monkeypatch.setenv("LLM_BASE_URL", "https://provider.example/v1/")
    monkeypatch.setenv("LLM_MODEL", "academic-model")

    provider = configured_provider()

    assert provider is not None
    assert provider.base_url == "https://provider.example/v1"
    assert provider.model == "academic-model"


def test_openai_compatible_provider_builds_request(monkeypatch):
    monkeypatch.setattr(httpx, "Client", FakeClient)
    provider = OpenAICompatibleProvider(
        "https://provider.example/v1",
        "secret",
        "academic-model",
    )

    content = provider.complete(
        "Revise this.",
        system="Do not invent citations.",
        temperature=0.1,
        timeout=15,
    )

    assert content == "Refined text."
    request = FakeClient.last_request
    assert request["url"] == "https://provider.example/v1/chat/completions"
    assert request["headers"]["Authorization"] == "Bearer secret"
    assert request["json"]["messages"][0]["role"] == "system"
    assert request["json"]["temperature"] == 0.1
    assert request["timeout"] == 15


def test_openai_compatible_provider_rejects_invalid_payload(monkeypatch):
    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr(FakeClient, "response_payload", {"choices": []})
    provider = OpenAICompatibleProvider("https://provider.example/v1", "secret", "model")

    with pytest.raises(ValueError, match="invalid response"):
        provider.complete("Revise this.")
