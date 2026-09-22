import unittest

from text_parser import (
    author_year_citations,
    citations,
    paragraph_count,
    split_paragraphs,
    split_sentences,
    words,
)


class TestTextParser(unittest.TestCase):
    def test_sentence_split_handles_academic_abbreviations(self):
        text = "This uses e.g. a standard abbreviation. The next sentence follows."
        self.assertEqual(len(split_sentences(text)), 2)

    def test_sentence_split_handles_et_al_and_decimals(self):
        text = "Jodhka et al. (2004) examine the issue. The rate was 2.5 percent."
        self.assertEqual(len(split_sentences(text)), 2)

    def test_sentence_split_preserves_quoted_sentence(self):
        text = 'The author writes "This matters." The analysis continues.'
        self.assertEqual(len(split_sentences(text)), 2)

    def test_paragraph_split_is_shared(self):
        text = "First paragraph.\n\nSecond paragraph."
        self.assertEqual(split_paragraphs(text), ["First paragraph.", "Second paragraph."])
        self.assertEqual(paragraph_count(text), 2)

    def test_words_are_unicode_aware(self):
        self.assertIn("caste", words("Caste and land relations."))
        self.assertIn("ਪੰਜਾਬ", words("ਪੰਜਾਬ land"))

    def test_author_year_parser_handles_narrative_and_parenthetical(self):
        text = "Jodhka (2004) examines caste. Gupta et al. (2000) respond. (Judge, 2014; Singh, 2021a)"
        found = author_year_citations(text)
        self.assertIn("Jodhka (2004)", found)
        self.assertIn("Gupta et al. (2000)", found)
        self.assertIn("Judge, 2014", found)
        self.assertIn("Singh, 2021a", found)

    def test_citations_are_deduplicated(self):
        text = "Jodhka (2004) argues this. Jodhka (2004) revisits it."
        self.assertEqual(citations(text), ["Jodhka (2004)"])


if __name__ == "__main__":
    unittest.main()
