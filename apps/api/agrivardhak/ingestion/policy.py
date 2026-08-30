"""Government orders as policy events (FR-404).

``news_event`` has existed since the initial schema and has never had a producer. The Risk
module says so itself, in a line that has been hardcoded since it was written:

    degraded.append("policy and procurement change is not modelled — no scheme feed yet")

There is now a scheme feed, and it did not need a new scraper. The शासनादेश stream *is* a
government policy feed: dated, categorised, published by the department whose decisions it
records, and — alone among the ten sources — carrying a licence someone has actually read.

**What it can and cannot support.** Each order gives us a date, a category and a one-sentence
subject. That is enough to say *"the department issued four orders touching crop insurance
this quarter, and 611 of your farmers grow the crops they name"* — an event and its exposure.
It is not enough to build D-13's causal chain (petrol → logistics → buyer attractiveness),
which needs quantities these listings do not contain. Reporting the event honestly is worth
more than inferring a chain we cannot evidence.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from agrivardhak.domain.models.knowledge import KnowledgeChunk
from agrivardhak.domain.models.market import NewsEvent

#: ``NewsEvent.headline`` is ``String(255)``; government-order subjects reach 329 characters.
#: The full wording always goes to ``body`` — truncation is for display only, and the chunk
#: it came from remains the citable text.
HEADLINE_CHARS = 240


def _headline(text: str) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= HEADLINE_CHARS:
        return cleaned
    return f"{cleaned[: HEADLINE_CHARS - 1]}…"


def load_policy_events(session: Session, *, source_key: str = "up-go-agriculture") -> int:
    """Create a ``NewsEvent`` for every classified, non-noise chunk of the order stream.

    Idempotent by external record: a re-run after new orders are fetched adds only the new
    ones. ``is_synthetic=False`` — these are real published orders, and the UI must be able
    to tell them apart from the demo's constructed events (seed/sources.md X8).
    """
    existing = set(
        session.execute(
            select(NewsEvent.external_record_id).where(NewsEvent.external_record_id.is_not(None))
        )
        .scalars()
        .all()
    )

    chunks = session.execute(
        select(KnowledgeChunk)
        .where(
            KnowledgeChunk.source_key == source_key,
            KnowledgeChunk.is_noise.is_(False),
            KnowledgeChunk.news_domain.is_not(None),
            KnowledgeChunk.superseded_by.is_(None),
            KnowledgeChunk.chunk_index == 0,
        )
        .order_by(KnowledgeChunk.observed_at.desc())
    ).scalars()

    url = _source_url(source_key)
    created = 0
    for chunk in chunks:
        if chunk.external_record_id in existing:
            continue
        session.add(
            NewsEvent(
                external_record_id=chunk.external_record_id,
                domain=chunk.news_domain,
                headline=_headline(chunk.text_hi),
                body=chunk.text_hi,
                url=url,
                occurred_at=chunk.observed_at,
                is_synthetic=False,
            )
        )
        existing.add(chunk.external_record_id)
        created += 1
    session.flush()
    return created


def _source_url(source_key: str) -> str | None:
    from agrivardhak.ingestion.registry import registry

    try:
        url: str | None = registry().by_key(source_key).url
    except KeyError:  # pragma: no cover - registry drift
        return None
    return url
