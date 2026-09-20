"""Advanced academic humanization built on the conservative core."""

from __future__ import annotations

import re
from typing import Dict

from humanize import HumanizeAI


class AdvancedHumanizer(HumanizeAI):
    """Academic editor with conservative, standard, and polish modes.

    This class never randomly inserts fillers, emojis, rhetorical questions,
    personal opinions, or sentence reordering.
    """

    PROFILES: Dict[str, Dict[str, bool]] = {
        "conservative": {
            "remove_ai_phrases": True,
            "simplify_wordiness": False,
            "soften_absolute_claims": False,
        },
        "standard": {
            "remove_ai_phrases": True,
            "simplify_wordiness": True,
            "soften_absolute_claims": False,
        },
        "polish": {
            "remove_ai_phrases": True,
            "simplify_wordiness": True,
            "soften_absolute_claims": True,
        },
    }

    def humanize_complete(self, text: str, intensity: str = "standard") -> str:
        """Humanize academic prose using a named editing profile.

        light/medium/heavy remain accepted for backwards compatibility.
        """
        aliases = {
            "light": "conservative",
            "medium": "standard",
            "heavy": "polish",
        }
        profile = aliases.get(intensity.lower(), intensity.lower())

        if profile not in self.PROFILES:
            raise ValueError(
                f"Unknown profile '{intensity}'. "
                f"Choose from: {', '.join(self.PROFILES)}."
            )

        settings = self.PROFILES[profile]
        editor = HumanizeAI(**settings)
        return editor.humanize(text)

    def humanize_paragraph(self, text: str, profile: str = "standard") -> str:
        """Alias with terminology suited to academic writing."""
        return self.humanize_complete(text, intensity=profile)

    def clean_spacing(self, text: str) -> str:
        """Normalize whitespace without changing wording."""
        return re.sub(r"[ \t]+", " ", text).strip()


if __name__ == "__main__":
    text = (
        "It is important to note that the relationship between caste and land "
        "is multifaceted. Moreover, it plays a crucial role in shaping agrarian "
        "relations due to the fact that land is unequally distributed."
    )

    humanizer = AdvancedHumanizer()
    for profile in ("conservative", "standard", "polish"):
        print(f"\n--- {profile.upper()} ---")
        print(humanizer.humanize_paragraph(text, profile))
