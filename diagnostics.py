"""Deterministic, offline diagnostics for academic prose.

Every finding carries exact character offsets into the text the caller sent, so
the editor can mark and correct the precise range. Nothing here contacts a
network service, and nothing rewrites a document by itself: the module only
describes what it observed and, where it is confident, offers a replacement.

Offset rules (documented so the client and the tests agree):

* offsets are Python ``str`` indices (code points, not UTF-16 units) into the
  text as sent; the editor's ``selectionStart``/``slice`` use the same units;
* line endings are not rewritten, so an offset means the same thing before and
  after a save (the document store already normalises CRLF on save);
* Markdown structure is masked before analysis (fenced code, inline code, YAML
  front matter, link targets, the reference list) and structural markers
  (heading hashes, list bullets, quote markers, table pipes) are dropped from
  the analysed prose while the mapping back to the original text is preserved,
  so a marker never shifts a reported range;
* citations, quotations and protected spans are excluded from spelling and
  capitalisation findings but still count towards readability;
* findings may overlap (a long sentence can also contain wordiness); they are
  ordered by ``start``, then ``end``, then rule id.

The rule tables are shared with the rest of the application: wordiness and
formulaic phrasing come from ``humanize``/``academic_analyser`` so a diagnostic
and a refine proposal never disagree about wording.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import os
import re
import tempfile
import threading
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from academic_analyser import AcademicAnalyzer
from diagnostic_lexicon import PROTECTED_WORDS, is_protected_word, looks_like_acronym
from humanize import HumanizeAI
from text_parser import _WORD_RE

# --------------------------------------------------------------------- limits

MAX_DOCUMENT_CHARS = 2_000_000
MAX_FINDINGS = 600
MAX_FINDINGS_PER_RULE = 120
# Words the spelling rules may report per document. The expensive step is
# finding one-edit neighbours, so the scan stops as soon as both spelling rules
# have reached their per-rule cap -- see ``_spelling_rules``. There is
# deliberately no *suggestion* budget any more: it used to decide whether a word
# looked like a typo, so a long document silently reclassified its later typos as
# merely "unknown". Classification must never depend on how much work has
# already been done.
SPELLING_RULES: tuple[str, ...] = ("spelling.misspelling", "spelling.unknown-word")
# Once this many unknown words in a row produced no finding, the spelling scan
# stops for the document: the rules are capped (so nothing more can be reported
# except through the personal dictionary), and this is what keeps a page of
# nonsense from costing seconds. Words after the stop are simply not examined,
# and the report says so through ``truncated``.
MAX_BARREN_SPELLING_WORDS = 40
CHUNK_TARGET_CHARS = 4_000
LONG_SENTENCE_WORDS = 35
LONG_PARAGRAPH_WORDS = 220
SPELLING_MIN_WORD_LENGTH = 3

# ---------------------------------------------------------------- categories

CATEGORY_INFO: dict[str, dict[str, str]] = {
    "spelling": {
        "label": "Spelling",
        "kind": "error",
        "hint": "Words that are not in the local dictionary.",
    },
    "agreement": {
        "label": "Subject-verb agreement",
        "kind": "error",
        "hint": "A verb that does not match its subject. Conventions that both styles allow are marked as style.",
    },
    "punctuation": {
        "label": "Punctuation",
        "kind": "error",
        "hint": "Spacing, doubled punctuation and unclosed brackets.",
    },
    "capitalization": {
        "label": "Capitalization",
        "kind": "error",
        "hint": "Sentence starts, the pronoun 'I' and language or nationality adjectives.",
    },
    "fragment": {
        "label": "Sentence fragment",
        "kind": "error",
        "hint": "A group of words without a main clause.",
    },
    "run_on": {
        "label": "Run-on sentence",
        "kind": "error",
        "hint": "Two clauses joined by a comma without a conjunction.",
    },
    "wordiness": {
        "label": "Wordiness and clarity",
        "kind": "style",
        "hint": "Longer wording where a shorter one says the same thing.",
    },
    "repetition": {
        "label": "Repetition",
        "kind": "style",
        "hint": "Words or phrases repeated closely together.",
    },
    "readability": {
        "label": "Readability",
        "kind": "style",
        "hint": "Sentences or paragraphs that are hard to follow.",
    },
    "tone": {
        "label": "Academic tone",
        "kind": "style",
        "hint": "Informal or overclaiming wording.",
    },
}

CATEGORY_ORDER: tuple[str, ...] = tuple(CATEGORY_INFO)
STYLE_CATEGORIES = frozenset(c for c in CATEGORY_ORDER if CATEGORY_INFO[c]["kind"] == "style")

# The coarse taxonomy a reader thinks in (the categories named in the request),
# reported next to the precise rule category so the sidebar can group widely
# while a rule keeps its own narrow identity.
DIAGNOSTIC_GROUPS: dict[str, dict[str, str]] = {
    "spelling": {"label": "Spelling"},
    "grammar": {"label": "Grammar"},
    "punctuation": {"label": "Punctuation"},
    "sentence_structure": {"label": "Sentence structure"},
    "clarity": {"label": "Clarity"},
    "concision": {"label": "Concision"},
    "academic_style": {"label": "Academic style"},
    "repetition": {"label": "Repetition"},
}

CATEGORY_GROUP: dict[str, str] = {
    "spelling": "spelling",
    "agreement": "grammar",
    "capitalization": "grammar",
    "punctuation": "punctuation",
    "fragment": "sentence_structure",
    "run_on": "sentence_structure",
    "readability": "clarity",
    "wordiness": "concision",
    "repetition": "repetition",
    "tone": "academic_style",
}

GROUP_ORDER: tuple[str, ...] = tuple(DIAGNOSTIC_GROUPS)

# ------------------------------------------------------------------ versions

ENGINE_NAME = "ScholarFlow local diagnostics"
ENGINE_VERSION = "3.0.0"
RULESET_VERSION = "2026.10"
DEFAULT_RULE_VERSION = "1.0"

# Rules introduced or materially changed after the first ruleset: a client can
# tell "this rule is new" from "this rule changed what it reports".
RULE_VERSIONS: dict[str, str] = {
    "spelling.misspelling": "2.0",
    "spelling.unknown-word": "2.0",
    "grammar.mass-noun-plural": "2.0",
    "grammar.article-an": "2.0",
    "grammar.redundant-preposition": "2.0",
    "punctuation.missing-apostrophe": "2.0",
    "clarity.ambiguous-this": "2.0",
}


def rule_version(rule: str) -> str:
    return RULE_VERSIONS.get(rule, DEFAULT_RULE_VERSION)


# ------------------------------------------------------------------ profiles


@dataclass(frozen=True)
class DiagnosticProfile:
    """A named emphasis for the *style* rules.

    Spelling and the reliable grammar families run in every profile; a profile
    only chooses which optional style categories are reported and how strict
    the length thresholds are. It never changes document text.
    """

    id: str
    label: str
    summary: str
    style_categories: frozenset[str]
    thresholds: dict[str, int]
    category_weights: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "summary": self.summary,
            "style_categories": sorted(self.style_categories),
            "thresholds": dict(self.thresholds),
            "always_on_categories": sorted(ERROR_CATEGORIES),
        }


# Rules a researcher expects to run no matter which emphasis they picked.
ERROR_CATEGORIES = frozenset(c for c in CATEGORY_ORDER if c not in STYLE_CATEGORIES)

PROFILES: dict[str, DiagnosticProfile] = {
    "academic_standard": DiagnosticProfile(
        id="academic_standard",
        label="Academic Standard",
        summary="Balanced: every error rule plus optional clarity, concision and register suggestions.",
        style_categories=frozenset(STYLE_CATEGORIES),
        thresholds={
            "long_sentence_words": LONG_SENTENCE_WORDS,
            "long_paragraph_words": LONG_PARAGRAPH_WORDS,
        },
        category_weights={
            "spelling": 0,
            "agreement": 1,
            "punctuation": 2,
            "capitalization": 3,
            "fragment": 4,
            "run_on": 5,
            "readability": 6,
            "wordiness": 7,
            "tone": 8,
            "repetition": 9,
        },
    ),
    "formal_academic": DiagnosticProfile(
        id="formal_academic",
        label="Formal Academic Writing",
        summary="Register first: keeps the formality and readability checks, holds back concision suggestions, and tolerates longer formal sentences.",
        style_categories=frozenset({"tone", "readability", "repetition"}),
        thresholds={
            # Formal prose is allowed to run longer before it is questioned.
            "long_sentence_words": 45,
            "long_paragraph_words": LONG_PARAGRAPH_WORDS,
        },
        category_weights={
            "spelling": 0,
            "agreement": 1,
            "tone": 2,
            "punctuation": 3,
            "capitalization": 4,
            "fragment": 5,
            "run_on": 6,
            "readability": 7,
            "repetition": 8,
            "wordiness": 9,
        },
    ),
    "concise_academic": DiagnosticProfile(
        id="concise_academic",
        label="Concise Academic Writing",
        summary="Brevity first: questions length, wordiness and repetition earlier, and leaves register comments aside.",
        style_categories=frozenset({"readability", "wordiness", "repetition"}),
        thresholds={
            "long_sentence_words": 28,
            "long_paragraph_words": 170,
        },
        category_weights={
            "spelling": 0,
            "agreement": 1,
            "wordiness": 2,
            "readability": 3,
            "repetition": 4,
            "punctuation": 5,
            "capitalization": 6,
            "fragment": 7,
            "run_on": 8,
            "tone": 9,
        },
    ),
}

DEFAULT_PROFILE = "academic_standard"

# A profile name that reaches the API from a bookmark, a saved preference or an
# older build is normalised here rather than rejected.
PROFILE_ALIASES: dict[str, str] = {
    "standard": "academic_standard",
    "academic": "academic_standard",
    "medium": "academic_standard",
    "default": "academic_standard",
    "formal": "formal_academic",
    "conservative": "formal_academic",
    "light": "formal_academic",
    "minimal": "formal_academic",
    "concise": "concise_academic",
    "polish": "concise_academic",
    "heavy": "concise_academic",
}


def normalize_profile(profile: str | None) -> DiagnosticProfile:
    """Resolve a profile name, accepting the rewrite profiles' names too."""
    if profile is None:
        return PROFILES[DEFAULT_PROFILE]
    if not isinstance(profile, str):
        raise ValueError("Profile must be a string.")
    key = profile.strip().lower().replace("-", "_").replace(" ", "_")
    key = PROFILE_ALIASES.get(key, key)
    resolved = PROFILES.get(key)
    if resolved is None:
        choices = ", ".join(p.id for p in PROFILES.values())
        raise ValueError(f"Unknown profile '{profile}'. Choose from: {choices}.")
    return resolved


# ----------------------------------------------------------------- data model


@dataclass(frozen=True)
class Diagnostic:
    """One finding, positioned exactly in the analysed text."""

    rule: str
    category: str
    kind: str
    confidence: str
    message: str
    explanation: str
    start: int
    end: int
    original: str
    replacements: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        digest = hashlib.sha1(self.original.encode("utf-8")).hexdigest()[:8]
        return f"{self.rule}@{self.start}-{self.end}#{digest}"

    @property
    def group(self) -> str:
        return CATEGORY_GROUP.get(self.category, self.category)

    def priority(self, profile: "DiagnosticProfile | None" = None) -> int:
        """Lower sorts first in the sidebar; profiles reprioritise, never rewrite."""
        if profile is None:
            profile = PROFILES[DEFAULT_PROFILE]
        return profile.category_weights.get(self.category, len(CATEGORY_ORDER))

    def to_dict(self, profile: "DiagnosticProfile | None" = None) -> dict[str, object]:
        info = CATEGORY_INFO.get(self.category, {})
        group = self.group
        return {
            "id": self.id,
            "rule": self.rule,
            "rule_version": rule_version(self.rule),
            "engine_version": ENGINE_VERSION,
            "ruleset_version": RULESET_VERSION,
            "category": self.category,
            "category_label": info.get("label", self.category),
            "group": group,
            "group_label": DIAGNOSTIC_GROUPS.get(group, {}).get("label", group),
            "kind": self.kind,
            "severity": self.kind,
            "confidence": self.confidence,
            "priority": self.priority(profile),
            "message": self.message,
            "explanation": self.explanation,
            "start": self.start,
            "end": self.end,
            "original": self.original,
            "replacement": self.replacements[0] if self.replacements else None,
            "replacements": list(self.replacements),
        }

    def sort_key(self) -> tuple[int, int, str]:
        return (self.start, self.end, self.rule)


# --------------------------------------------------------------- word tables

# Wording preferences that the refine path already applies, so diagnostics and
# rewrites agree. Sources: HumanizeAI.DEFAULT_WORDINESS / AI_MARKER_REPLACEMENTS.
WORDINESS_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("in order to", "to"),
    ("due to the fact that", "because"),
    ("despite the fact that", "although"),
    ("in spite of the fact that", "although"),
    ("at this point in time", "currently"),
    ("has the ability to", "can"),
    ("is able to", "can"),
    ("are able to", "can"),
    ("a number of", "several"),
    ("a large number of", "many"),
    ("in the event that", "if"),
    ("for the purpose of", "for"),
    ("in the realm of", "in"),
    ("a plethora of", "many"),
    ("a wide range of", "many"),
    ("plays a crucial role in shaping", "shapes"),
    ("plays a vital role in shaping", "shapes"),
    ("play a crucial role in shaping", "shape"),
    ("play a vital role in shaping", "shape"),
    ("plays a crucial role in", "shapes"),
    ("plays a vital role in", "shapes"),
    ("delves into", "examines"),
    ("delve into", "examine"),
    ("sheds light on", "examines"),
    ("shed light on", "examine"),
    ("provides a deep dive into", "examines"),
    ("robust and comprehensive", "detailed"),
)

# Formulaic openers removed without replacement (optional style suggestion).
FORMULAIC_REMOVALS: tuple[str, ...] = (
    "it is important to note that",
    "it is worth noting that",
    "it should be noted that",
    "it is interesting to note that",
)

VAGUE_QUANTIFIERS: tuple[tuple[str, str | None], ...] = (
    ("a lot of", "many"),
    ("lots of", "many"),
    ("a bit", "slightly"),
    ("kind of", "somewhat"),
    ("sort of", "somewhat"),
    ("a huge amount of", "much"),
)

CONTRACTIONS: tuple[tuple[str, str], ...] = (
    ("don't", "do not"),
    ("doesn't", "does not"),
    ("didn't", "did not"),
    ("can't", "cannot"),
    ("won't", "will not"),
    ("isn't", "is not"),
    ("aren't", "are not"),
    ("wasn't", "was not"),
    ("weren't", "were not"),
    ("hasn't", "has not"),
    ("haven't", "have not"),
    ("hadn't", "had not"),
    ("won't", "will not"),
    ("wouldn't", "would not"),
    ("shouldn't", "should not"),
    ("couldn't", "could not"),
    ("it's", "it is"),
    ("that's", "that is"),
    ("there's", "there is"),
    ("they're", "they are"),
    ("we're", "we are"),
    ("you're", "you are"),
    ("i'm", "I am"),
    ("let's", "let us"),
)

OVERCLAIM_WORDS: tuple[str, ...] = tuple(
    sorted(AcademicAnalyzer.ABSOLUTES, key=len, reverse=True)
) + ("everyone", "nobody", "no one", "obviously", "of course", "undoubtedly")

# Titles, languages, nationalities and months that must start with a capital.
CAPITALIZED_TERMS = frozenset(
    """
    english french german spanish italian portuguese dutch russian chinese japanese korean
    arabic persian sanskrit hindi urdu tamil kannada bengali marathi gujarati punjabi telugu
    malayalam sinhala swahili latin greek hebrew turkish thai vietnamese indonesian malay
    indian american british european asian african australian canadian irish scottish welsh
    victorian edwardian mughal colonial january february march april may june july august
    september october november december monday tuesday wednesday thursday friday saturday sunday
    """.split()
)

STOPWORDS = frozenset(
    """
    a about above after again against all also am among an and any are as at be because been
    before being below between both but by can cannot could did do does doing down during each
    few for from further had has have having he her here hers herself him himself his how i if
    in into is it its itself just me more most my myself no nor not of off on once only or other
    ought our ours ourselves out over own same she should so some such than that the their theirs
    them themselves then there these they this those through to too under until up very was we
    were what when where which while who whom why will with would you your yours yourself
    yourselves thus however therefore moreover furthermore additionally
    """.split()
)

FINITE_VERBS = frozenset(
    """
    is are was were be been being am has have had do does did can could may might must shall
    should will would appears appear appeared seems seem seemed becomes become became remains
    remain remained suggests suggest suggested shows show showed indicates indicate indicated
    argues argue argued finds find found reports report reported demonstrates demonstrate
    demonstrated reveals reveal revealed examines examine examined explores explore explored
    notes note noted observes observe observed concludes conclude concluded claims claim claimed
    states state stated explains explain explained shows remains includes include included
    reflects reflect reflected examines supports support supported challenges challenge
    challenged establishes establish established provides provide provided offers offer offered
    suggests leads lead led makes make made takes take took gives give gave goes go went comes
    come came says say said thinks think thought believes believe believed holds hold held
    draws draw drew points point pointed reveals contributes contribute contributed
    """.split()
)

# -ed/-ing words that also work as finite verbs in academic prose.
FINITE_ED_FORMS = frozenset({"based", "used", "found", "said", "shown", "given"})

IMPERATIVE_HINTS = frozenset(
    """
    consider note examine explore use apply take write read see compare contrast discuss
    describe analyse analyze define remember ensure avoid describe report present
    """.split()
)

SUBORDINATORS = frozenset(
    """
    because although though since while whereas if unless until when whenever after before
    as that which who whom whose where whether despite during given provided
    """.split()
)

COORDINATORS = frozenset({"and", "but", "or", "nor", "for", "so", "yet"})

RELATIVE_PRONOUNS = frozenset({"which", "who", "whom", "whose", "that", "where"})

PLURAL_SUBJECTS = frozenset(
    """
    people scholars researchers authors participants respondents students respondents
    studies findings results data criteria phenomena analyses children women men policies
    institutions scholars reviewers editors interviewers respondents
    """.split()
)

IRREGULAR_PLURALS = frozenset(
    """
    children women men people data criteria phenomena analyses media curricula indices
    """.split()
)

# Words that end in "s" but are singular (so "a/an X" is fine).
SINGULAR_S_WORDS = frozenset(
    """
    analysis basis crisis thesis hypothesis synthesis emphasis focus status apparatus census
    class process business access progress success address stress process species series
    analysis consensus apparatus nexus corpus locus radius virus campus census discourse
    """.split()
)


def _british_equivalents(word: str) -> Iterator[str]:
    """Candidate US spellings for a British form, so it is never flagged."""
    yield re.sub(r"isation\b", "ization", word)
    yield re.sub(r"ise\b", "ize", word)
    yield re.sub(r"ised\b", "ized", word)
    yield re.sub(r"ises\b", "izes", word)
    yield re.sub(r"ising\b", "izing", word)
    yield re.sub(r"yse\b", "yze", word)
    yield re.sub(r"ysed\b", "yzed", word)
    yield re.sub(r"yses\b", "yzes", word)
    yield re.sub(r"ysing\b", "yzing", word)
    yield re.sub(r"our\b", "or", word)
    yield re.sub(r"ours\b", "ors", word)
    yield re.sub(r"oured\b", "ored", word)
    yield re.sub(r"ouring\b", "oring", word)
    yield re.sub(r"ourite\b", "orite", word)
    yield re.sub(r"re\b", "er", word)
    yield re.sub(r"ogue\b", "og", word)
    yield re.sub(r"elled\b", "eled", word)
    yield re.sub(r"elling\b", "eling", word)
    yield re.sub(r"eller\b", "eler", word)
    yield re.sub(r"mme\b", "m", word)
    yield re.sub(r"ence\b", "ense", word)
    yield re.sub(r"eable\b", "able", word)


# Contractions that are unambiguously mispunctuated without an apostrophe. A
# closed list: "its/it's", "whose/who's" and possessives are excluded on purpose.
MISSING_APOSTROPHE_FORMS: dict[str, str] = {
    "dont": "don't",
    "doesnt": "doesn't",
    "didnt": "didn't",
    "isnt": "isn't",
    "arent": "aren't",
    "wasnt": "wasn't",
    "werent": "weren't",
    "hasnt": "hasn't",
    "havent": "haven't",
    "hadnt": "hadn't",
    "couldnt": "couldn't",
    "wouldnt": "wouldn't",
    "shouldnt": "shouldn't",
    "cant": "can't",
    "wont": "won't",
    "thats": "that's",
    "theres": "there's",
}
# Forms that are also ordinary words somewhere in academic English ("cant" = cant
# language, "wont" = wont), so they are reported more cautiously.
HOMOPHONE_APOSTROPHE_FORMS = frozenset({"cant", "wont", "thats"})

# Words spelled with a vowel letter that begin with a consonant sound.
CONSONANT_SOUND_VOWELS: tuple[str, ...] = (
    "uni", "use", "usu", "uti", "utili", "eu", "eul", "eup", "euro", "ufo",
    "one", "once", "ouija", "ubiq",
)

# Words whose leading "h" is silent, so the article follows the vowel.
SILENT_H_WORDS = frozenset(
    {
        "hour", "hours", "hourly", "honest", "honestly", "honesty",
        "honour", "honours", "honourable", "honor", "honors", "honorable",
        "heir", "heirs", "heiress",
    }
)

# Uncountable nouns that never take a plural in academic English. Deliberately
# short: "researches", "trainings" and "evidences" are ordinary in Indian
# English and in legal writing, so they are left alone.
MASS_NOUN_PLURALS: dict[str, str] = {
    "informations": "information",
    "equipments": "equipment",
    "feedbacks": "feedback",
    "advices": "advice",
    "knowledges": "knowledge",
    "softwares": "software",
    "datas": "data",
    "furnitures": "furniture",
    "homeworks": "homework",
    "luggages": "luggage",
}

# Transitive verbs that take no preposition in standard usage.
REDUNDANT_PREPOSITIONS: dict[str, str] = {
    "discuss about": "discuss",
    "discusses about": "discusses",
    "discussed about": "discussed",
    "discussing about": "discussing",
    "emphasise on": "emphasise",
    "emphasises on": "emphasises",
    "emphasised on": "emphasised",
    "emphasize on": "emphasize",
    "emphasizes on": "emphasizes",
    "emphasized on": "emphasized",
}


def _match_case(original: str, replacement: str) -> str:
    """Carry the original capitalisation onto a replacement."""
    if original.isupper() and len(original) > 1:
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


# ------------------------------------------------------------------ the mask


class _Mask:
    """Regions of the document that must not be analysed as prose."""

    def __init__(self, text: str) -> None:
        self.text = text
        self._line_starts = self._compute_line_starts(text)
        ranges: list[tuple[int, int]] = []
        ranges.extend(self._front_matter(text))
        ranges.extend(self._code_blocks(text))
        ranges.extend(self._inline_code(text))
        ranges.extend(self._reference_list(text))
        ranges.extend(self._resource_spans(text))
        self.ranges = _merge_ranges(ranges)
        # The merged ranges are sorted and non-overlapping, so a lookup can
        # binary-search them instead of walking the list. The prose builder asks
        # this question once per character, which made a long document with many
        # code spans and citations quadratic before.
        self._range_starts = [start for start, _ in self.ranges]

    @staticmethod
    def _compute_line_starts(text: str) -> list[int]:
        starts = [0]
        for match in re.finditer("\n", text):
            starts.append(match.end())
        return starts

    def line_index(self, position: int) -> int:
        return max(0, bisect.bisect_right(self._line_starts, position) - 1)

    def line_span(self, index: int) -> tuple[int, int]:
        start = self._line_starts[index]
        if index + 1 < len(self._line_starts):
            end = self._line_starts[index + 1]
        else:
            end = len(self.text)
        # Keep the newline out of the span so it can be re-emitted as prose.
        while end > start and self.text[end - 1] == "\n":
            end -= 1
        return start, end

    def line_text(self, index: int) -> str:
        start, end = self.line_span(index)
        return self.text[start:end]

    def _covering(self, position: int) -> int:
        """Index of the merged range containing ``position``, or -1."""
        index = bisect.bisect_right(self._range_starts, position) - 1
        if index >= 0 and self.ranges[index][1] > position:
            return index
        return -1

    def blocked(self, start: int, end: int) -> bool:
        """True when any masked region overlaps the span."""
        index = self._covering(start)
        if index >= 0:
            return True
        following = bisect.bisect_right(self._range_starts, start)
        return following < len(self.ranges) and self.ranges[following][0] < end

    def fully_blocked(self, start: int, end: int) -> bool:
        """True when a masked region covers the whole span (e.g. a code line)."""
        index = self._covering(start)
        return index >= 0 and self.ranges[index][1] >= end

    def line_count(self) -> int:
        return len(self._line_starts)

    def iter_blocked(self) -> Iterator[tuple[int, int]]:
        return iter(self.ranges)

    # -- individual mask kinds -------------------------------------------

    @staticmethod
    def _front_matter(text: str) -> list[tuple[int, int]]:
        if not text.startswith("---"):
            return []
        closing = re.search(r"^---\s*$|^\.\.\.\s*$", text[3:], re.MULTILINE)
        if not closing:
            return []
        return [(0, 3 + closing.end())]

    def _code_blocks(self, text: str) -> list[tuple[int, int]]:
        ranges: list[tuple[int, int]] = []
        open_at: int | None = None
        fence_char = ""
        fence_len = 0
        for index, line in enumerate(text.split("\n")):
            stripped = line.strip()
            if open_at is None:
                match = re.match(r"^(`{3,}|~{3,})", stripped)
                if match:
                    # Only the fence character may repeat; the optional info
                    # string is checked with string operations instead of a
                    # second whitespace quantifier, which would backtrack
                    # badly on a line of spaces in a large document.
                    rest = stripped[match.end():]
                    if not rest or (
                        " " not in rest and "\t" not in rest and "`" not in rest and "~" not in rest
                    ):
                        open_at = self._line_starts[index]
                        fence_char = match.group(1)[0]
                        fence_len = len(match.group(1))
                continue
            if re.fullmatch(rf"{re.escape(fence_char)}{{{fence_len},}}", stripped):
                start, end = self.line_span(index)
                ranges.append((open_at, end))
                open_at = None
        if open_at is not None:
            ranges.append((open_at, len(text)))
        return ranges

    @staticmethod
    def _inline_code(text: str) -> list[tuple[int, int]]:
        ranges: list[tuple[int, int]] = []
        taken: list[tuple[int, int]] = []
        for size in (3, 2, 1):
            pattern = rf"(?<!`){'`' * size}([^`\n]*?){'`' * size}(?!`)"
            for match in re.finditer(pattern, text):
                span = (match.start(), match.end())
                if any(span[0] < end and start < span[1] for start, end in taken):
                    continue
                taken.append(span)
                ranges.append(span)
        return ranges

    _REFERENCE_HEADING_RE = re.compile(
        r"(?:#{1,6} ?)?(references|bibliography|works cited|literature cited):?",
        re.IGNORECASE,
    )

    @classmethod
    def _reference_list(cls, text: str) -> list[tuple[int, int]]:
        """Mask the reference list, matched per stripped line.

        The heading is matched against an already trimmed line, so the pattern
        contains no repeated whitespace quantifiers and cannot backtrack on a
        long run of spaces or tabs in a large document.
        """
        offset = 0
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped and cls._REFERENCE_HEADING_RE.fullmatch(stripped):
                return [(offset, len(text))]
            offset += len(line) + 1
        return []

    @staticmethod
    def _resource_spans(text: str) -> list[tuple[int, int]]:
        patterns = (
            r"https?://\S+",
            r"\bwww\.[^\s)\]]+",
            r"\bdoi:\s*\S+",
            r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+",
            r"[\w.+-]+@[\w-]+\.[\w.-]+",
            r"\]\(([^)\s]+)\)",  # Markdown link target
            r"\[[^\]]*\]:\s*\S+",  # link reference definition
        )
        ranges: list[tuple[int, int]] = []
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                ranges.append((match.start(), match.end()))
        return ranges


def _merge_ranges(ranges: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    ordered = sorted((start, end) for start, end in ranges if end > start)
    merged: list[tuple[int, int]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


# ------------------------------------------------------------- prose mapping


@dataclass
class _View:
    """Prose view of a chunk plus the mapping back to original offsets."""

    text: str
    index_map: list[int]
    segments: list[tuple[int, int]]
    heading_segments: list[tuple[int, int]]

    def in_heading(self, position: int) -> bool:
        return any(start <= position < end for start, end in self.heading_segments)

    def original_span(self, start: int, end: int) -> tuple[int, int]:
        if start >= end:
            return (self.index_map[start] if start < len(self.index_map) else 0, 0)
        return (self.index_map[start], self.index_map[end - 1] + 1)


_LIST_PREFIX_RE = re.compile(r"^(\s*)([-*+]\s+|\d{1,3}[.)]\s+)")
_BLOCKQUOTE_RE = re.compile(r"^(\s*)((?:>\s?)+)")
_HEADING_RE = re.compile(r"^(\s{0,3})(#{1,6})(\s+)")
_TABLE_RE = re.compile(r"^\s*\|")
_HARD_BREAK = "\u0000"


class _ViewBuilder:
    """Render one chunk as prose while keeping a map back to original offsets."""

    def __init__(self, text: str, mask: _Mask) -> None:
        self.text = text
        self.mask = mask
        self.pieces: list[str] = []
        self.mapping: list[int] = []
        self.segments: list[tuple[int, int]] = []
        self.heading_segments: list[tuple[int, int]] = []
        self.segment_start = 0

    def emit(self, char: str, source_index: int) -> None:
        self.pieces.append(char)
        self.mapping.append(source_index)

    def close_segment(self) -> None:
        if len(self.pieces) > self.segment_start:
            self.segments.append((self.segment_start, len(self.pieces)))
        self.pieces.append(_HARD_BREAK)
        self.mapping.append(-1)
        self.segment_start = len(self.pieces)

    def build(self, start: int, end: int) -> _View:
        text, mask = self.text, self.mask
        line_index = mask.line_index(start)
        while line_index < mask.line_count():
            line_start, line_end = mask.line_span(line_index)
            if line_start >= end:
                break
            raw = text[line_start:min(line_end, end)]
            if not raw.strip() or mask.fully_blocked(line_start, line_start + len(raw)):
                self.close_segment()
            else:
                offset = 0
                structural = False
                is_heading = False
                heading = _HEADING_RE.match(raw)
                quote = _BLOCKQUOTE_RE.match(raw)
                bullet = _LIST_PREFIX_RE.match(raw)
                if heading:
                    offset, structural, is_heading = heading.end(), True, True
                elif quote:
                    offset, structural = quote.end(), True
                elif bullet:
                    offset, structural = bullet.end(), True
                elif _TABLE_RE.match(raw):
                    structural = True

                for position, char in enumerate(raw[offset:]):
                    source_index = line_start + offset + position
                    if char in "*_":
                        continue
                    if char == "|" and _TABLE_RE.match(raw):
                        continue
                    if mask.blocked(source_index, source_index + 1):
                        if self.mapping and self.mapping[-1] != -1:
                            previous = text[self.mapping[-1]]
                            following = text[source_index + 1] if source_index + 1 < len(text) else ""
                            if previous.isalnum() and following.isalnum():
                                self.emit(" ", source_index)
                        continue
                    self.emit(" " if char == "\t" else char, source_index)
                if structural:
                    if is_heading and len(self.pieces) > self.segment_start:
                        self.heading_segments.append((self.segment_start, len(self.pieces)))
                    self.close_segment()
                else:
                    self.emit("\n", line_start + max(0, len(raw) - 1))
            line_index += 1

        while self.pieces and self.pieces[-1] == _HARD_BREAK:
            self.pieces.pop()
            self.mapping.pop()
        if len(self.pieces) > self.segment_start:
            self.segments.append((self.segment_start, len(self.pieces)))
        return _View(
            text="".join(self.pieces),
            index_map=self.mapping,
            segments=self.segments,
            heading_segments=self.heading_segments,
        )


def _build_view(text: str, mask: _Mask, start: int, end: int) -> _View:
    return _ViewBuilder(text, mask).build(start, end)


def _sentence_spans(text: str, *, loose: bool = False) -> list[tuple[int, int]]:
    """Offset-preserving sentence splitter mirroring ``text_parser``.

    The rules are the same (abbreviations and decimals do not end a sentence,
    the next character must start a new sentence) but the spans are returned
    instead of stripped strings, so findings keep exact offsets.

    ``loose=True`` also treats a full stop followed by whitespace as a boundary
    when the next word starts in lower case. The strict mode is used for
    readability, the loose mode for fragment, run-on and capitalisation rules,
    because "…was small. because the sample…" must still be examined as two
    units (that is exactly the error those rules look for).
    """
    from text_parser import _is_abbreviation

    boundaries: list[int] = []
    for index, char in enumerate(text[:-1]):
        if char not in ".!?":
            continue
        if char == "." and _is_abbreviation(text, index + 1):
            continue
        if (
            char == "."
            and index > 0
            and text[index - 1].isdigit()
            and text[index + 1].isdigit()
        ):
            continue
        cursor = index + 1
        while cursor < len(text) and text[cursor] in "\"”’'»)]}":
            cursor += 1
        if cursor >= len(text) or not text[cursor].isspace():
            continue
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor >= len(text):
            boundaries.append(cursor)
            continue
        following = text[cursor]
        if following.isupper() or following.isdigit() or following in '"“‘([—':
            boundaries.append(cursor)
        elif loose and following.islower():
            boundaries.append(cursor)

    spans: list[tuple[int, int]] = []
    cursor = 0
    for boundary in boundaries:
        trimmed = _trim_span(text, cursor, boundary)
        if trimmed:
            spans.append(trimmed)
        cursor = boundary
    tail = _trim_span(text, cursor, len(text))
    if tail:
        spans.append(tail)
    if not spans:
        trimmed = _trim_span(text, 0, len(text))
        if trimmed:
            spans.append(trimmed)
    return spans


def _trim_span(text: str, start: int, end: int) -> tuple[int, int] | None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if end > start else None


# --------------------------------------------------- proper-noun protection


def _widely_capitalized(text: str) -> set[str]:
    """Lower-cased words that the author capitalises away from a sentence start.

    A word a writer consistently capitalises in the middle of a sentence is
    being used as a proper noun (a surname, a village, a programme). Treating it
    as a misspelling would be the worst kind of false positive, so those words
    are protected for the whole document. The check is deliberately generous:
    it can only ever *remove* a finding, never add one.
    """
    protected: set[str] = set()
    for match in _WORD_RE.finditer(text):
        token = match.group(0)
        if not token[:1].isupper() or token.isupper():
            continue
        before = text[: match.start()]
        # Sentence start: the token follows ". ", "! ", "? ", a newline, or the
        # beginning of the document. Those positions carry no signal, because
        # every sentence starts with a capital.
        stripped = before.rstrip()
        if not stripped or stripped[-1] in ".!?\n:;\u0000" or stripped.endswith("\u2014"):
            continue
        if len(token) > 2:
            protected.add(unicodedata.normalize("NFC", token.lower()))
    return protected


# --------------------------------------------------------- protected content

_CITATION_RE = re.compile(r"\([^()]{0,160}\)")
_QUOTE_RES = (
    re.compile(r'"[^"\n]{1,400}"'),
    re.compile(r"“[^”\n]{1,400}”"),
    re.compile(r"‘[^’\n]{1,400}’"),
    re.compile(r"(?<![\w’'])'[^'\n]{1,200}'(?![\w'])"),
)


def _protected_spans(clean: str) -> list[tuple[int, int]]:
    """Citations and quotations: analysed for readability, not for spelling."""
    spans: list[tuple[int, int]] = []
    for pattern in (_CITATION_RE, *_QUOTE_RES):
        for match in pattern.finditer(clean):
            spans.append((match.start(), match.end()))
    return _merge_ranges(spans)


# ------------------------------------------------------------ spell checking


class PersonalDictionary:
    """User words that must never be flagged as misspellings."""

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            from research_library.store import default_data_dir

            path = default_data_dir() / "writing-dictionary.json"
        self.path = Path(path)

    def words(self) -> list[str]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(payload, dict):
            return []
        raw = payload.get("words")
        if not isinstance(raw, list):
            return []
        cleaned = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                cleaned.append(item.strip())
        return sorted(dict.fromkeys(cleaned), key=str.lower)

    def add(self, word: str) -> list[str]:
        word = _clean_dictionary_word(word)
        words = self.words()
        if word.lower() not in {existing.lower() for existing in words}:
            words.append(word)
        self._write(words)
        return self.words()

    def remove(self, word: str) -> list[str]:
        target = word.strip().lower()
        words = [item for item in self.words() if item.lower() != target]
        self._write(words)
        return self.words()

    def _write(self, words: Sequence[str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"words": sorted(words, key=str.lower)}, indent=2)
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", delete=False, dir=str(self.path.parent), suffix=".tmp"
        )
        try:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            handle.close()
        os.replace(handle.name, self.path)


def _clean_dictionary_word(word: str) -> str:
    if not isinstance(word, str):
        raise ValueError("A dictionary word must be text.")
    cleaned = word.strip()
    if not cleaned:
        raise ValueError("A dictionary word cannot be empty.")
    if len(cleaned) > 64:
        raise ValueError("A dictionary word must be 64 characters or fewer.")
    if not re.fullmatch(r"[^\W\d_][\w'’\-]*", cleaned, re.UNICODE):
        raise ValueError("Use only letters, apostrophes and hyphens in a dictionary word.")
    return cleaned


_SPELL_CHECKER = None


def _spell_checker():
    """Shared local dictionary; loading is lazy so the app starts instantly."""
    global _SPELL_CHECKER
    if _SPELL_CHECKER is None:
        from spellchecker import SpellChecker

        _SPELL_CHECKER = SpellChecker(language="en")
    return _SPELL_CHECKER


def spelling_engine_available() -> bool:
    try:
        _spell_checker()
    except Exception:  # pragma: no cover - only when the package is missing
        return False
    return True


def _dictionary_knows(word: str, checker) -> bool:
    """True when the word (or a British equivalent of it) is known."""
    if not checker.unknown([word]):
        return True
    for candidate in _british_equivalents(word):
        if candidate != word and not checker.unknown([candidate]):
            return True
    return False


_ALPHABET = "abcdefghijklmnopqrstuvwxyz"


def _edit_one_variants(word: str) -> set[str]:
    """All single-edit neighbours of a word (deletes, swaps, replaces, inserts)."""
    variants: set[str] = set()
    for index in range(len(word) + 1):
        left, right = word[:index], word[index:]
        if right:
            variants.add(left + right[1:])
            if len(right) > 1:
                variants.add(left + right[1] + right[0] + right[2:])
            for char in _ALPHABET:
                variants.add(left + char + right[1:])
        for char in _ALPHABET:
            variants.add(left + char + right)
    variants.discard(word)
    return variants


def _spelling_candidates(word: str, checker, limit: int = 3) -> tuple[str, ...]:
    """Suggestions from single-edit neighbours.

    ``SpellChecker.candidates()`` also explores two-edit variants and takes
    ~1.5 s per unknown word, which is far too slow to run while someone types.
    Enumerating single-edit neighbours costs a few milliseconds and catches the
    ordinary typo classes (transposition, insertion, omission, wrong letter),
    which is what a diagnostic needs; the field-term case is handled by the
    personal dictionary instead.
    """
    neighbours = _edit_one_variants(word)
    # One batched lookup instead of one call per neighbour: measurably faster
    # (~0.3 ms instead of ~0.5 ms per unknown word) and the engine leans on it
    # for every unknown word, not only the first few.
    unknown = checker.unknown(neighbours)
    known = [candidate for candidate in neighbours if candidate not in unknown]
    if not known:
        return ()

    def rank(candidate: str) -> tuple[int, str]:
        frequency = checker.word_frequency.dictionary.get(candidate, 0)
        return (-frequency, candidate)

    return tuple(sorted(known, key=rank)[:limit])


# ------------------------------------------------------------------- run state


@dataclass
class _Run:
    """State that belongs to one analysis, never to the engine as a whole."""

    profile: DiagnosticProfile = PROFILES[DEFAULT_PROFILE]
    rule_counts: dict[str, int] = field(default_factory=dict)
    spelling_stopped_early: bool = False
    # Text a more specific rule has already explained, so the general spelling
    # pass does not report the same characters a second time.
    handled_spans: set[tuple[int, int]] = field(default_factory=set)

    def threshold(self, name: str, fallback: int) -> int:
        return int(self.profile.thresholds.get(name, fallback))


# ----------------------------------------------------------------- the engine


class DiagnosticEngine:
    """Run the rule families over a document and return positioned findings."""

    def __init__(
        self,
        personal_dictionary: Iterable[str] | None = None,
        *,
        max_findings: int = MAX_FINDINGS,
        chunk_target: int = CHUNK_TARGET_CHARS,
    ) -> None:
        self.extra_words = {
            word.strip().lower() for word in (personal_dictionary or ()) if word and word.strip()
        }
        self.max_findings = max_findings
        self.chunk_target = chunk_target
        # Per-analysis state (suggestion budget, per-rule counts, profile
        # thresholds) lives on a run object so a profile cannot leak into the
        # next call. ``_lock`` serialises concurrent analyses of one engine, so
        # two requests can never interleave their run state.
        self._lock = threading.Lock()
        self._run = _Run()
        self._proper_nouns: set[str] = set()

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def categories() -> list[dict[str, str]]:
        return [
            {
                "id": name,
                "label": info["label"],
                "kind": info["kind"],
                "hint": info["hint"],
                "group": CATEGORY_GROUP.get(name, name),
                "group_label": DIAGNOSTIC_GROUPS.get(
                    CATEGORY_GROUP.get(name, name), {}
                ).get("label", name),
            }
            for name, info in CATEGORY_INFO.items()
        ]

    @staticmethod
    def profiles() -> list[dict[str, object]]:
        return [profile.to_dict() for profile in PROFILES.values()]

    @staticmethod
    def groups() -> list[dict[str, str]]:
        return [
            {"id": name, "label": info["label"]} for name, info in DIAGNOSTIC_GROUPS.items()
        ]

    def _chunks(self, text: str) -> Iterator[tuple[int, int]]:
        """Split at paragraph boundaries so long documents stay responsive."""
        start = 0
        cursor = 0
        length = len(text)
        while cursor < length:
            gap = re.search(r"\n\s*\n", text[cursor:])
            if gap is None:
                yield (start, length)
                return
            cursor += gap.end()
            if cursor - start >= self.chunk_target:
                yield (start, cursor)
                start = cursor
        if start < length:
            yield (start, length)

    def analyse(
        self,
        text: str,
        *,
        categories: Sequence[str] | None = None,
        profile: str | None = None,
        document_id: str | None = None,
        revision: int | None = None,
    ) -> dict[str, object]:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if len(text) > MAX_DOCUMENT_CHARS:
            raise ValueError(
                f"The document is longer than the {MAX_DOCUMENT_CHARS:,} character analysis limit."
            )
        active = normalize_profile(profile)
        # The profile decides which optional style categories are reported; the
        # error categories always run. An explicit ``categories`` argument
        # narrows that set further (used by clients that hide a pane).
        wanted = set(ERROR_CATEGORIES) | set(active.style_categories)
        if categories:
            wanted &= set(categories)
        unknown = set(categories or ()) - set(CATEGORY_ORDER)
        if unknown:
            raise ValueError("Unknown diagnostic categories: " + ", ".join(sorted(unknown)))

        notes: list[str] = []
        findings: list[Diagnostic] = []
        truncated = False
        if not text.strip():
            notes.append("The document is empty, so there is nothing to check yet.")

        checker = None
        if "spelling" in wanted:
            try:
                checker = _spell_checker()
            except Exception:  # pragma: no cover - dependency missing
                notes.append(
                    "The local spelling dictionary is unavailable, so spelling was not checked. "
                    "Install the 'pyspellchecker' package to enable it."
                )

        with self._lock:
            self._run = _Run(profile=active)
            self._proper_nouns = _widely_capitalized(text)
            mask = _Mask(text)
            metrics_context: list[str] = []
            for chunk_start, chunk_end in self._chunks(text):
                view = _build_view(text, mask, chunk_start, chunk_end)
                if not view.text.strip():
                    continue
                protected = _protected_spans(view.text)
                metrics_context.append(view.text)
                findings.extend(self._analyse_chunk(view, protected, mask, wanted, checker))
                if len(findings) > self.max_findings * 2:
                    truncated = True
                    break
            findings.sort(key=Diagnostic.sort_key)
            if len(findings) > self.max_findings:
                truncated = True
                findings = findings[: self.max_findings]
            rule_counts = dict(self._run.rule_counts)
            stopped_early = self._run.spelling_stopped_early
        if any(count >= MAX_FINDINGS_PER_RULE for count in rule_counts.values()):
            # A single rule hit its cap, so the report is not exhaustive.
            truncated = True
        if stopped_early:
            # Spelling stopped examining the document part-way through.
            truncated = True
            notes.append(
                "Spelling stopped examining this document after "
                f"{MAX_BARREN_SPELLING_WORDS} more unknown words produced no finding, "
                "so the results are not a complete list for the whole text."
            )

        counts = {"error": 0, "style": 0}
        by_category: dict[str, int] = {}
        by_group: dict[str, int] = {}
        for finding in findings:
            counts[finding.kind] = counts.get(finding.kind, 0) + 1
            by_category[finding.category] = by_category.get(finding.category, 0) + 1
            by_group[finding.group] = by_group.get(finding.group, 0) + 1
        for category in CATEGORY_ORDER:
            by_category.setdefault(category, 0)
        for group in GROUP_ORDER:
            by_group.setdefault(group, 0)

        if not findings and text.strip():
            notes.append(
                "No findings. Every checked passage passed the local rules for the "
                "categories you selected."
            )
        if truncated:
            notes.append(
                f"Only the first {self.max_findings} findings are shown for this document."
            )

        return {
            "document_id": document_id,
            "revision": revision,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "characters": len(text),
            "diagnostics": [finding.to_dict(active) for finding in findings],
            "counts": {
                "total": len(findings),
                "error": counts.get("error", 0),
                "style": counts.get("style", 0),
                "by_category": by_category,
                "by_group": by_group,
            },
            "metrics": self._metrics("\n\n".join(metrics_context)),
            "categories": self.categories(),
            "notes": notes,
            "truncated": truncated,
            "profile": active.to_dict(),
            "engine": {
                "name": ENGINE_NAME,
                "version": ENGINE_VERSION,
                "ruleset_version": RULESET_VERSION,
                "spelling": (
                    "pyspellchecker 0.8.2 (MIT), bundled dictionary"
                    if checker is not None
                    else "unavailable"
                ),
                "spelling_available": checker is not None,
                "external_services": "none",
                "checked_categories": sorted(wanted),
            },
        }

    # -- metrics ----------------------------------------------------------

    @staticmethod
    def _metrics(text: str) -> dict[str, object]:
        words = _WORD_RE.findall(text)
        sentences = _sentence_spans(text)
        paragraphs = [block for block in re.split(r"\n\s*\n", text) if block.strip()]
        word_count = len(words)
        sentence_count = len(sentences) or (1 if word_count else 0)
        syllables = sum(_syllables(word) for word in words) or 1
        if word_count:
            flesch = 206.835 - 1.015 * (word_count / sentence_count) - 84.6 * (
                syllables / word_count
            )
        else:
            flesch = 0.0
        longest = max((len(_WORD_RE.findall(block)) for block in paragraphs), default=0)
        return {
            "words": word_count,
            "sentences": sentence_count,
            "paragraphs": len(paragraphs),
            "reading_time_minutes": round(word_count / 200, 1),
            "average_sentence_words": round(word_count / sentence_count, 1) if word_count else 0.0,
            "longest_paragraph_words": longest,
            "flesch_reading_ease": round(max(0.0, min(100.0, flesch)), 1),
        }

    # -- rule families ----------------------------------------------------

    def _analyse_chunk(
        self,
        view: _View,
        protected: Sequence[tuple[int, int]],
        mask: _Mask,
        wanted: set[str],
        checker,
    ) -> list[Diagnostic]:
        clean = view.text
        found: list[Diagnostic] = []
        rule_counts: dict[str, int] = self._run.rule_counts

        def add(
            rule: str,
            category: str,
            message: str,
            explanation: str,
            clean_start: int,
            clean_end: int,
            replacements: Sequence[str] = (),
            confidence: str = "high",
            kind_override: str | None = None,
        ) -> None:
            if category not in wanted:
                return
            if rule_counts.get(rule, 0) >= MAX_FINDINGS_PER_RULE:
                return
            original_start, original_end = view.original_span(clean_start, clean_end)
            original = mask.text[original_start:original_end]
            if not original:
                return
            kind = kind_override or CATEGORY_INFO[category]["kind"]
            replacements = tuple(r for r in replacements if r != original)
            rule_counts[rule] = rule_counts.get(rule, 0) + 1
            found.append(
                Diagnostic(
                    rule=rule,
                    category=category,
                    kind=kind,
                    confidence=confidence,
                    message=message,
                    explanation=explanation,
                    start=original_start,
                    end=original_end,
                    original=original,
                    replacements=replacements,
                )
            )

        # Contractions run first: "dont" is a punctuation fault, not a spelling
        # one, and the spelling pass must not report the same word twice.
        self._apostrophe_rules(clean, protected, add)
        if "spelling" in wanted and checker is not None:
            self._spelling_rules(clean, protected, checker, add)
        self._article_rules(clean, protected, add)
        self._punctuation_rules(clean, protected, add)
        self._capitalization_rules(clean, protected, add, view.heading_segments)
        self._tone_rules(clean, protected, add)
        self._wordiness_rules(clean, protected, add)
        self._usage_rules(clean, protected, add)
        self._clarity_rules(clean, protected, add)
        self._repetition_rules(clean, add)
        self._sentence_rules(clean, protected, add)
        return _drop_contained(found)

    # -- spelling ---------------------------------------------------------

    def _part_is_acceptable(self, part: str, checker) -> bool:
        if len(part) < SPELLING_MIN_WORD_LENGTH:
            return True
        if part in self.extra_words or part in STOPWORDS or part in _ACADEMIC_TERMS:
            return True
        if is_protected_word(part):
            return True
        return _dictionary_knows(part, checker)

    def _spelling_rules(self, clean: str, protected, checker, add) -> None:
        """Report unknown words, and distinguish a typo from an unfamiliar word.

        Deciding a word is misspelled is the most intrusive thing this engine
        does, so it is deliberately conservative:

        * a word the author capitalises mid-sentence anywhere in the document is
          treated as a proper noun and never touched;
        * the bundled protection vocabulary (names, caste and community terms,
          place names, field concepts, survey abbreviations) is checked first;
        * a token that looks like an abbreviation, carries digits, is written in
          another script, or builds out of known parts is left alone;
        * a finding becomes a confident *misspelling* with a replacement only
          when an ordinary one-edit neighbour exists in the dictionary. Without
          such a neighbour the word is reported as *unknown* with **no**
          replacement offered, because an unfamiliar word is not an error.
        """
        seen: set[tuple[int, int]] = set()
        barren = 0
        for match in _WORD_RE.finditer(clean):
            if barren >= MAX_BARREN_SPELLING_WORDS:
                self._run.spelling_stopped_early = True
                break
            raw = match.group(0)
            start, end = match.start(), match.end()
            if (start, end) in seen:
                continue
            seen.add((start, end))
            if any(span_start <= start < span_end for span_start, span_end in protected):
                continue
            if (start, end) in self._run.handled_spans:
                # A contraction rule already explained this word.
                continue
            if any(char.isdigit() for char in raw):
                continue
            if not re.search(r"[A-Za-z]", raw):
                # The bundled dictionary is English; words written in another
                # script (or transliterated symbols) are not "misspellings".
                continue
            if looks_like_acronym(raw):
                continue
            capitalized = raw[:1].isupper() and not raw.isupper()
            word = unicodedata.normalize("NFC", raw.lower())
            if len(word) < SPELLING_MIN_WORD_LENGTH:
                continue
            if is_protected_word(word, capitalized=capitalized):
                continue
            if word in self._proper_nouns:
                # Capitalised in the middle of a sentence somewhere in this
                # document: a name, not a typo.
                continue
            parts = [part for part in re.split(r"['’\-]", word) if part]
            if len(parts) > 1:
                # A compound is only a misspelling if one of its words is.
                if all(self._part_is_acceptable(part, checker) for part in parts):
                    continue
            elif self._part_is_acceptable(word, checker):
                continue
            before_count = sum(self._run.rule_counts.get(name, 0) for name in SPELLING_RULES)
            candidates = _spelling_candidates(word, checker)

            if candidates:
                # A one-edit neighbour exists, so this is very likely a typo.
                # A capitalised token is still reported more cautiously: it
                # could be an unfamiliar name the author has not used twice.
                rule = "spelling.misspelling"
                confidence = "high" if not capitalized else "medium"
                suggestion = f" Did you mean \"{candidates[0]}\"?"
                message = f"\"{raw}\" looks like a misspelling.{suggestion}"
                explanation = (
                    "The local dictionary has no such word, but it is one letter "
                    "away from a common word. If this is a name or a term from your "
                    "field, add it to your personal dictionary instead."
                )
                if capitalized:
                    explanation += (
                        " A word that starts a sentence is also how a proper name "
                        "can appear, so check before accepting."
                    )
            elif capitalized:
                # A word the author capitalised, with no dictionary neighbour:
                # read it as a name and say nothing. Flagging every unfamiliar
                # proper noun is the fastest way to make a checker useless.
                continue
            else:
                rule = "spelling.unknown-word"
                confidence = "medium"
                message = f"\"{raw}\" is not in the local dictionary."
                explanation = (
                    "No obvious correction was found, so nothing is suggested: an "
                    "unfamiliar word is not necessarily wrong. If it is a name, a "
                    "caste or community term, a place or a term from your field, add "
                    "it to your personal dictionary and it will not be flagged again."
                )
            add(
                rule,
                "spelling",
                message,
                explanation,
                start,
                end,
                candidates,
                confidence=confidence,
            )
            if self._run.rule_counts.get(rule, 0) > before_count:
                barren = 0
            else:
                barren += 1

    # -- punctuation and capitalization -----------------------------------

    def _punctuation_rules(self, clean: str, protected, add) -> None:
        def inside_protected(start: int, end: int) -> bool:
            return any(s <= start and end <= span_end for s, span_end in protected)

        for match in re.finditer(r"[ \t]+([,.;:!?])", clean):
            punctuation = match.group(1)
            if inside_protected(match.start(), match.end()):
                continue
            if punctuation == "." and match.start() > 0 and clean[match.start() - 1].isdigit():
                continue
            if clean[match.end() - 1] == "." and match.end() < len(clean) and clean[match.end()].isdigit():
                continue  # decimal written with a space must not be "fixed" blindly
            add(
                "punctuation.space-before-mark",
                "punctuation",
                f"Extra space before \"{punctuation}\".",
                "Remove the space so the mark sits directly after the word.",
                match.start(),
                match.end(),
                (punctuation,),
            )

        for match in re.finditer(r"([,;:])(?=[A-Za-z])", clean):
            if inside_protected(match.start(), match.end()):
                continue
            add(
                "punctuation.missing-space",
                "punctuation",
                f"Missing space after \"{match.group(1)}\".",
                "Add a space after the mark.",
                match.start(),
                match.end(),
                (match.group(1) + " ",),
                confidence="medium",
            )

        for match in re.finditer(r"([.!?])(?=[A-Z])", clean):
            if inside_protected(match.start(), match.end()):
                continue
            if clean[max(0, match.start() - 1)].isupper() and (
                match.start() < 2 or not clean[match.start() - 2].isalpha()
            ):
                continue  # initials such as "R.Singh"
            if match.group(1) == "." and _looks_like_abbreviation(clean, match.end()):
                continue
            add(
                "punctuation.missing-space",
                "punctuation",
                f"Missing space after \"{match.group(1)}\".",
                "Add a space so the next sentence does not run into this one.",
                match.start(),
                match.end(),
                (match.group(1) + " ",),
                confidence="medium",
            )

        for match in re.finditer(r"([,;:])[,;:]+", clean):
            add(
                "punctuation.doubled-mark",
                "punctuation",
                "Repeated punctuation mark.",
                "Keep a single mark.",
                match.start(),
                match.end(),
                (match.group(1),),
            )

        for match in re.finditer(r"\.{2}(?!\.)", clean):
            add(
                "punctuation.doubled-mark",
                "punctuation",
                "Two full stops where one is intended.",
                "Use one full stop, or three for an ellipsis.",
                match.start(),
                match.end(),
                (".", "…"),
                confidence="medium",
            )

        self._bracket_rules(clean, add, inside_protected)

    def _bracket_rules(self, clean: str, add, inside_protected) -> None:
        stack: list[tuple[str, int]] = []
        pairs = {")": "(", "]": "["}
        for index, char in enumerate(clean):
            if char in "([":
                stack.append((char, index))
            elif char in ")]":
                if stack and stack[-1][0] == pairs[char]:
                    stack.pop()
                else:
                    add(
                        "punctuation.unmatched-bracket",
                        "punctuation",
                        f"Closing \"{char}\" without an opening bracket.",
                        "Remove it or add the matching opening bracket.",
                        index,
                        index + 1,
                        (),
                        confidence="medium",
                    )
        for opener, index in stack:
            add(
                "punctuation.unclosed-bracket",
                "punctuation",
                f"Unclosed \"{opener}\".",
                "Close the bracket or remove it.",
                index,
                index + 1,
                (),
                confidence="medium",
            )

    def _capitalization_rules(
        self, clean: str, protected, add, heading_segments: Sequence[tuple[int, int]] = ()
    ) -> None:
        def inside_protected(start: int, end: int) -> bool:
            return any(s <= start and end <= span_end for s, span_end in protected)

        for match in re.finditer(r"\bi\b", clean):
            if inside_protected(match.start(), match.end()):
                continue
            add(
                "capitalization.pronoun-i",
                "capitalization",
                "The pronoun \"i\" must be capitalized.",
                "Use \"I\".",
                match.start(),
                match.end(),
                ("I",),
            )

        for match in re.finditer(r"\b[a-z]{2,}\b", clean):
            if match.group(0) not in CAPITALIZED_TERMS:
                continue
            if inside_protected(match.start(), match.end()):
                continue
            add(
                "capitalization.proper-adjective",
                "capitalization",
                f"\"{match.group(0)}\" is normally capitalized.",
                "Capitalize languages, nationalities, months and weekdays.",
                match.start(),
                match.end(),
                (match.group(0)[0].upper() + match.group(0)[1:],),
            )

        for start, end, _opens_block in self._segment_sentences(clean):
            sentence = clean[start:end]
            first = re.search(r"[A-Za-z]", sentence)
            if not first or len(_WORD_RE.findall(sentence)) < 3:
                continue
            letter = start + first.start()
            if heading_segments and any(span_start <= letter < span_end for span_start, span_end in heading_segments):
                continue  # heading case is a layout choice, not a language error
            if inside_protected(letter, letter + 1):
                continue
            if clean[letter].islower():
                add(
                    "capitalization.sentence-start",
                    "capitalization",
                    "A sentence starts with a lower-case letter.",
                    "Capitalize the first word of the sentence.",
                    letter,
                    letter + 1,
                    (clean[letter].upper(),),
                    confidence="medium",
                )

    # -- contractions, articles, usage ------------------------------------

    def _apostrophe_rules(self, clean: str, protected, add) -> None:
        """Missing apostrophes in the contractions academic prose still uses.

        Only a closed list of unambiguous forms is handled. Possessives
        ("students" vs "students'") and homophones ("its" vs "it's") are left
        alone because deciding them needs the sentence's meaning, and a rule
        that guesses would be worse than no rule. Every span it reports is
        claimed so the spelling pass does not also call the word unknown.
        """
        for form, expansion in MISSING_APOSTROPHE_FORMS.items():
            for match in re.finditer(rf"\b{re.escape(form)}\b", clean.lower()):
                start, end = match.start(), match.end()
                if any(span_start <= start < span_end for span_start, span_end in protected):
                    continue
                original = clean[start:end]
                self._run.handled_spans.add((start, end))
                replacement = _match_case(original, expansion)
                add(
                    "punctuation.missing-apostrophe",
                    "punctuation",
                    f"\"{original}\" is missing its apostrophe.",
                    f"Write \"{replacement}\" in academic prose. This is the "
                    "contraction spelled out or punctuated.",
                    start,
                    end,
                    (replacement,),
                    confidence="high" if form not in HOMOPHONE_APOSTROPHE_FORMS else "medium",
                )

    def _article_rules(self, clean: str, protected, add) -> None:
        """`a` / `an` chosen by sound, with the exceptions that matter.

        Two sound classes are the whole difficulty: words spelled with a vowel
        that begin with a consonant sound ("a university", "a European") and
        words spelled with a silent h ("an hour"). Abbreviations are skipped
        entirely, because "an MBA" and "a UN report" are both correct and the
        letter does not tell you which sound it takes.
        """
        pattern = re.compile(r"\b(a|an|A|An|AN)\s+([A-Za-z][\w’'\-]*)")
        for match in pattern.finditer(clean):
            article, following = match.group(1), match.group(2)
            start, end = match.start(1), match.start(1) + len(article)
            if any(span_start <= start < span_end for span_start, span_end in protected):
                continue
            if looks_like_acronym(following):
                # "an MBA", "a UN report": the letter does not tell you the sound.
                continue
            lowered = following.lower()
            lowered_article = article.lower()
            head = lowered.split("-")[0]
            if lowered.startswith(CONSONANT_SOUND_VOWELS) or head in SILENT_H_WORDS or (
                lowered in SILENT_H_WORDS
            ):
                sound = "vowel" if head in SILENT_H_WORDS or lowered in SILENT_H_WORDS else "consonant"
            elif lowered[:1] in "aeiou":
                sound = "vowel"
            else:
                sound = "consonant"
            expected = "an" if sound == "vowel" else "a"
            if lowered_article == expected:
                continue
            replacement = _match_case(article, expected)
            # Letter-based cases are unambiguous; u- and h- words depend on the
            # sound, and style guides differ about a few of them.
            ambiguous = lowered[:1] in {"u", "h"}
            add(
                "grammar.article-an",
                "agreement",
                f"Use \"{replacement}\" before \"{following}\".",
                f"\"{following}\" begins with a {sound} sound, so the article is "
                f"\"{expected}\". The choice follows the sound, not the spelling.",
                start,
                end,
                (replacement,),
                confidence="medium" if ambiguous else "high",
            )

    def _usage_rules(self, clean: str, protected, add) -> None:
        """High-precision usage faults: mass nouns and redundant prepositions.

        Both families are small on purpose. Each entry is a phrase whose
        correction no style guide disputes, and each one is reported at medium
        confidence, because a checker that argues about debatable usage loses a
        writer's trust faster than one that stays quiet.
        """
        for form, correction in MASS_NOUN_PLURALS.items():
            for match in re.finditer(rf"\b{form}\b", clean.lower()):
                start, end = match.start(), match.end()
                if any(span_start <= start < span_end for span_start, span_end in protected):
                    continue
                original = clean[start:end]
                replacement = _match_case(original, correction)
                add(
                    "grammar.mass-noun-plural",
                    "agreement",
                    f"\"{original}\" is not used as a plural in academic English.",
                    f"The uncountable noun takes no plural here; write "
                    f"\"{replacement}\" or count it explicitly (\"two findings\").",
                    start,
                    end,
                    (replacement,),
                    confidence="high",
                )

        for phrase, correction in REDUNDANT_PREPOSITIONS.items():
            for match in re.finditer(rf"\b{re.escape(phrase)}\b", clean.lower()):
                start, end = match.start(), match.end()
                if any(span_start <= start < span_end for span_start, span_end in protected):
                    continue
                original = clean[start:end]
                replacement = _match_case(original, correction)
                add(
                    "grammar.redundant-preposition",
                    "agreement",
                    f"\"{original}\" carries a preposition the verb does not take.",
                    f"Write \"{replacement}\": the verb is already transitive, so the "
                    "preposition is redundant rather than optional.",
                    start,
                    end,
                    (replacement,),
                    confidence="medium",
                )

    def _clarity_rules(self, clean: str, protected, add) -> None:
        """A bare "This shows..." opener, the commonest ambiguity in a draft.

        The pronoun is not wrong, but in a long argument the reader cannot tell
        what it points at. No replacement is offered, because the fix is the
        author's noun, not a phrase the engine can invent.
        """
        pattern = re.compile(
            r"(?:(?<=^)|(?<=[.!?]\s)|(?<=\u0000)|(?<=\n))\s*(This|this|Which|which)\s+"
            r"(is|are|was|were|shows|show|suggests|suggest|means|mean|implies|imply|"
            r"indicates|indicate|reflects|reflect|explains|explain|demonstrates|demonstrate)"
        )
        for match in pattern.finditer(clean):
            start, end = match.start(1), match.end(1)
            if any(span_start <= start < span_end for span_start, span_end in protected):
                continue
            add(
                "clarity.ambiguous-this",
                "readability",
                f"\"{clean[start:end]}\" does not name what it refers to.",
                "Optional: add the noun it stands for (\"This pattern shows...\", "
                "\"This finding suggests...\"). No replacement is offered, because the "
                "engine cannot know which noun you mean.",
                start,
                end,
                (),
                confidence="low",
            )

    # -- tone, wordiness, repetition --------------------------------------

    def _tone_rules(self, clean: str, protected, add) -> None:
        lower = clean.lower()
        for contraction, expansion in CONTRACTIONS:
            for match in re.finditer(rf"\b{re.escape(contraction)}\b", lower):
                if _inside(match.start(), protected):
                    continue
                add(
                    "tone.contraction",
                    "tone",
                    f"\"{clean[match.start():match.end()]}\" is informal for academic prose.",
                    "Optional: expand the contraction for a more formal register. "
                    "Quotations and direct speech are excluded.",
                    match.start(),
                    match.end(),
                    (_capitalize_at_sentence_start(clean, match.start(), expansion),),
                    confidence="medium",
                )

        for phrase, suggestion in VAGUE_QUANTIFIERS:
            for match in re.finditer(rf"\b{re.escape(phrase)}\b", lower):
                if _inside(match.start(), protected):
                    continue
                add(
                    "tone.vague-quantifier",
                    "tone",
                    f"\"{phrase.capitalize()}\" is vague for an academic claim.",
                    "Optional: state the quantity or scale explicitly"
                    + (f", for example \"{suggestion}\"." if suggestion else "."),
                    match.start(),
                    match.end(),
                    (suggestion,) if suggestion else (),
                    confidence="medium",
                )

        for word in OVERCLAIM_WORDS:
            pattern = rf"\b{re.escape(word)}\b"
            for match in re.finditer(pattern, lower):
                if _inside(match.start(), protected):
                    continue
                add(
                    "tone.overclaim",
                    "tone",
                    f"\"{clean[match.start():match.end()]}\" is a strong claim.",
                    "Optional: check that the evidence supports this strength. "
                    "Hedging language such as \"often\" or \"suggests\" is usually safer "
                    "in academic writing. Changing this would change your meaning, so no "
                    "replacement is offered.",
                    match.start(),
                    match.end(),
                    (),
                    confidence="medium",
                )

    def _wordiness_rules(self, clean: str, protected, add) -> None:
        lower = clean.lower()
        for phrase, replacement in WORDINESS_REPLACEMENTS:
            for match in re.finditer(rf"\b{re.escape(phrase)}\b", lower):
                if _inside(match.start(), protected):
                    continue
                add(
                    "wordiness.longer-phrase",
                    "wordiness",
                    f"\"{clean[match.start():match.end()]}\" can be shorter.",
                    f"Optional: \"{replacement}\" says the same thing. Your argument and "
                    "terminology are unchanged.",
                    match.start(),
                    match.end(),
                    (_capitalize_at_sentence_start(clean, match.start(), replacement),),
                )

        for phrase in FORMULAIC_REMOVALS:
            for match in re.finditer(rf"\b{re.escape(phrase)}[ ,]*", lower):
                if _inside(match.start(), protected):
                    continue
                start, end, replacement = _removal_replacement(clean, match.start(), match.end())
                add(
                    "wordiness.formulaic-opener",
                    "wordiness",
                    "Formulaic opening that adds no information.",
                    "Optional: start with the substance of the sentence. "
                    "Your claim and citations are unchanged.",
                    start,
                    end,
                    (replacement,) if replacement else (),
                    confidence="medium",
                )

    def _repetition_rules(self, clean: str, add) -> None:
        tokens = list(_WORD_RE.finditer(clean))
        words = [match.group(0).lower() for match in tokens]

        for previous, current in zip(range(len(words)), range(1, len(words))):
            if words[previous] == words[current] and len(words[current]) > 1:
                match = tokens[current]
                add(
                    "repetition.immediate",
                    "repetition",
                    f"\"{match.group(0)}\" is repeated.",
                    "Optional: remove the duplicate word.",
                    match.start(),
                    match.end(),
                    (),
                    confidence="high",
                )

        counts: dict[str, list[int]] = {}
        for index, word in enumerate(words):
            if len(word) < 5 or word in STOPWORDS or word in _ACADEMIC_TERMS:
                continue
            counts.setdefault(word, []).append(index)

        word_total = max(1, len(words))
        for word, indexes in sorted(counts.items()):
            if len(indexes) < 4:
                continue
            if len(indexes) / word_total < 0.02:
                continue
            for index in indexes[2:7]:
                match = tokens[index]
                add(
                    "repetition.overused-word",
                    "repetition",
                    f"\"{match.group(0)}\" appears {len(indexes)} times in this passage.",
                    "Optional: vary the wording where it does not change your terminology.",
                    match.start(),
                    match.end(),
                    (),
                    confidence="medium",
                )

        for phrase, indexes in _repeated_phrases(words).items():
            for index in indexes[:4]:
                match = tokens[index]
                end = tokens[min(index + 1, len(tokens) - 1)]
                add(
                    "repetition.overused-phrase",
                    "repetition",
                    f"The phrase \"{phrase}\" is used {len(indexes)} times in this passage.",
                    "Optional: vary the phrasing, or keep it if the repetition is deliberate.",
                    match.start(),
                    end.end(),
                    (),
                    confidence="medium",
                )

    # -- sentences --------------------------------------------------------

    def _segment_sentences(
        self, clean: str, *, loose: bool = True
    ) -> list[tuple[int, int, bool]]:
        """Sentences with their spans and whether they open a paragraph block."""
        spans: list[tuple[int, int, bool]] = []
        for block in re.finditer(r"[^\n\u0000]+(?:\n(?!\n)[^\n\u0000]+)*", clean):
            offset = block.start()
            for position, (start, end) in enumerate(_sentence_spans(block.group(0), loose=loose)):
                spans.append((offset + start, offset + end, position == 0))
        return spans

    def _sentence_rules(self, clean: str, protected, add) -> None:
        sentences = self._segment_sentences(clean, loose=True)
        readability_sentences = {
            (start, end) for start, end, _ in self._segment_sentences(clean, loose=False)
        }
        for start, end, opens_block in sentences:
            sentence = clean[start:end]
            sentence_protected = [
                (span_start - start, span_end - start)
                for span_start, span_end in protected
                if span_start < end and span_end > start
            ]
            words = _WORD_RE.findall(sentence)
            if not words:
                continue

            long_sentence = self._run.threshold("long_sentence_words", LONG_SENTENCE_WORDS)
            if (start, end) in readability_sentences and len(words) >= long_sentence:
                add(
                    "readability.long-sentence",
                    "readability",
                    f"This sentence is {len(words)} words long.",
                    "Optional: split it so the main claim is easier to follow. "
                    "No replacement is offered because splitting a sentence changes "
                    "how your argument is presented.",
                    start,
                    end,
                    (),
                    confidence="high",
                )

            if not opens_block and _looks_like_fragment(sentence, words):
                add(
                    "fragment.no-main-clause",
                    "fragment",
                    "This group of words has no main clause.",
                    "Join it to the previous sentence, or add a subject and a finite verb. "
                    "Deliberate stylistic fragments are common in some fields, so this is "
                    "reported at medium confidence.",
                    start,
                    end,
                    (),
                    confidence="medium",
                )
                continue

            splice = _comma_splice(sentence, sentence_protected)
            if splice is not None:
                position = start + splice
                add(
                    "run_on.comma-splice",
                    "run_on",
                    "Two clauses are joined by a comma without a conjunction.",
                    "Use a semicolon, a full stop, or add a conjunction such as \"and\". "
                    "This is reported at medium confidence because comma use varies "
                    "between style guides.",
                    position,
                    position + 1,
                    (";", ". And", ", and"),
                    confidence="medium",
                )

        for block in re.finditer(r"[^\n\u0000]+(?:\n(?!\n)[^\n\u0000]+)*", clean):
            words = _WORD_RE.findall(block.group(0))
            if len(words) < self._run.threshold("long_paragraph_words", LONG_PARAGRAPH_WORDS):
                continue
            add(
                "readability.long-paragraph",
                "readability",
                f"This paragraph is {len(words)} words long.",
                "Optional: split it into shorter paragraphs. No replacement is offered.",
                block.start(),
                block.end(),
                (),
                confidence="high",
            )

        self._agreement_rules(clean, protected, add)

    # -- agreement --------------------------------------------------------

    def _agreement_rules(self, clean: str, protected, add) -> None:
        def flagged(start: int, end: int) -> bool:
            return _inside(start, protected) or _inside(end - 1, protected)

        for hit in _there_is_plural_spans(clean):
            noun = hit.noun.lower()
            if noun in SINGULAR_S_WORDS or noun in _ACADEMIC_TERMS:
                continue
            if noun.endswith(("ss", "us", "is", "ics", "ness", "ysis")):
                continue
            if flagged(hit.verb_start, hit.verb_end):
                continue
            verb = hit.verb.lower()
            replacement = {"is": "are", "was": "were", "has": "have", "does": "do"}[verb]
            if clean[hit.verb_start].isupper():
                replacement = replacement.capitalize()
            add(
                "agreement.plural-subject",
                "agreement",
                f"\"{noun}\" is plural, but the verb \"{verb}\" is singular.",
                f"Use \"{replacement}\".",
                hit.verb_start,
                hit.verb_end,
                (replacement,),
                confidence="medium",
            )

        for match in re.finditer(
            r"\b(these|those)\s+(is|was|has|does)\b", clean, re.IGNORECASE
        ):
            if flagged(match.start(2), match.end(2)):
                continue
            verb = match.group(2).lower()
            replacement = {"is": "are", "was": "were", "has": "have", "does": "do"}[verb]
            add(
                "agreement.demonstrative",
                "agreement",
                f"\"{match.group(1)}\" is plural, but \"{verb}\" is singular.",
                f"Use \"{replacement}\".",
                match.start(2),
                match.end(2),
                (replacement,),
                confidence="medium",
            )

        for match in re.finditer(r"\b(this|that)\s+(are|were)\b", clean, re.IGNORECASE):
            if flagged(match.start(2), match.end(2)):
                continue
            verb = match.group(2).lower()
            replacement = {"are": "is", "were": "was"}[verb]
            add(
                "agreement.demonstrative",
                "agreement",
                f"\"{match.group(1)}\" is singular, but \"{verb}\" is plural.",
                f"Use \"{replacement}\".",
                match.start(2),
                match.end(2),
                (replacement,),
                confidence="medium",
            )

        for match in re.finditer(
            r"\b(each|every|either|neither)\s+of\b[^.;!?]{0,40}?\b(are|were|have|do)\b",
            clean,
            re.IGNORECASE,
        ):
            if flagged(match.start(2), match.end(2)):
                continue
            verb = match.group(2).lower()
            replacement = {"are": "is", "were": "was", "have": "has", "do": "does"}[verb]
            add(
                "agreement.indefinite-pronoun",
                "agreement",
                f"\"{match.group(1)} of ...\" takes a singular verb, not \"{verb}\".",
                f"Use \"{replacement}\".",
                match.start(2),
                match.end(2),
                (replacement,),
                confidence="medium",
            )

        for match in re.finditer(
            r"\b(people|scholars|researchers|authors|participants|respondents|students)\s+"
            r"(is|was|has|does)\b",
            clean,
            re.IGNORECASE,
        ):
            if flagged(match.start(2), match.end(2)):
                continue
            verb = match.group(2).lower()
            replacement = {"is": "are", "was": "were", "has": "have", "does": "do"}[verb]
            add(
                "agreement.plural-subject",
                "agreement",
                f"\"{match.group(1)}\" is plural, but the verb \"{verb}\" is singular.",
                f"Use \"{replacement}\".",
                match.start(2),
                match.end(2),
                (replacement,),
                confidence="medium",
            )

        for match in re.finditer(r"\b(a|an)\s+([A-Za-z]{4,}(?:s|ies))\b", clean, re.IGNORECASE):
            noun = match.group(2).lower()
            if noun in SINGULAR_S_WORDS:
                continue
            if noun.endswith(("ss", "us", "is", "ics", "ness", "ysis", "sis")):
                continue
            if flagged(match.start(2), match.end(2)):
                continue
            add(
                "agreement.article-with-plural",
                "agreement",
                f"\"{noun}\" is plural, so \"{match.group(1)}\" does not fit.",
                "Remove the article or make the noun singular.",
                match.start(),
                match.end(),
                (match.group(2),),
                confidence="medium",
            )

        # Convention, not an error: both conventions are used in academic prose.
        for match in re.finditer(
            r"\b(data|criteria|phenomena|analyses|media|curricula)\s+(is|was|has)\b",
            clean,
            re.IGNORECASE,
        ):
            if flagged(match.start(2), match.end(2)):
                continue
            add(
                "agreement.latin-plural-convention",
                "agreement",
                f"\"{match.group(1)}\" is a Latin plural treated as singular here.",
                "Style choice, not an error: many style guides accept \"data is\". "
                "Use the plural form if your target journal follows the strict convention.",
                match.start(1),
                match.end(2),
                (),
                confidence="low",
                kind_override="style",
            )


# ------------------------------------------------------------ rule utilities


def _drop_contained(findings: Sequence[Diagnostic]) -> list[Diagnostic]:
    """Remove a finding that another finding of the same rule fully contains.

    Findings are grouped by rule and ordered by position with the longest first,
    so a containment check only has to look at the previous kept finding: the
    comparison stays O(n log n) instead of the quadratic scan that made a
    document with thousands of repeated words take seconds (found by the
    pathological-input regression test).
    """
    by_rule: dict[str, list[Diagnostic]] = {}
    for finding in findings:
        by_rule.setdefault(finding.rule, []).append(finding)
    kept: list[Diagnostic] = []
    for items in by_rule.values():
        items.sort(key=lambda item: (item.start, -(item.end - item.start)))
        previous: Diagnostic | None = None
        for finding in items:
            if previous is not None and finding.end <= previous.end:
                continue  # contained in the finding already kept
            kept.append(finding)
            previous = finding
    kept.sort(key=Diagnostic.sort_key)
    return kept


def _inside(position: int, spans: Sequence[tuple[int, int]]) -> bool:
    for start, end in spans:
        if start > position:
            return False
        if start <= position < end:
            return True
    return False


def _looks_like_abbreviation(clean: str, position: int) -> bool:
    start = position
    while start > 0 and (clean[start - 1].isalnum() or clean[start - 1] in "."):
        start -= 1
    token = clean[start:position]
    return len(token) <= 5 and token.endswith(".") and token[:-1].isalpha()


def _syllables(word: str) -> int:
    word = word.lower()
    groups = re.findall(r"[aeiouy]+", word)
    count = len(groups)
    if word.endswith("e") and not word.endswith(("le", "ee")) and count > 1:
        count -= 1
    return max(1, count)


def _starts_sentence(clean: str, start: int) -> bool:
    cursor = start - 1
    while cursor >= 0 and clean[cursor] in " \t\n\u0000":
        cursor -= 1
    return cursor < 0 or clean[cursor] in ".!?:;\u0000"


def _capitalize_at_sentence_start(clean: str, start: int, replacement: str) -> str:
    """A replacement must not introduce a lower-case sentence start."""
    if replacement and _starts_sentence(clean, start):
        return replacement[0].upper() + replacement[1:]
    return replacement


def _removal_replacement(clean: str, start: int, end: int) -> tuple[int, int, str]:
    """Remove a phrase, keeping the sentence capitalised and spaced correctly."""
    while end < len(clean) and clean[end] in " ,":
        end += 1
    if end < len(clean) and clean[end].islower() and start == 0:
        return (start, end + 1, clean[end].upper())
    return (start, end, "")


def _repeated_phrases(words: Sequence[str]) -> dict[str, list[int]]:
    phrases: dict[str, list[int]] = {}
    significant = [
        (index, word)
        for index, word in enumerate(words)
        if len(word) >= 4 and word not in STOPWORDS
    ]
    bigrams: dict[str, list[int]] = {}
    for (index, word), (next_index, next_word) in zip(significant, significant[1:]):
        if next_index != index + 1:
            continue
        bigrams.setdefault(f"{word} {next_word}", []).append(index)
    for phrase, indexes in bigrams.items():
        if len(indexes) >= 3:
            phrases[phrase] = indexes
    return phrases


NON_VERB_ED_WORDS = frozenset(
    """
    limited based related detailed varied noted selected used derived called expected
    supposed interested advanced developed connected isolated oriented situated
    """.split()
)


def _is_finite_verb(word: str) -> bool:
    """Approximate finite-verb test used by the medium-confidence rules."""
    word = word.lower()
    if word in FINITE_VERBS or word in FINITE_ED_FORMS:
        return True
    if word in STOPWORDS or word in SUBORDINATORS or word in COORDINATORS:
        return False
    if word.endswith("ed") and len(word) >= 5 and word not in NON_VERB_ED_WORDS:
        return True
    if word.endswith("s") and len(word) >= 4 and not word.endswith(("ss", "us", "is", "ics", "ness")):
        return word not in NON_VERB_S_WORDS
    return False


NON_VERB_S_WORDS = frozenset(
    """
    first second third fourth fifth always sometimes perhaps less thus unless across
    process analysis basis status focus campus census consensus apparatus class business
    access progress success address stress species series versus sometimes anyway
    """.split()
) | SINGULAR_S_WORDS


def _looks_like_fragment(sentence: str, words: Sequence[str]) -> bool:
    if len(words) < 2 or len(words) > 12:
        return False
    lowered = [word.lower() for word in words]
    if sentence.rstrip().endswith((":", ";", "-", "—")):
        return False
    if lowered[0] in IMPERATIVE_HINTS:
        return False
    finite = any(_is_finite_verb(word) for word in lowered)
    if lowered[0] in SUBORDINATORS:
        # A subordinator needs a main clause after the comma.
        if "," in sentence:
            tail = sentence.split(",", 1)[1]
            tail_words = [word.lower() for word in _WORD_RE.findall(tail)]
            return not any(_is_finite_verb(word) for word in tail_words)
        return True
    return not finite


CONJUNCTIVE_ADVERBS = frozenset(
    """
    however therefore thus moreover furthermore nevertheless nonetheless consequently
    additionally instead meanwhile indeed also still hence otherwise similarly likewise
    """.split()
)

MIN_CLAUSE_WORDS = 3


_THERE_IS_RE = re.compile(
    r"\b(?:there|here)\s+(?P<verb>is|was|has|does)\s+", re.IGNORECASE
)
_QUANTIFIER_WORDS = frozenset(
    """
    a an the many several some numerous few two three four five various multiple no
    """.split()
)
_NOUN_RE = re.compile(r"[A-Za-z]{3,}(?:s|ies)\b")


@dataclass(frozen=True)
class _ThereIsHit:
    """One "there is <quantifiers> <plural noun>" observation."""

    verb: str
    verb_start: int
    verb_end: int
    noun: str
    start: int
    end: int


def _there_is_plural_spans(text: str) -> Iterator[_ThereIsHit]:
    """Find "there is many studies"-style wording without a nested regex.

    Quantifier words are skipped one at a time in a bounded loop, so a document
    full of "numerous numerous numerous" cannot cause backtracking (a nested
    regex with a repeated whitespace group did, as CodeQL reported).
    """
    for match in _THERE_IS_RE.finditer(text):
        position = match.end()
        for _ in range(3):
            word_match = re.match(r"[A-Za-z]+", text[position:])
            if not word_match or word_match.group(0).lower() not in _QUANTIFIER_WORDS:
                break
            noun_position = position + word_match.end()
            space = re.match(r"\s+", text[noun_position:])
            if not space:
                break
            position = noun_position + space.end()
        noun_match = _NOUN_RE.match(text, position)
        if not noun_match:
            continue
        yield _ThereIsHit(
            verb=match.group("verb"),
            verb_start=match.start("verb"),
            verb_end=match.end("verb"),
            noun=noun_match.group(0),
            start=match.start(),
            end=noun_match.end(),
        )


def _comma_splice(
    sentence: str, protected: Sequence[tuple[int, int]] = ()
) -> int | None:
    """Return the offset of a comma joining two finite clauses, if any.

    Deliberately conservative: both sides must look like clauses (at least
    three words each and a finite verb), coordinated or subordinated clauses are
    skipped, and a comma that opens a parenthetical adverb ("Recent work,
    however, argues…") is not a splice. This keeps the rule at medium confidence
    and avoids reporting ordinary academic punctuation as an error.
    """
    commas = [match.start() for match in re.finditer(",", sentence)]
    if not commas:
        return None
    for position in commas:
        if any(start <= position < end for start, end in protected):
            continue  # a comma inside a citation (Gupta, 2000; Rao, 2011) is not a splice
        left = sentence[:position]
        right = sentence[position + 1:]
        left_words = [word.lower() for word in _WORD_RE.findall(left)]
        right_words = [word.lower() for word in _WORD_RE.findall(right)]
        if len(left_words) < MIN_CLAUSE_WORDS or len(right_words) < MIN_CLAUSE_WORDS:
            continue
        if right_words[0] in COORDINATORS or right_words[0] in RELATIVE_PRONOUNS:
            continue
        if right_words[0] in SUBORDINATORS or left_words[-1] in SUBORDINATORS:
            continue
        if left_words[0] in SUBORDINATORS and left_words[0] not in RELATIVE_PRONOUNS:
            # "While X, Y" is one sentence with a fronted subordinate clause.
            continue
        if right_words[0] in CONJUNCTIVE_ADVERBS:
            # "…, however, argues …" is a parenthetical interruption, not a
            # clause boundary: a second comma closes the adverb. Only treat it
            # as a splice when the adverb runs straight into a new clause
            # ("…, moreover it reshaped …").
            after_adverb = right[right.find(right_words[0]) + len(right_words[0]):]
            if after_adverb.lstrip().startswith(","):
                continue
        left_finite = any(_is_finite_verb(word) for word in left_words)
        right_finite = any(_is_finite_verb(word) for word in right_words)
        if left_finite and right_finite:
            return position
    return None


# --------------------------------------------------------- curated vocabularies

# Field terms that a general dictionary does not contain. Kept deliberately
# small and alphabetical so it is easy to review and extend.
_ACADEMIC_TERMS = frozenset(
    """
    abductive affectivity agrarianism alterity annaliste autoethnography bibliometrics
    biopolitics caste castes coloniality commensurability conceptualised conceptualized
    constructivist counterfactual critique decolonial deconstructive delimitation
    desegregate dialectical dialogic discursively dramaturgical emic endogeneity
    epistemic epistemologies epistemology etic ethnography ethnomethodology exogeneity
    falsifiability generalisable generalisability gerrymandering hermeneutic heteronormative
    heuristic historiography homophily hybridity ideal-typical idiographic intersectional
    intersectionality interpretivist intertextual intersubjective liminality longitudinal
    meta-analysis meta-analyses methodological methodological individualism multi-sited
    multimethod narratology non-parametric normativity ontologies ontology operationalised
    operationalized paradigm paradigmatic parsimonious performativity positionality
    postcolonial poststructural pragmatics problematised problematized psychometric
    qualitative quantitative reflexivity reliability replicability representativeness
    rigour robustness sample-based saturation semiotic sociotechnical structuration
    subjectivation subjectivities subaltern substantivist subtextuality temporalities
    test-retest theoretically thick description transferability triangulation typology
    tenurial tenurially tenure-based unobservable validity verstehen
    """.split()
)
