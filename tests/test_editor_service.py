from editor_service import AcademicEditorService
from llm_tools import LLMProvider


class FakeProvider(LLMProvider):
    name = "fake-provider"

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.prompts = []

    def complete(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        if self.error:
            raise self.error
        return self.response


def test_local_editor_returns_rewrite_and_diagnostics():
    service = AcademicEditorService(provider_factory=lambda: None)

    result = service.rewrite(
        "It is important to note that caste shapes access to land (Gupta, 2000).",
        profile="standard",
    )

    assert "important to note" not in result.refined_text.lower()
    assert result.provider == "deterministic-local"
    assert result.used_llm is False
    assert result.stats["original_words"] > 0
    assert result.safeguards["llm_citations_verified"] is True
    assert result.grammar_and_style["citation_count"] == 1
    assert result.receipt["receipt_id"].startswith("revision:")
    assert result.receipt["llm_requested"] is False


def test_llm_request_falls_back_when_provider_is_not_configured():
    service = AcademicEditorService(provider_factory=lambda: None)

    result = service.rewrite("Caste shapes access to land.", use_llm=True)

    assert result.used_llm is False
    assert result.provider == "deterministic-local"
    assert "no provider is configured" in result.notices[0]


def test_safe_llm_output_is_used():
    provider = FakeProvider(
        "Caste continues to shape access to land (Gupta, 2000)."
    )
    service = AcademicEditorService(provider_factory=lambda: provider)

    result = service.rewrite(
        "Caste shapes access to land (Gupta, 2000).",
        use_llm=True,
    )

    assert result.used_llm is True
    assert result.provider == "fake-provider"
    assert result.refined_text.startswith("Caste continues")
    assert provider.prompts
    assert provider.prompts[0][1]["temperature"] == 0.1


def test_llm_output_with_changed_citation_is_rejected():
    provider = FakeProvider(
        "Caste shapes access to land (Invented, 2025)."
    )
    service = AcademicEditorService(provider_factory=lambda: provider)

    result = service.rewrite(
        "Caste shapes access to land (Gupta, 2000).",
        use_llm=True,
    )

    assert result.used_llm is False
    assert "LLM output was rejected" in result.notices[0]
    assert "Invented" not in result.refined_text


def test_llm_output_with_removed_url_reference_is_rejected():
    provider = FakeProvider("The full study supports the claim.")
    service = AcademicEditorService(provider_factory=lambda: provider)

    result = service.rewrite(
        "The full study is available at https://example.org/paper.",
        use_llm=True,
    )

    assert result.used_llm is False
    assert "citation markers" in result.notices[0]
    assert "https://example.org/paper" in result.refined_text


def test_llm_failure_does_not_discard_local_revision():
    provider = FakeProvider(error=TimeoutError("provider timed out"))
    service = AcademicEditorService(provider_factory=lambda: provider)

    result = service.rewrite(
        "It is important to note that caste shapes access.",
        use_llm=True,
    )

    assert result.used_llm is False
    assert "important to note" not in result.refined_text.lower()
    assert "TimeoutError" in result.notices[0]
