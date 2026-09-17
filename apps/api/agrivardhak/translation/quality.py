"""Scoring a translation against what it must preserve — used by ``make translation-eval``.

Pure functions, no network, so the scorer itself is tested offline
(``tests/test_translation_quality.py``) and only the model's output varies between runs.

Fluency is not what goes wrong in a way that hurts someone here. What hurts is a number that
changed, a "not" that disappeared, a legal category flattened into a friendlier phrase, or a
scheme name translated into something nobody can search for. So each case states those
properties explicitly, and a similarity score against a human reference is reported beside
them rather than instead of them:

- **numbers** — every digit sequence in the source appears in the output, same count;
- **must_include** — groups of acceptable renderings, at least one per group must appear;
- **must_exclude** — renderings that would be wrong (e.g. a dropped negation's opposite);
- **verbatim** — terms that must survive untranslated (scheme names, the product name);
- **chrF** — character n-gram F-score against a human reference, when one exists. Character
  level rather than word level because Hindi morphology and spelling variants (फ़सल / फसल)
  make exact word matches punish renderings a reader would call identical.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

_DIGITS = re.compile(r"\d+")

#: Spelling variants a Hindi reader treats as the same word. Folded before matching so a case
#: does not fail on फ़ vs फ or on chandrabindu vs anusvara.
_NUKTA = "\u093c"
_CHANDRABINDU = "\u0901"
_ANUSVARA = "\u0902"


def fold(text: str) -> str:
    """Normalise for matching: NFC, lower-case, nukta dropped, chandrabindu → anusvara."""
    text = unicodedata.normalize("NFC", text)
    text = unicodedata.normalize("NFD", text).replace(_NUKTA, "")
    text = unicodedata.normalize("NFC", text).replace(_CHANDRABINDU, _ANUSVARA)
    return re.sub(r"\s+", " ", text).strip().lower()


def numbers(text: str) -> Counter[str]:
    """Digit sequences, with Indian and Western grouping ignored: 1,20,000 and 120,000 match."""
    joined = re.sub(r"(?<=\d),(?=\d)", "", text)
    return Counter(_DIGITS.findall(joined))


def chrf(hypothesis: str, reference: str, *, order: int = 6, beta: float = 2.0) -> float:
    """chrF (Popović, 2015) on 0-100, whitespace removed, averaged over n = 1..order."""
    hyp = fold(hypothesis).replace(" ", "")
    ref = fold(reference).replace(" ", "")
    if not hyp or not ref:
        return 0.0
    precisions: list[float] = []
    recalls: list[float] = []
    for n in range(1, order + 1):
        hyp_grams = Counter(hyp[i : i + n] for i in range(len(hyp) - n + 1))
        ref_grams = Counter(ref[i : i + n] for i in range(len(ref) - n + 1))
        if not hyp_grams or not ref_grams:
            continue
        overlap = sum((hyp_grams & ref_grams).values())
        precisions.append(overlap / sum(hyp_grams.values()))
        recalls.append(overlap / sum(ref_grams.values()))
    if not precisions:
        return 0.0
    p = sum(precisions) / len(precisions)
    r = sum(recalls) / len(recalls)
    if p == 0 and r == 0:
        return 0.0
    return 100 * (1 + beta**2) * p * r / (beta**2 * p + r)


@dataclass(frozen=True)
class Case:
    source: str
    target: str  # "hi-IN" | "en-IN"
    category: str
    #: Each inner tuple is a set of alternatives; one of them must appear in the output.
    must_include: tuple[tuple[str, ...], ...] = ()
    must_exclude: tuple[str, ...] = ()
    verbatim: tuple[str, ...] = ()
    reference: str | None = None
    #: Minimum chrF against ``reference``. Unset means "report, do not gate".
    min_chrf: float | None = None
    note: str = ""


@dataclass
class Result:
    case: Case
    output: str | None
    failures: list[str] = field(default_factory=list)
    chrf: float | None = None

    @property
    def passed(self) -> bool:
        return self.output is not None and not self.failures


def score(case: Case, output: str | None) -> Result:
    result = Result(case, output)
    if output is None:
        result.failures.append("no translation returned")
        return result

    folded = fold(output)

    missing = numbers(case.source) - numbers(output)
    if missing:
        result.failures.append(f"numbers lost: {sorted(missing.elements())}")

    for group in case.must_include:
        if not any(fold(option) in folded for option in group):
            result.failures.append(f"missing one of {list(group)}")

    for term in case.must_exclude:
        if fold(term) in folded:
            result.failures.append(f"contains forbidden {term!r}")

    for term in case.verbatim:
        if term not in output:
            result.failures.append(f"not kept verbatim: {term!r}")

    if case.reference is not None:
        result.chrf = chrf(output, case.reference)
        if case.min_chrf is not None and result.chrf < case.min_chrf:
            result.failures.append(f"chrF {result.chrf:.1f} < {case.min_chrf:.0f}")

    return result
