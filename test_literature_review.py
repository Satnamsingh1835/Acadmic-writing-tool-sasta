import unittest

from literature_review import LiteratureReviewAnalyzer


class TestLiteratureReviewAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = LiteratureReviewAnalyzer()

    def test_tracks_literature_review_flow(self):
        text = (
            "Jodhka (2004) examines caste and land relations. "
            "This suggests that land relations cannot be separated from caste. "
            "However, other studies identify regional variation. "
            "This remains underexplored. "
            "This study examines how these relations are reconfigured."
        )
        report = self.analyzer.analyse(text)
        signals = report["paragraphs"][0]["signals"]
        for key in self.analyzer.REQUIRED_FLOW:
            self.assertTrue(signals[key], key)
        self.assertEqual(report["paragraphs"][0]["missing"], [])

    def test_flags_missing_synthesis(self):
        text = (
            "Jodhka (2004) examines caste and land relations. "
            "The study reports unequal access to land."
        )
        item = self.analyzer.analyse(text)["paragraphs"][0]
        self.assertIn("interpretation", item["missing"])
        self.assertIn("comparison_or_synthesis", item["missing"])
        self.assertIn("gap", item["missing"])

    def test_preserves_paragraph_units(self):
        text = (
            "Jodhka (2004) examines caste and land relations. "
            "This suggests that land relations are material.\n\n"
            "Other studies identify regional variation."
        )
        report = self.analyzer.analyse(text)
        self.assertEqual(report["paragraph_count"], 2)

    def test_flags_multiple_source_listing(self):
        text = (
            "Jodhka (2004) examines caste and land relations. "
            "Gupta (2000) discusses caste hierarchy. "
            "Judge (2014) examines Punjab."
        )
        synthesis = self.analyzer.analyse(text)["paragraphs"][0]["synthesis_diagnostics"]
        self.assertTrue(synthesis["multiple_sources"])
        self.assertTrue(synthesis["possible_source_listing"])
        self.assertIsNotNone(synthesis["editorial_prompt"])

    def test_recognises_explicit_comparison(self):
        text = (
            "Jodhka (2004) examines caste and land relations. "
            "However, Gupta (2000) identifies regional variation."
        )
        synthesis = self.analyzer.analyse(text)["paragraphs"][0]["synthesis_diagnostics"]
        self.assertTrue(synthesis["explicit_synthesis_signal"])
        self.assertTrue(synthesis["signals"]["contrast_or_tension"])

    def test_recognises_qualification_and_reconfiguration(self):
        text = (
            "Jodhka (2004) examines caste and land relations. "
            "Gupta (2000) qualifies this account because the relationship varies over time."
        )
        synthesis = self.analyzer.analyse(text)["paragraphs"][0]["synthesis_diagnostics"]
        self.assertTrue(synthesis["signals"]["qualification_or_condition"])
        self.assertTrue(synthesis["signals"]["temporal_reconfiguration"])

    def test_does_not_invent_interpretation(self):
        text = (
            "Jodhka (2004) examines caste and land relations. "
            "Gupta (2000) discusses caste hierarchy."
        )
        prompt = self.analyzer.analyse(text)["paragraphs"][0]["synthesis_diagnostics"]["editorial_prompt"]
        self.assertIsNotNone(prompt)
        self.assertNotIn("Jodhka", prompt)

    def test_prompt_absent_when_synthesis_signal_exists(self):
        text = (
            "Jodhka (2004) examines caste and land relations. "
            "However, Gupta (2000) identifies regional variation."
        )
        synthesis = self.analyzer.analyse(text)["paragraphs"][0]["synthesis_diagnostics"]
        self.assertIsNone(synthesis["editorial_prompt"])


if __name__ == "__main__":
    unittest.main()
