import unittest

from academic_analyser import AcademicAnalyzer
from humanize import HumanizeAI
from advanced_humanize import AdvancedHumanizer


class TestAcademicHumanizer(unittest.TestCase):
    def setUp(self):
        self.core = HumanizeAI()
        self.advanced = AdvancedHumanizer()

    def test_removes_formulaic_ai_opening(self):
        text = "It is important to note that caste shapes land relations."
        self.assertEqual(self.core.humanize(text), "Caste shapes land relations.")

    def test_simplifies_wordiness(self):
        text = "Land relations change due to the fact that institutions change."
        self.assertEqual(
            self.core.humanize(text),
            "Land relations change because institutions change.",
        )

    def test_preserves_citation(self):
        text = "It is important to note that caste varies regionally (Gupta, 2000)."
        self.assertIn("(Gupta, 2000)", self.core.humanize(text))

    def test_preserves_url(self):
        text = "See https://example.org/paper for the full argument."
        self.assertIn("https://example.org/paper", self.core.humanize(text))

    def test_no_conversational_markers(self):
        output = self.core.humanize(
            "Furthermore, caste structures access to land."
        )
        self.assertNotRegex(output.lower(), r"you know|basically|right\?|i think")

    def test_sentence_order_is_preserved(self):
        text = "First, land is redistributed. Second, access is contested."
        output = self.core.humanize(text)
        self.assertLess(output.index("First"), output.index("Second"))

    def test_invalid_profile(self):
        with self.assertRaises(ValueError):
            self.advanced.humanize_complete("Text.", "unknown")


class TestAcademicAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = AcademicAnalyzer()

    def test_detects_formulaic_and_overclaiming(self):
        text = (
            "It is important to note that this proves that caste always "
            "determines land relations."
        )
        report = self.analyzer.analyse(text)
        self.assertIn(
            "it is important to note that", report["formulaic_phrases"]
        )
        self.assertIn("proves that", report["possible_overclaims"])
        self.assertIn("always", report["possible_overclaims"])

    def test_detects_long_sentence(self):
        text = " ".join(["This sentence"] + ["contains"] * 40) + "."
        report = self.analyzer.analyse(text)
        self.assertEqual(len(report["long_sentences"]), 1)

    def test_detects_repeated_opening(self):
        text = "Caste relations matter. Caste relations shape access."
        report = self.analyzer.analyse(text)
        self.assertEqual(report["repetitive_openings"]["caste relations"], 2)


if __name__ == "__main__":
    unittest.main()
