"""``retrieve()`` — the seam between the knowledge base and everything that asks it (DR-07).

Everything above this line is the observer's problem; everything below it belongs to the
caller. There is exactly one function to learn.

**Hybrid, because neither half is sufficient.** Dense vectors handle paraphrase — a CEO
asking about "crop insurance" should reach an order about प्रधानमंत्री फसल बीमा योजना. Lexical
search handles the opposite failure: ``लघु एवं सीमांत कृषक`` is a legal category with a
landholding threshold attached, and an embedding that puts it near "small farmers" has
already lost the thing that matters. The two lists are fused with Reciprocal Rank Fusion,
which needs no score normalisation and degrades to whichever list exists — so when no encoder
is installed (NFR-303), retrieval quietly becomes lexical-only instead of failing.

**Trust multiplies; it does not merely tie-break.** A stale, unlicensed chunk that matches
the query well must lose to a fresher authoritative one that matches slightly worse. Decay
comes from ``provenance/trust.py`` — the same function that ages a farmer's plot-area claim,
called with the same ``as_of`` — and the licence and verification gates from
``knowledge/gates.py`` clamp the result. A chunk from an ``UNKNOWN``-licence source therefore
tops out below the orchestrator's confidence floor and cannot reach a recommendation, which
is ADR-0014 enforced in arithmetic rather than in a review checklist.
"""

from __future__ import annotations

import datetime as dt
import functools
import uuid
from dataclasses import dataclass

from sqlalchemy import Float, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from agrivardhak.domain.enums import (
    ExternalRecordKind,
    NewsDomain,
    SourceType,
    VerificationStatus,
)
from agrivardhak.domain.models.knowledge import KnowledgeChunk
from agrivardhak.intelligence.contracts import EvidenceRef
from agrivardhak.knowledge import embed, gates
from agrivardhak.provenance import trust

#: RRF's damping constant. 60 is the value from the original formulation and is not tuned
#: here — with two lists over a corpus this size, anything in 20-100 gives the same ordering.
RRF_K = 60

#: How many candidates each half contributes before fusion. Generous relative to ``k``,
#: because the point of fusing is to let a result ranked poorly by one method be rescued by
#: the other.
CANDIDATES = 40

#: Decay policies registered in ``trust.DEFAULT_POLICIES``.
SCHEME_ATTRIBUTE = "scheme_text"
POLICY_ATTRIBUTE = "policy_event"

#: ADR-0012's advisory tier is guidance, not a figure a ranking may rest on. Applied as a
#: discount rather than an exclusion so an FAQ can still answer a farmer's question.
ADVISORY_DISCOUNT = 0.8

#: Cosine floor for a *dense* neighbour to count as a match at all.
#:
#: Nearest-neighbour search always returns k rows. Without a floor, "bitcoin mining" came
#: back with three Hindi government orders — real retrieval, ranked correctly, and useless:
#: a reader cannot tell "here is your answer" from "here is the closest thing in a corpus
#: that does not discuss this".
#:
#: Measured over this corpus (2026-08-30): legitimate queries top out at 0.46-0.78, junk at
#: 0.20-0.38. **The bands overlap** — "cold storage" scores 0.338 against 0.380 for
#: "शेयर बाजार सेंसेक्स" — so no cosine threshold separates them cleanly, and one that
#: claimed to would be lying about its own precision. 0.42 clears every junk query measured
#: and costs one weak English query whose Hindi equivalent (भण्डारण, 0.464) still works.
#:
#: Lexical hits bypass this entirely: an exact term match is stronger evidence than any
#: embedding distance, and it is the half that protects rare legal wording.
MIN_COSINE = 0.42


@dataclass(frozen=True)
class RetrievedChunk:
    """One passage, with everything a caller needs to cite it or refuse to."""

    chunk_id: uuid.UUID
    external_record_id: uuid.UUID
    source_key: str
    text_hi: str
    text_en: str | None
    news_domain: NewsDomain | None
    observed_at: dt.datetime
    #: Fused rank score before trust is applied. Comparable within one result set only.
    relevance: float
    #: Source trust after verification and age decay, clamped by the licence gate.
    trust: float
    #: ``relevance * trust`` — the ordering key.
    score: float
    #: The highest confidence a claim resting on this chunk may carry (ADR-0014).
    ceiling: float
    licence: str
    is_authoritative: bool
    verification_status: VerificationStatus
    evidence: EvidenceRef

    @property
    def is_inert(self) -> bool:
        """True when the licence gate keeps this below the orchestrator's floor."""
        return self.ceiling <= gates.INERT_LICENCE_CEILING


@functools.lru_cache(maxsize=1)
def _source_facts() -> dict[str, tuple[str, bool]]:
    """``source_key -> (licence, is_authoritative)`` from the registry.

    The registry is the single source of truth for licence (``source_registry.py``: *"UNKNOWN
    blocks a cap lift (ADR-0014). Never guess this."*), so it is read rather than mirrored
    into a column that would drift the first time someone confirms a licence.
    """
    from agrivardhak.ingestion.registry import registry

    return {s.key: (s.licence, str(s.authority) == "authoritative") for s in registry().SOURCES}


def _rrf(ranked: list[uuid.UUID]) -> dict[uuid.UUID, float]:
    return {chunk_id: 1.0 / (RRF_K + rank) for rank, chunk_id in enumerate(ranked, start=1)}


def _base_query(
    kind: ExternalRecordKind | None, news_domain: NewsDomain | None
) -> Select[tuple[KnowledgeChunk]]:
    statement = select(KnowledgeChunk).where(
        KnowledgeChunk.superseded_by.is_(None),
        KnowledgeChunk.is_noise.is_(False),
    )
    if kind is not None:
        statement = statement.where(KnowledgeChunk.kind == kind)
    if news_domain is not None:
        statement = statement.where(KnowledgeChunk.news_domain == news_domain)
    return statement


def _lexical_ids(
    session: Session, query: str, base: Select[tuple[KnowledgeChunk]], limit: int
) -> list[uuid.UUID]:
    """Postgres full-text over the generated ``search_doc`` column.

    ``plainto_tsquery`` with the ``simple`` configuration: no stemming, no stop-word list, so
    Devanagari tokens and statutory English survive intact.
    """
    tsquery = func.plainto_tsquery("simple", query)
    statement = (
        base.add_columns(func.ts_rank(KnowledgeChunk.search_doc, tsquery).cast(Float))
        .where(KnowledgeChunk.search_doc.op("@@")(tsquery))
        .order_by(func.ts_rank(KnowledgeChunk.search_doc, tsquery).desc())
        .limit(limit)
    )
    return [row[0].id for row in session.execute(statement).all()]


def _dense_ids(
    session: Session, query: str, base: Select[tuple[KnowledgeChunk]], limit: int
) -> list[uuid.UUID]:
    """Cosine nearest neighbours above :data:`MIN_COSINE`.

    Returns an empty list when no encoder is installed, and — deliberately — also when the
    corpus simply has nothing close to the query. Saying nothing is the correct answer to a
    question these documents do not address.
    """
    vectors = embed.encode([query])
    if not vectors:
        return []
    # pgvector's cosine_distance is 1 - cosine_similarity, so the floor becomes a ceiling.
    max_distance = 1.0 - MIN_COSINE
    distance = KnowledgeChunk.embedding.cosine_distance(vectors[0])
    statement = (
        base.where(KnowledgeChunk.embedding.is_not(None), distance < max_distance)
        .order_by(distance)
        .limit(limit)
    )
    return [chunk.id for chunk in session.execute(statement).scalars()]


def retrieve(
    session: Session,
    *,
    query: str,
    as_of: dt.datetime,
    k: int = 5,
    kind: ExternalRecordKind | None = None,
    news_domain: NewsDomain | None = None,
    include_inert: bool = True,
    commercial: bool = False,
) -> list[RetrievedChunk]:
    """Rank the knowledge base against ``query``.

    ``include_inert`` keeps licence-blocked passages in the result so a caller can *show*
    them as context with a marker; they carry a ceiling below the orchestrator's floor either
    way, so they cannot silently become advice. Pass ``False`` where only actionable
    knowledge belongs, as the gather layer does.
    """
    if not query.strip():
        return []

    base = _base_query(kind, news_domain)
    lexical = _lexical_ids(session, query, base, CANDIDATES)
    dense = _dense_ids(session, query, base, CANDIDATES)

    fused: dict[uuid.UUID, float] = {}
    for scores in (_rrf(lexical), _rrf(dense)):
        for chunk_id, value in scores.items():
            fused[chunk_id] = fused.get(chunk_id, 0.0) + value
    if not fused:
        return []

    chunks = session.execute(
        select(KnowledgeChunk).where(KnowledgeChunk.id.in_(list(fused)))
    ).scalars()

    out: list[RetrievedChunk] = []
    for chunk in chunks:
        scored = _score(chunk, as_of=as_of, relevance=fused[chunk.id], commercial=commercial)
        if not include_inert and scored.is_inert:
            continue
        out.append(scored)
    out.sort(key=lambda c: c.score, reverse=True)
    return out[:k]


def _score(
    chunk: KnowledgeChunk, *, as_of: dt.datetime, relevance: float, commercial: bool
) -> RetrievedChunk:
    """Apply source trust, age decay and the licence gate to one chunk.

    One implementation, shared by :func:`retrieve` and :func:`recent`. Duplicating it would
    let the two paths disagree about whether a passage is safe to act on, which is the one
    thing here that must never differ.
    """
    licence, authoritative = _source_facts().get(chunk.source_key, ("UNKNOWN", False))
    ceiling = gates.ceiling_for(
        licence=licence,
        verification_status=chunk.verification_status,
        has_extraction=chunk.extracted is not None,
        commercial=commercial,
    )
    attribute = POLICY_ATTRIBUTE if chunk.news_domain else SCHEME_ATTRIBUTE
    decayed = trust.effective_confidence(
        source_type=SourceType.EXTERNAL_SOURCE,
        verification_status=chunk.verification_status,
        observed_at=chunk.observed_at,
        as_of=as_of,
        attribute=attribute,
    )
    if not authoritative:
        decayed *= ADVISORY_DISCOUNT
    capped = min(decayed, ceiling)
    return RetrievedChunk(
        chunk_id=chunk.id,
        external_record_id=chunk.external_record_id,
        source_key=chunk.source_key,
        text_hi=chunk.text_hi,
        text_en=chunk.text_en,
        news_domain=chunk.news_domain,
        observed_at=chunk.observed_at,
        relevance=relevance,
        trust=capped,
        score=relevance * capped,
        ceiling=ceiling,
        licence=licence,
        is_authoritative=authoritative,
        verification_status=chunk.verification_status,
        evidence=EvidenceRef(
            kind="knowledge_chunk",
            id=chunk.id,
            label=_label(chunk, licence),
            as_of=chunk.observed_at,
        ),
    )


def recent(
    session: Session,
    *,
    as_of: dt.datetime,
    k: int = 6,
    kind: ExternalRecordKind | None = None,
    news_domain: NewsDomain | None = None,
    commercial: bool = False,
) -> list[RetrievedChunk]:
    """The newest passages, unranked by relevance because there is no query to rank against.

    Ordered by the publisher's own date, not by trust: this answers "what has the department
    said lately", and reordering that by how much we trust each source would misrepresent a
    chronology as a judgement. Trust and the licence gate are still computed and attached, so
    a caller can mark an uncleared passage exactly as it would in a search result.
    """
    chunks = session.execute(
        _base_query(kind, news_domain)
        .order_by(KnowledgeChunk.observed_at.desc(), KnowledgeChunk.chunk_index)
        .limit(k)
    ).scalars()
    return [_score(chunk, as_of=as_of, relevance=0.0, commercial=commercial) for chunk in chunks]


def _label(chunk: KnowledgeChunk, licence: str) -> str:
    """What the packet's Evidence section shows.

    Names the publisher's date and flags an unconfirmed licence, because a reader deciding
    whether to act on a passage needs to know we are not cleared to rely on it.
    """
    when = chunk.observed_at.date().isoformat()
    head = (chunk.text_hi or "").strip()
    if len(head) > 90:
        head = f"{head[:87]}…"
    unconfirmed = not licence or licence.upper() == gates.UNKNOWN_LICENCE
    marker = " [licence unconfirmed]" if unconfirmed else ""
    return f"{chunk.source_key} {when}: {head}{marker}"
