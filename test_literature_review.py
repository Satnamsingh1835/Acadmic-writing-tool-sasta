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
        self.assertEqual(report["paragraphs"][0]["paragraph"], 1)
        self.assertEqual(report["paragraphs"][1]["paragraph"], 2)


if __name__ == "__main__":
    unittest.main()
