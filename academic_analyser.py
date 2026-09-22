"""Cached document analysis for academic prose."""
from __future__ import annotations

import re
from collections import Counter

from text_parser import citations as parse_citations
from text_parser import split_sentences, words as parse_words
from dataclasses import dataclass
from typing import Dict, List, Tuple


class AcademicAnalyzer:
    FORMULAIC = ("it is important to note that", "it is worth noting that", "it should be noted that", "in today's world", "in the modern era", "in the realm of", "a plethora of", "plays a crucial role in", "plays a vital role in", "delve into", "deep dive into", "shed light on")
    ABSOLUTES = ("always", "never", "proves that", "clearly demonstrates", "definitively shows", "undeniable", "unquestionably")
    COMPARISON = ("however", "whereas", "although", "by contrast", "in contrast", "similarly", "likewise", "unlike", "while", "yet")
    EVIDENCE = ("according to", "finds", "found", "reports", "reported", "documents", "documented", "observes", "observed", "estimates", "estimated", "survey", "interview", "data", "evidence")
    INTERPRETATION = ("this suggests", "this indicates", "this means", "this demonstrates", "this reveals", "therefore", "thus", "hence", "because")
    GAP = ("however, few", "however, little", "remains unclear", "remains underexplored", "limited attention", "little attention", "has not examined", "has received little", "gap in the literature", "underexplored")
    CONTRIBUTION = ("this study", "this research", "the present study", "this paper", "this article", "i argue", "i examine", "i explore")
    CITATION_AUTHOR_YEAR = re.compile(r"\b[A-Z][A-Za-z'’-]+(?:\s+et al\.)?\s*\((?:19|20)\d{2}[a-z]?\)")
    CITATION_PARENTHETICAL = re.compile(r"\(([^()]*(?:19|20)\d{2}[a-z]?[^()]*)\)")
    AUTHOR_YEAR_IN_PARENTHESIS = re.compile(r"[A-Z][A-Za-z'’-]+(?:\s+et al\.)?,?\s+(?:19|20)\d{2}[a-z]?")
    SOURCE_RE = re.compile(r"\b(?:according to|argues?|argue|finds?|found|shows?|show|reports?|reported|documents?|documented|observes?|observed|estimates?|estimated)\b", re.I)

    def __init__(self, long_sentence_words: int = 35) -> None:
        if long_sentence_words < 1:
            raise ValueError("long_sentence_words must be positive")
        self.long_sentence_words = long_sentence_words

    @classmethod
    def sentences(cls, text: str) -> List[str]:
        return split_sentences(text)

    @classmethod
    def words(cls, text: str) -> List[str]:
        return parse_words(text)

    @classmethod
    def contains(cls, sentence: str, signals: Tuple[str, ...]) -> List[str]:
        lower = sentence.lower()
        return [s for s in signals if re.search(r"\b" + re.escape(s) + r"\b", lower)]

    @classmethod
    @classmethod
    def citations(cls, text: str) -> List[str]:
        return parse_citations(text)

    def analyse(self, text: str) -> Dict[str, object]:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        sentences = self.sentences(text)
        sentence_words = [self.words(s) for s in sentences]
        sentence_citations = [self.citations(s) for s in sentences]
        roles = []
        for i, sentence in enumerate(sentences, 1):
            evidence = self.contains(sentence, self.EVIDENCE)
            interpretation = self.contains(sentence, self.INTERPRETATION)
            comparison = self.contains(sentence, self.COMPARISON)
            gap = self.contains(sentence, self.GAP)
            contribution = self.contains(sentence, self.CONTRIBUTION)
            role = "gap" if gap else "comparison_or_synthesis" if comparison else "source_or_evidence" if evidence or sentence_citations[i-1] else "interpretation" if interpretation else "author_position" if contribution else "claim_or_context"
            roles.append({"sentence": i, "role": role, "signals": {"citation": bool(sentence_citations[i-1]), "evidence": evidence, "interpretation": interpretation, "comparison": comparison, "gap": gap, "contribution": contribution}, "text": sentence})
        role_names = [r["role"] for r in roles]
        openings = [" ".join(words[:2]) for words in sentence_words if words]
        counts = Counter(openings)
        lower_text = text.lower()
        source_claims = [i for i, s in enumerate(sentences, 1) if (sentence_citations[i-1] or self.SOURCE_RE.search(s))]
        cited_source_claims = [i for i in source_claims if sentence_citations[i-1]]
        return {"sentence_count": len(sentences), "word_count": sum(map(len, sentence_words)), "formulaic_phrases": [p for p in self.FORMULAIC if p in lower_text], "possible_overclaims": [p for p in self.ABSOLUTES if p in lower_text], "repetitive_openings": {k: v for k, v in counts.items() if v > 1}, "long_sentences": [{"sentence": i, "words": len(words), "text": sentences[i-1]} for i, words in enumerate(sentence_words, 1) if len(words) >= self.long_sentence_words], "citation_count": len(self.citations(text)), "citations": self.citations(text), "citation_diagnostics": {"cited_source_claims": len(cited_source_claims), "possible_uncited_source_claims": [i for i in source_claims if not sentence_citations[i-1]], "note": "Possible flags only; some claims may be common knowledge or supported by a citation elsewhere in the paragraph."}, "roles": roles, "literature_review_signals": {"source_or_evidence": "source_or_evidence" in role_names, "interpretation": "interpretation" in role_names, "comparison_or_synthesis": "comparison_or_synthesis" in role_names, "gap": "gap" in role_names, "author_position": "author_position" in role_names, "possible_missing": [r for r in ("source_or_evidence", "interpretation", "comparison_or_synthesis") if r not in role_names]}}

    def summary(self, text: str) -> str:
        r = self.analyse(text)
        return f"{r['sentence_count']} sentences, {r['word_count']} words."
