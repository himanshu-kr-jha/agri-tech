"""The lexical corpus: domain terms whose translation is fixed, not left to the model.

``glossary.json`` is the data; this module matches terms in source text and checks that a
translation used the canonical rendering. The service (``translation/service.py``) uses it
three ways:

1. **Resolve locally.** A string made only of terms, numbers and punctuation ("FPO", "1.48 ac",
   "Paddy 1,832 ac") is assembled here without an API call.
2. **Mask.** Terms become ``[T1]``, ``[T2]`` placeholders before the text goes to Sarvam, and are
   replaced with the canonical rendering afterwards. Measured on 2026-09-17: bracket placeholders
   survive mayura:v1 intact and it inflects around them ("[T2] ने इसे अनुमोदित किया"), while
   ``XT1X`` was transliterated and ``{{T1}}`` changed the verb. Articles stay outside the
   placeholder: "Runs the [T1]" → "[T1] को चलाता है", but "Runs [T1]" → "दौड़ [T1]" (runs, on foot).
3. **Verify.** A translation — fresh or from memory — whose source contains a term but whose
   output lacks the canonical rendering is rejected. That is what keeps an older machine row
   ("FPO CEO" → "महिला आरक्षण आयोग की अध्यक्ष") from ever being served again.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

GLOSSARY_FILE = Path(__file__).with_name("glossary.json")

HINDI = "hi-IN"
ENGLISH = "en-IN"

_NOT_DEVANAGARI_BEFORE = r"(?<![\u0900-\u097F])"
_NOT_DEVANAGARI_AFTER = r"(?![\u0900-\u097F])"
PLACEHOLDER = re.compile(r"\[T(\d+)\]")
#: A number directly before a unit term: "857 acres", "1,832ac", "13.8 t".
_NUMBER_BEFORE = re.compile(r"(\d+(?:[.,]\d+)*)\s?$")


@dataclass(frozen=True)
class Term:
    id: str
    en: str
    hi: str
    en_patterns: tuple[re.Pattern[str], ...]
    hi_patterns: tuple[re.Pattern[str], ...]
    #: A unit of measure: masked together with the number before it.
    unit: bool = False

    def canonical(self, target: str) -> str:
        return self.hi if target == HINDI else self.en


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    term: Term


@dataclass(frozen=True)
class Glossary:
    terms: tuple[Term, ...]
    #: Short hash of the file. The browser namespaces its cache by this, so editing the
    #: glossary cannot leave old renderings on screen.
    version: str

    def matches(self, text: str, source: str) -> list[Match]:
        """Non-overlapping term occurrences in ``text``, left to right; longer spans win."""
        found: list[Match] = []
        for term in self.terms:
            patterns = term.hi_patterns if source == HINDI else term.en_patterns
            for pattern in patterns:
                # A pattern may match context it must not replace ("the collective": the
                # article stays in the sentence); its ``term`` group is then the span.
                group = "term" if "term" in pattern.groupindex else 0
                found.extend(
                    Match(m.start(group), m.end(group), term) for m in pattern.finditer(text)
                )
        found.sort(key=lambda m: (m.start, -(m.end - m.start)))
        chosen: list[Match] = []
        cursor = 0
        for match in found:
            if match.start >= cursor and match.end > match.start:
                chosen.append(match)
                cursor = match.end
        return chosen

    def compliant(self, source_text: str, translated: str, source: str, target: str) -> bool:
        """Every term in the source appears in the translation in its canonical form, at least
        as many times as it occurs. Necessary, not sufficient: the canonical word can be present
        for another reason ("organization" → संगठन), which is why machine rows also carry the
        glossary version they were produced under."""
        haystack = translated if target == HINDI else translated.lower()
        needed: dict[str, int] = {}
        for match in self.matches(source_text, source):
            wanted = match.term.canonical(target)
            key = wanted if target == HINDI else wanted.lower()
            needed[key] = needed.get(key, 0) + 1
        return all(haystack.count(key) >= count for key, count in needed.items())


def _hindi_pattern(form: str) -> re.Pattern[str]:
    return re.compile(f"{_NOT_DEVANAGARI_BEFORE}{re.escape(form)}{_NOT_DEVANAGARI_AFTER}")


@lru_cache
def load(path: Path = GLOSSARY_FILE) -> Glossary:
    raw = path.read_bytes()
    data = json.loads(raw)
    terms = tuple(
        Term(
            id=entry["id"],
            en=entry["en"],
            hi=entry["hi"],
            en_patterns=tuple(re.compile(p) for p in entry["en_patterns"]),
            hi_patterns=tuple(_hindi_pattern(f) for f in entry.get("hi_forms", [])),
            unit=bool(entry.get("unit", False)),
        )
        for entry in data["terms"]
    )
    return Glossary(terms, hashlib.sha256(raw).hexdigest()[:12])


def mask(text: str, source: str, glossary: Glossary | None = None) -> tuple[str, list[Term]]:
    """Replace each term with ``[T1]``, ``[T2]``… in order. Returns the text and the terms."""
    glossary = glossary or load()
    out: list[str] = []
    terms: list[Term] = []
    cursor = 0
    for match in glossary.matches(text, source):
        start, term = match.start, match.term
        number = _NUMBER_BEFORE.search(text[cursor : match.start]) if term.unit else None
        if number:
            # Measured: "on 857 [T3]" came back "857 सरसों पर [T3]" — the model moved the
            # placeholder away from its number. One placeholder for the quantity keeps them
            # together: "on [T3]" → "[T3] पर", with [T3] = "857 एकड़".
            start = cursor + number.start()
            value = number.group(1)
            term = replace(term, en=f"{value} {term.en}", hi=f"{value} {term.hi}")
        out.append(text[cursor:start])
        terms.append(term)
        out.append(f"[T{len(terms)}]")
        cursor = match.end
    out.append(text[cursor:])
    return "".join(out), terms


def unmask(translated: str, terms: list[Term], target: str) -> str | None:
    """Put canonical renderings back. ``None`` unless every placeholder appears exactly once."""
    seen = [int(n) for n in PLACEHOLDER.findall(translated)]
    if sorted(seen) != list(range(1, len(terms) + 1)):
        return None
    return PLACEHOLDER.sub(lambda m: terms[int(m.group(1)) - 1].canonical(target), translated)


def segments(text: str, source: str, target: str) -> list[tuple[str, bool]]:
    """``text`` split into ``(piece, fixed)``: fixed pieces are canonical terms, already in
    ``target``; the rest still needs translating. Numbers are left to the caller."""
    glossary = load()
    out: list[tuple[str, bool]] = []
    cursor = 0
    for match in glossary.matches(text, source):
        if match.start > cursor:
            out.append((text[cursor : match.start], False))
        out.append((match.term.canonical(target), True))
        cursor = match.end
    if cursor < len(text):
        out.append((text[cursor:], False))
    return out
