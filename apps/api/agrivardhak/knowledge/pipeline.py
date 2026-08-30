"""The Data Observer: raw records in, retrievable chunks out (ADR-0018, DR-07).

    classify  →  segment  →  embed  →  index

Runs as a batch over ``ExternalRecord`` rows that have no chunks yet. Idempotent: a re-run
observes only what is new, so ``make ingest`` is safe to repeat and a cron re-run that finds
nothing is a no-op rather than a duplicate.

It deliberately does **not** call a language model. Extraction — the one step where a model
earns its keep — is a separate offline batch (``knowledge/extract.py``) whose output is
committed as a reviewable fixture, so this pipeline stays deterministic and the demo never
depends on a provider being up (NFR-303).

**Chunk boundaries depend on whether an encoder was present when a record was observed**, and
this is worth knowing before it surprises someone. With one, ``segment`` splits long passages
at topic breakpoints; without, it packs whole sentences to a length budget. On this corpus
that is the difference between 207 chunks and 195 — four long FAQ answers split 4/1/5/5
instead of 1/1/1/1, and every government-order subject is one chunk either way.

Three reasons that is acceptable rather than a DR-09 determinism problem. Chunking is stable
*once written*, because the table is append-only and this function skips records that already
have chunks. Replay is unaffected, because an ``EvidenceSnapshot`` is frozen and resolves
against the chunk ids it recorded, not against whatever the observer would produce today
(INV-2). And the variation is between environments, not between runs with the same random
seed, which is what DR-09 actually constrains.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agrivardhak.domain.enums import ExternalRecordKind
from agrivardhak.domain.models.knowledge import KnowledgeChunk
from agrivardhak.domain.models.provenance import DataSource, ExternalRecord
from agrivardhak.ingestion.schemes import CMS_SECTIONS
from agrivardhak.knowledge import classify as classify_mod
from agrivardhak.knowledge import embed, segment

log = logging.getLogger(__name__)

#: Kinds whose payloads carry prose worth retrieving. The other five batches are numeric
#: tables — the orchestrator resolves those per crop and year (ADR-0013); embedding a row of
#: cost figures would produce a vector that means nothing.
TEXT_KINDS = (ExternalRecordKind.SCHEME, ExternalRecordKind.NEWS)


@dataclass
class ObserveResult:
    records_seen: int = 0
    chunks_written: int = 0
    noise: int = 0
    embedded: int = 0
    by_domain: dict[str, int] = field(default_factory=dict)

    def __str__(self) -> str:
        domains = ", ".join(f"{k}={v}" for k, v in sorted(self.by_domain.items())) or "none"
        return (
            f"{self.records_seen} records → {self.chunks_written} chunks "
            f"({self.noise} noise, {self.embedded} embedded); domains: {domains}"
        )


@dataclass(frozen=True)
class Passage:
    """One document's worth of text pulled out of a raw payload, before segmentation."""

    text_hi: str
    text_en: str | None
    category: str | None


def passage_from(payload: dict[str, Any]) -> Passage | None:
    """Read the indexable text out of a raw payload.

    Two shapes, because two scrapers. A शासनादेश listing row keeps its subject; a CMS item
    joins its title and body. Hindi is the canonical field in both (ADR-0015) — ``text_en``
    only ever holds the publisher's own English, never a translation we made.
    """
    section = payload.get("_section")
    if section and section in CMS_SECTIONS:
        title_hi, title_en, body_hi, body_en = CMS_SECTIONS[section]
        hindi = " ".join(str(payload.get(f) or "").strip() for f in (title_hi, body_hi)).strip()
        english = " ".join(str(payload.get(f) or "").strip() for f in (title_en, body_en)).strip()
        if not hindi:
            return None
        return Passage(hindi, english or None, category=str(section))

    subject = str(payload.get("subject") or "").strip()
    if subject:
        return Passage(subject, None, category=str(payload.get("category") or "") or None)
    return None


def _observed_records(session: Session) -> set[Any]:
    """Ids that already have chunks, so a re-run does no work twice."""
    return set(
        session.execute(select(KnowledgeChunk.external_record_id).distinct()).scalars().all()
    )


def observe(
    session: Session,
    *,
    as_of: dt.datetime | None = None,
    kinds: tuple[ExternalRecordKind, ...] = TEXT_KINDS,
    limit: int | None = None,
) -> ObserveResult:
    """Chunk, classify and embed every text-bearing record that has not been observed."""
    result = ObserveResult()
    already = _observed_records(session)

    source_keys: dict[uuid.UUID, str] = {
        row[0]: row[1] for row in session.execute(select(DataSource.id, DataSource.key)).all()
    }
    advisory = _advisory_source_keys()

    statement = (
        select(ExternalRecord)
        .where(ExternalRecord.kind.in_(kinds))
        .order_by(ExternalRecord.observed_at.desc())
    )
    if limit is not None:
        statement = statement.limit(limit)

    pending: list[tuple[ExternalRecord, str, list[str], Passage, Any]] = []
    for record in session.execute(statement).scalars():
        if record.id in already:
            continue
        result.records_seen += 1
        passage = passage_from(record.payload)
        if passage is None:
            continue
        source_key = source_keys.get(record.source_id, "unknown")
        verdict = classify_mod.classify(
            passage.text_hi,
            category=passage.category,
            is_advisory=source_key in advisory,
        )
        chunks = (
            segment.segment(passage.text_hi)
            if not verdict.is_noise
            else [segment.strip_markup(passage.text_hi)]
        )
        pending.append((record, source_key, chunks, passage, verdict))

    # Embed once, in one batch, rather than per record — the encoder pays a fixed cost per
    # call and the corpus is small enough to hold in memory comfortably.
    flat = [text for _, _, chunks, _, verdict in pending if not verdict.is_noise for text in chunks]
    vectors = embed.encode(flat) if flat else []
    if vectors is None:
        log.info("no sentence encoder — chunks are written without embeddings")
        vectors = []
    vector_iter = iter(vectors)

    for record, source_key, chunks, passage, verdict in pending:
        for index, text in enumerate(chunks):
            vector = None
            if not verdict.is_noise:
                vector = next(vector_iter, None)
            session.add(
                KnowledgeChunk(
                    external_record_id=record.id,
                    source_key=source_key,
                    kind=record.kind,
                    chunk_index=index,
                    text_hi=text,
                    # The publisher's English belongs with the first chunk only; splitting a
                    # translation across Hindi topic boundaries would misalign the two.
                    text_en=passage.text_en if index == 0 else None,
                    translation_source="publisher" if passage.text_en and index == 0 else None,
                    is_noise=verdict.is_noise,
                    noise_reason=verdict.noise_reason,
                    news_domain=verdict.news_domain,
                    embedding=vector,
                    observed_at=record.observed_at,
                )
            )
            result.chunks_written += 1
            if verdict.is_noise:
                result.noise += 1
            if vector is not None:
                result.embedded += 1
            if verdict.news_domain is not None:
                key = verdict.news_domain.value
                result.by_domain[key] = result.by_domain.get(key, 0) + 1
    session.flush()
    return result


def _advisory_source_keys() -> frozenset[str]:
    """Registry keys on the ADVISORY tier (ADR-0012)."""
    from agrivardhak.ingestion.registry import registry

    return frozenset(s.key for s in registry().SOURCES if str(s.authority) == "advisory")


def backfill_embeddings(session: Session, *, batch_size: int = 128) -> int:
    """Embed chunks that were written before an encoder was on disk.

    The normal order of events is that someone clones the repo, runs ``make seed`` with no
    model present, and only later runs ``make embed-model``. Without this, those chunks would
    stay lexical-only forever and the vector index would cover whatever happened to be
    ingested afterwards — a silently half-built index is worse than none, because the gaps
    are invisible at query time.

    ``embedding`` is in the append-only trigger's mutable allowlist for exactly this: a
    vector is a derived index over ``text_hi``, not a claim about the world, so refreshing
    it does not rewrite history.
    """
    if not embed.available():
        return 0
    pending = list(
        session.execute(
            select(KnowledgeChunk).where(
                KnowledgeChunk.embedding.is_(None),
                KnowledgeChunk.is_noise.is_(False),
            )
        ).scalars()
    )
    if not pending:
        return 0

    filled = 0
    for start in range(0, len(pending), batch_size):
        window = pending[start : start + batch_size]
        vectors = embed.encode([c.text_hi for c in window])
        if vectors is None:  # pragma: no cover - encoder vanished mid-run
            break
        for chunk, vector in zip(window, vectors, strict=True):
            chunk.embedding = vector
            filled += 1
    session.flush()
    return filled


def chunk_counts(session: Session) -> dict[str, int]:
    """Small helper for the CLI and tests."""
    rows = session.execute(
        select(KnowledgeChunk.source_key, func.count()).group_by(KnowledgeChunk.source_key)
    ).all()
    return {key: count for key, count in rows}
