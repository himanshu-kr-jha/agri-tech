"""Search the external knowledge base (DR-07).

Thin, like the other routers: everything behind ``knowledge.retrieval.retrieve``, which is
the seam a future retriever replaces.

The response deliberately exposes the gate. A caller sees ``licence``, ``ceiling`` and
``inert`` alongside the text, because a passage nobody has cleared us to rely on is still
useful to *read* and must never be quietly presented as though it were actionable. A UI that
rendered these without the marker would undo ADR-0014 at the last step.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from agrivardhak.api.auth import CurrentScope
from agrivardhak.db.session import get_session
from agrivardhak.domain.enums import ExternalRecordKind, NewsDomain
from agrivardhak.knowledge.retrieval import RetrievedChunk, recent, retrieve

router = APIRouter(prefix="/api/v1", tags=["knowledge"])

SessionDep = Annotated[Session, Depends(get_session)]

MAX_QUERY_CHARS = 400
MAX_RESULTS = 20


def _serialise(hit: RetrievedChunk) -> dict[str, Any]:
    return {
        "chunk_id": str(hit.chunk_id),
        "external_record_id": str(hit.external_record_id),
        "source_key": hit.source_key,
        # Hindi first, and never replaced by the English: the published wording is the
        # canonical one (ADR-0015) and the only text a rule may be read from.
        "text_hi": hit.text_hi,
        "text_en": hit.text_en,
        "news_domain": hit.news_domain.value if hit.news_domain else None,
        "observed_at": hit.observed_at.isoformat(),
        "relevance": round(hit.relevance, 6),
        "trust": round(hit.trust, 4),
        "score": round(hit.score, 6),
        "ceiling": hit.ceiling,
        "licence": hit.licence,
        "licence_confirmed": hit.licence.upper() != "UNKNOWN",
        "authority": "AUTHORITATIVE" if hit.is_authoritative else "ADVISORY",
        "verification_status": hit.verification_status.value,
        #: True when this may be read but may not drive a recommendation (ADR-0014).
        "inert": hit.is_inert,
        "evidence": {
            "kind": hit.evidence.kind,
            "id": str(hit.evidence.id),
            "label": hit.evidence.label,
            "as_of": hit.evidence.as_of.isoformat(),
        },
    }


@router.get("/knowledge/search")
def search(
    session: SessionDep,
    scope: CurrentScope,
    q: Annotated[str, Query(description="Query text; Hindi or English")],
    k: Annotated[int, Query(ge=1, le=MAX_RESULTS)] = 5,
    kind: Annotated[str | None, Query()] = None,
    domain: Annotated[str | None, Query(description="NewsDomain filter")] = None,
) -> dict[str, Any]:
    """Rank cached public agricultural text against a query.

    Organization-agnostic: this is published government material, not anyone's farm data,
    so no row-level scoping applies beyond requiring an authenticated caller. Nothing here
    crosses the information boundary (INV-5) because nothing here is about a farmer.
    """
    query = q.strip()
    if not query:
        raise HTTPException(status_code=422, detail="query must not be empty")
    if len(query) > MAX_QUERY_CHARS:
        raise HTTPException(
            status_code=422, detail=f"query must be at most {MAX_QUERY_CHARS} characters"
        )

    record_kind = _enum_or_422(ExternalRecordKind, kind, "kind")
    news_domain = _enum_or_422(NewsDomain, domain, "domain")

    hits = retrieve(
        session,
        query=query,
        as_of=dt.datetime.now(dt.UTC),
        k=k,
        kind=record_kind,
        news_domain=news_domain,
    )
    return {
        "query": query,
        "count": len(hits),
        "results": [_serialise(h) for h in hits],
        # Stated rather than implied: a caller that ignores `inert` is misusing the result.
        "note": (
            "Passages marked inert come from a source whose licence is unconfirmed. They "
            "may be read as context and may not drive a recommendation (ADR-0014)."
        ),
        "actor": str(scope.actor_user_id),
    }


def _enum_or_422(enum_cls: Any, value: str | None, field: str) -> Any:
    if value is None:
        return None
    try:
        return enum_cls(value.upper())
    except ValueError:
        allowed = ", ".join(sorted(m.value for m in enum_cls))
        raise HTTPException(
            status_code=422, detail=f"unknown {field} {value!r}; expected one of: {allowed}"
        ) from None


@router.get("/knowledge/recent")
def recent_notices(
    session: SessionDep,
    scope: CurrentScope,
    k: Annotated[int, Query(ge=1, le=MAX_RESULTS)] = 6,
    domain: Annotated[str | None, Query(description="NewsDomain filter")] = None,
) -> dict[str, Any]:
    """The most recently published passages, newest first.

    Exists for the farmer portal, which needs something on the screen before anyone has
    typed a query — a search box facing someone who does not yet know what the government
    has published is a dead end, not a feature.

    Same gate as :func:`search`: uncleared passages are returned and flagged, never hidden
    and never promoted.
    """
    news_domain = _enum_or_422(NewsDomain, domain, "domain")
    hits = recent(session, as_of=dt.datetime.now(dt.UTC), k=k, news_domain=news_domain)
    return {
        "count": len(hits),
        "results": [_serialise(h) for h in hits],
        "note": (
            "Published departmental notices, newest first. Marked-inert passages come from a "
            "source whose licence is unconfirmed and are context only (ADR-0014)."
        ),
        "actor": str(scope.actor_user_id),
    }
