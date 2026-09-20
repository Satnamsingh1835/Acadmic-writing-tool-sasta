"""Academic literature-review humanizer.

Conservative and deterministic: no fillers, emojis, rhetorical questions,
random sentence reordering, invented claims, or citation rewriting.
"""

from humanize import HumanizeAI


class AdvancedHumanizer(HumanizeAI):
    """Academic editor with literature-review profiles."""

    PROFILES = {
        "conservative": dict(
            remove_ai_phrases=True,
            simplify_wordiness=False,
            soften_absolute_claims=False,
            british_english=True,
        ),
        "standard": dict(
            remove_ai_phrases=True,
            simplify_wordiness=True,
            soften_absolute_claims=False,
            british_english=True,
        ),
        "polish": dict(
            remove_ai_phrases=True,
            simplify_wordiness=True,
            soften_absolute_claims=True,
            british_english=True,
        ),
    }

    def humanize_complete(self, text: str, intensity: str = "standard") -> str:
        """Humanize academic prose using a named profile."""
        aliases = {"light": "conservative", "medium": "standard", "heavy": "polish"}
        profile = aliases.get(intensity.lower(), intensity.lower())

        if profile not in self.PROFILES:
            raise ValueError(
                f"Unknown profile '{intensity}'. "
                f"Choose from: {', '.join(self.PROFILES)}."
            )

        return HumanizeAI(**self.PROFILES[profile]).humanize(text)

    def humanize_literature_review(self, text: str, profile: str = "standard") -> str:
        """Humanize a literature-review passage while preserving paragraphs."""
        return self.humanize_complete(text, profile)

    def humanize_paragraph(self, text: str, profile: str = "standard") -> str:
        return self.humanize_complete(text, profile)


if __name__ == "__main__":
    sample = (
        "It is important to note that caste plays a crucial role in shaping "
        "agrarian relations. Furthermore, land relations change due to the fact "
        "that institutions are historically specific."
    )
    editor = AdvancedHumanizer()
    for profile in ("conservative", "standard", "polish"):
        print(f"\n--- {profile.upper()} ---")
        print(editor.humanize_literature_review(sample, profile))
