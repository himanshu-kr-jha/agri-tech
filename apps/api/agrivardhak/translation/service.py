"""Translate a batch of on-screen strings, memory first, Sarvam second (ADR-0023).

The browser sends whatever text it found on the page and the language it wants. For each
string this module works out the *source* language from its script, so one request can
carry English interface labels and a Hindi government order at once, and anything already
in the target language comes back untouched.

Order of resolution, per string:

1. already in the target script → returned as-is;
2. a ``translation_memory`` row → returned (``HUMAN`` rows included, which is how the
   hand-written dictionary keeps beating the machine);
3. Sarvam, if the caller may spend a call → stored as ``MACHINE`` and returned;
4. otherwise the source text, unchanged.

Step 3 is gated by ``machine_budget``. The sign-in page has no session, and a public endpoint
that spends a paid API key on arbitrary text without limit is a cost-exhaustion bug waiting
for a script to find it. So the router gives anonymous callers a small shared hourly budget
(enough for the sign-in page to translate once, after which it is served from memory) and
signed-in callers an unlimited one.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from agrivardhak.config import get_settings
from agrivardhak.domain.models.translation import (
    ORIGIN_HUMAN,
    ORIGIN_MACHINE,
    TranslationMemory,
)
from agrivardhak.translation import glossary, sarvam
from agrivardhak.translation.quality import numbers

log = logging.getLogger(__name__)

HINDI = "hi-IN"
ENGLISH = "en-IN"
LANGUAGES = (HINDI, ENGLISH)

_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_LATIN = re.compile(r"[A-Za-z]")
_WHITESPACE = re.compile(r"\s+")
#: A number and nothing else: "11", "2026", "13.8", "1,20,000", "82%". Deliberately not the
#: whole whitespace token — government order titles glue words to numbers ("संख्या-11",
#: "2401-फसल"), and copying those tokens verbatim left Hindi words inside an English line.
_NUMERIC_TOKEN = re.compile(r"(\d+(?:[.,:/]\d+)*%?)")


def normalise(text: str) -> str:
    """Collapse whitespace. Two renderings of one label differ only in indentation."""
    return _WHITESPACE.sub(" ", text).strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


def detect(text: str) -> str | None:
    """``hi-IN`` or ``en-IN`` by majority script, or ``None`` for text with no letters."""
    devanagari = len(_DEVANAGARI.findall(text))
    latin = len(_LATIN.findall(text))
    if devanagari == 0 and latin == 0:
        return None
    # Weighted as in lib/dom-translate.ts: a Devanagari word spends more code points on fewer
    # letters, and a Hindi sentence that names "AgriVardhak" is still Hindi.
    return HINDI if devanagari * 1.5 >= latin else ENGLISH


@dataclass(frozen=True)
class Pair:
    source: str
    translated: str


def lookup(session: Session, source: str, target: str, texts: list[str]) -> dict[str, str]:
    """Memory hits for ``texts`` (already normalised), keyed by source text.

    A machine row whose source contains a glossary term is a hit only if it was produced under
    the current glossary; otherwise the term may carry a rendering the glossary now forbids.
    """
    by_hash = {content_hash(t): t for t in texts}
    if not by_hash:
        return {}
    rows = session.execute(
        select(
            TranslationMemory.source_hash,
            TranslationMemory.translated_text,
            TranslationMemory.origin,
            TranslationMemory.corpus_version,
        ).where(
            TranslationMemory.source_lang == source,
            TranslationMemory.target_lang == target,
            TranslationMemory.source_hash.in_(list(by_hash)),
        )
    ).all()
    current = glossary.load()
    hits: dict[str, str] = {}
    for source_hash, translated, origin, version in rows:
        text = by_hash[source_hash]
        stale = (
            origin == ORIGIN_MACHINE
            and version != current.version
            and bool(current.matches(text, source))
        )
        if not stale:
            hits[text] = translated
    return hits


def store(
    session: Session,
    source: str,
    target: str,
    pairs: list[Pair],
    *,
    origin: str,
    provider: str,
    model: str | None,
) -> None:
    """Upsert pairs. A machine write never replaces a human row; a human write always does."""
    if not pairs:
        return
    rows = [
        {
            "source_lang": source,
            "target_lang": target,
            "source_hash": content_hash(p.source),
            "source_text": normalise(p.source),
            "translated_text": p.translated,
            "origin": origin,
            "provider": provider,
            "model": model,
            "corpus_version": glossary.load().version if origin == ORIGIN_MACHINE else None,
        }
        for p in pairs
    ]
    statement = insert(TranslationMemory).values(rows)
    update = {
        "translated_text": statement.excluded.translated_text,
        "origin": statement.excluded.origin,
        "provider": statement.excluded.provider,
        "model": statement.excluded.model,
        "corpus_version": statement.excluded.corpus_version,
        "updated_at": statement.excluded.updated_at,
    }
    statement = statement.on_conflict_do_update(
        index_elements=["source_lang", "target_lang", "source_hash"],
        set_=update,
        where=(TranslationMemory.origin == ORIGIN_MACHINE) if origin == ORIGIN_MACHINE else None,
    )
    session.execute(statement)


@dataclass(frozen=True)
class TranslateResult:
    #: Same length and order as the input, always.
    translations: list[str]
    #: Per input: True when the string is settled — translated, or needing no translation
    #: (already in the target language, no letters). False when it came back as source text
    #: because it could not be translated (budget, provider failure, number guard).
    resolved: list[bool]
    #: Strings and fragments sent to Sarvam for this request, successful or not.
    machine_calls: int


def numbers_kept(source: str, translated: str) -> bool:
    """Every digit sequence in ``source`` survives in ``translated``, the same number of times.

    Measured, not hypothetical: on 2026-09-17 mayura:v1 turned the fragment "205 kg" into
    "बीस किलो" (twenty kg) and "13.8 kg" into "तेरह किलो आठ पौंड". A wrong number on a farmer's
    screen is worse than an untranslated one, so a translation that loses one is rejected.
    """
    return not (numbers(source) - numbers(translated))


def acceptable(source: str, translated: str, target: str) -> bool:
    """A translation may be shown: numbers intact, in ``target``, and glossary terms canonical.

    The language check is asymmetric on purpose. mayura:v1 returned "In grant संख्या-11 Title
    2401-फसल Krishi कर्म…" for a government order: every number intact, mostly Latin, and
    still carrying Hindi words glued to numbers. English output may contain no Devanagari at
    all. Hindi output may contain Latin — DAP, PM-KISAN, Sarjoo-52 are how Hindi prints them.

    The glossary check is what keeps a domain word's meaning fixed (ADR-0023 §9): "FPO CEO"
    rendered as "महिला आरक्षण आयोग की अध्यक्ष", or "the collective" as "सामूहिक रूप से", fails
    it — including when the bad rendering is already sitting in the translation memory.
    """
    if not numbers_kept(source, translated):
        return False
    if target == ENGLISH:
        if _DEVANAGARI.search(translated):
            return False
    elif detect(translated) not in (HINDI, None):
        return False
    source_lang = HINDI if target == ENGLISH else ENGLISH
    return glossary.load().compliant(source, translated, source_lang, target)


def _letters(text: str) -> int:
    return len(_DEVANAGARI.findall(text)) + len(_LATIN.findall(text))


def _pieces(text: str, source: str, target: str) -> list[tuple[str, bool]]:
    """``text`` as ``(piece, fixed)``. Fixed pieces are glossary terms (already rendered in
    ``target``) and numbers; everything else is prose the model has to translate."""
    out: list[tuple[str, bool]] = []
    for piece, fixed in glossary.segments(text, source, target):
        if fixed:
            out.append((piece, True))
            continue
        for i, part in enumerate(_NUMERIC_TOKEN.split(piece)):
            if part:
                out.append((part, i % 2 == 1))
    return out


def _resolve_locally(text: str, source: str, target: str) -> str | None:
    """A rendering that needs no model, or ``None``.

    - Only terms, numbers and punctuation ("FPO", "1.48 ac", "Paddy 1,832 ac, Guava 9 ac"):
      assembled from the glossary.
    - A number beside a short unit the glossary does not know: left exactly as written. A bare
      abbreviation gives a model nothing to disambiguate with — "13.8 t" (tonnes) once came back
      as "13.8 किग्रा" (kilograms). Units it does know (ac, ha, t, q, kg) are in the glossary.
    """
    pieces = _pieces(text, source, target)
    free_letters = sum(_letters(p) for p, fixed in pieces if not fixed)
    if free_letters == 0:
        return normalise("".join(p for p, _ in pieces))
    has_term = any(fixed and not _NUMERIC_TOKEN.fullmatch(p) for p, fixed in pieces)
    if not has_term and re.search(r"\d", text) and free_letters <= 3:
        return text
    return None


def _reassemble(text: str, source: str, target: str, fragments: dict[str, str]) -> str | None:
    """Terms and numbers fixed in place, every prose piece replaced by its translation."""
    out: list[str] = []
    for piece, fixed in _pieces(text, source, target):
        if fixed or _letters(piece) == 0:
            out.append(piece)
            continue
        translated = fragments.get(piece.strip())
        if translated is None:
            return None
        lead = piece[: len(piece) - len(piece.lstrip())]
        trail = piece[len(piece.rstrip()) :]
        out.append(f"{lead}{translated.strip()}{trail}")
    return normalise("".join(out))


def _translate_with_model(
    misses: list[str], source: str, target: str
) -> tuple[dict[str, str], int]:
    """Masked translation first; for what fails the checks, prose-only fragments.

    Returns accepted translations and the number of Sarvam inputs spent.
    """
    masked = {s: glossary.mask(s, source) for s in misses}
    inputs = sorted({m for m, _ in masked.values()})
    fresh = sarvam.translate_many(inputs, source, target)
    calls = len(inputs)

    accepted: dict[str, str] = {}
    rejected: list[str] = []
    for s, (m, terms) in masked.items():
        out = fresh.get(m)
        if out is None:
            continue  # provider failure: nothing to salvage
        rendered = glossary.unmask(out, terms, target) if terms else out
        if rendered is not None and acceptable(s, rendered, target):
            accepted[s] = normalise(rendered)
        else:
            rejected.append(s)

    # A dropped placeholder, a changed number, a half-translated line: translate only the
    # prose between the fixed pieces and put the terms and numbers back verbatim.
    runs = sorted(
        {
            piece.strip()
            for s in rejected
            for piece, fixed in _pieces(s, source, target)
            if not fixed and _letters(piece) > 0
        }
    )
    if runs:
        calls += len(runs)
        fragments = {
            r: t
            for r, t in sarvam.translate_many(runs, source, target).items()
            if numbers_kept(r, t)
        }
        for s in rejected:
            rebuilt = _reassemble(s, source, target, fragments)
            if rebuilt is not None and acceptable(s, rebuilt, target):
                accepted[s] = rebuilt
            else:
                log.warning("translation dropped: failed number/glossary checks for %r", s[:80])
    return accepted, calls


def translate(
    session: Session, texts: list[str], target: str, *, machine_budget: int | None
) -> TranslateResult:
    """Translate ``texts`` into ``target``.

    Per distinct string: glossary-only strings resolve locally; then the translation memory
    (whose rows must still pass ``acceptable``); then Sarvam, with glossary terms masked.
    ``machine_budget`` caps how many strings may go to Sarvam (``None``: no cap); strings beyond
    it come back as source text, marked unresolved.
    """
    if target not in LANGUAGES:
        raise ValueError(f"unsupported target language {target!r}")

    normalised = [normalise(t) for t in texts]

    # source language → distinct strings that need translating from it
    wanted: dict[str, set[str]] = defaultdict(set)
    for text in normalised:
        source = detect(text)
        if source is not None and source != target:
            wanted[source].add(text)

    settings = get_settings()
    resolved: dict[str, str] = {}
    remaining = machine_budget
    calls = 0
    for source, distinct in wanted.items():
        pending: set[str] = set()
        for text in distinct:
            local = _resolve_locally(text, source, target)
            if local is None:
                pending.add(text)
            else:
                resolved[text] = local

        hits = {
            s: t
            for s, t in lookup(session, source, target, sorted(pending)).items()
            if acceptable(s, t, target)
        }
        resolved.update(hits)
        misses = sorted(pending - hits.keys())
        if remaining is not None:
            misses = misses[:remaining]
            remaining -= len(misses)
        if not misses or not sarvam.available():
            continue

        accepted, spent = _translate_with_model(misses, source, target)
        calls += spent
        resolved.update(accepted)
        try:
            store(
                session,
                source,
                target,
                [Pair(s, t) for s, t in accepted.items()],
                origin=ORIGIN_MACHINE,
                provider="sarvam",
                model=settings.sarvam_translate_model,
            )
            session.commit()
        except Exception as exc:
            # The translation is still good for this response; only the memory missed it.
            session.rollback()
            log.warning("translation memory write failed: %s", exc)

    translations: list[str] = []
    settled: list[bool] = []
    for text in normalised:
        source = detect(text)
        needs = source is not None and source != target
        translations.append(resolved.get(text, text))
        settled.append(not needs or text in resolved)
    return TranslateResult(translations, settled, calls)


def seed_human(session: Session, entries: list[tuple[str, str]]) -> int:
    """Load hand-written ``(english, hindi)`` pairs in both directions as ``HUMAN`` rows."""
    forward = [Pair(normalise(en), hi) for en, hi in entries if normalise(en) and hi.strip()]
    backward = [Pair(normalise(hi), en) for en, hi in entries if normalise(hi) and en.strip()]
    for source, target, pairs in ((ENGLISH, HINDI, forward), (HINDI, ENGLISH, backward)):
        # Deduplicate by hash — one statement may not touch the same conflict key twice. The
        # first entry wins, as in the browser's dictionary lookup (lib/i18n.ts), so "सूचनाएँ"
        # is "Notices" on both sides rather than whichever key came last.
        distinct: dict[str, Pair] = {}
        for pair in pairs:
            distinct.setdefault(content_hash(pair.source), pair)
        store(
            session,
            source,
            target,
            list(distinct.values()),
            origin=ORIGIN_HUMAN,
            provider="i18n.ts",
            model=None,
        )
    return len(forward) + len(backward)
