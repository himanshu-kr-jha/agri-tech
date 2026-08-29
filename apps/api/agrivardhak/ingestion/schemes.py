"""Landing the two UP scheme sources (batch 3) as ``ExternalRecord`` rows.

These two do not fit ``ingestion/registry.py``'s data.gov.in shape, because neither came from
data.gov.in. ``seed/fetch_up_schemes.py`` scrapes an ASP.NET GridView and reads a CMS API, so
each has its own payload layout and its own idea of what one record is.

**What this data actually is, so nobody plans against the wrong thing.** The शासनादेश scraper
harvests *listing rows* — serial number, order number, date, section, category, subject — and
never downloads the linked government order. The ``subject`` field is one Hindi sentence
averaging 199 characters. There is no eligibility text here, because eligibility text lives
in PDFs this repository has no path to fetch. What the listing does carry, reliably and with
dates, is *that a policy act occurred and what it concerned* — which is a policy feed, and is
how it is used (FR-404).

Hindi is stored exactly as published, zero-width joiners and all (ADR-0015).
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from agrivardhak.domain.enums import ExternalRecordKind
from agrivardhak.domain.models.provenance import ExternalRecord
from agrivardhak.ingestion.registry import GENERATED_DIR, ensure_source, registry

#: CMS section → (Hindi title field, English title field, Hindi body field, English body
#: field). The portal names the same concept four different ways across its sections.
CMS_SECTIONS: dict[str, tuple[str, str, str, str]] = {
    "faqs": ("questionInHindi", "questionInEng", "answerInHindi", "answerInEng"),
    "advisorys": ("topicInHindi", "topicInEng", "contentInHindi", "contentInEng"),
    "circulars": ("topicInHindi", "topicInEng", "contentInHindi", "contentInEng"),
    "whatsNews": ("topicInHindi", "topicInEng", "contentInHindi", "contentInEng"),
    "announcements": ("nameInHindi", "nameInEng", "contentInHindi", "contentInEng"),
    "news": ("newsInHindi", "newsInEng", "contentInHindi", "contentInEng"),
    "magazine": (
        "magazineNameInHindi",
        "magazineNameInEng",
        "contentInHindi",
        "contentInEng",
    ),
}


def _parse_go_date(value: str) -> dt.datetime | None:
    """``dd/mm/yyyy`` as published. Returns None rather than guessing on a malformed date."""
    try:
        day, month, year = (int(p) for p in value.strip().split("/"))
        return dt.datetime(year, month, day, tzinfo=dt.UTC)
    except (ValueError, TypeError):
        return None


def _parse_cms_date(value: str | None) -> dt.datetime | None:
    """``dd-mm-yyyy HH:MM`` as the CMS publishes it."""
    if not value:
        return None
    for fmt in ("%d-%m-%Y %H:%M", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(value.strip(), fmt).replace(tzinfo=dt.UTC)
        except ValueError:
            continue
    return None


def _insert(session: Session, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    statement = (
        pg_insert(ExternalRecord)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["kind", "dedupe_key"])
        .returning(ExternalRecord.id)
    )
    return len(session.execute(statement).scalars().all())


def _load_government_orders(session: Session, source: Any, payload: dict[str, Any]) -> int:
    data_source = ensure_source(session, source)
    fetched = dt.datetime.now(dt.UTC)
    rows: list[dict[str, Any]] = []
    for index, order in enumerate(payload.get("orders", [])):
        if not isinstance(order, dict):
            continue
        # go_number is the de-facto identity: fetch_up_schemes.py already uses it as the
        # incremental cursor and to merge new rows against known ones.
        number = str(order.get("go_number") or index).strip()
        observed = _parse_go_date(str(order.get("go_date", ""))) or fetched
        rows.append(
            {
                "source_id": data_source.id,
                "kind": ExternalRecordKind.SCHEME,
                "dedupe_key": f"{source.key}:{number}"[:255],
                "fetched_at": fetched,
                "observed_at": observed,
                "payload": order,
                "summary": str(order.get("subject", ""))[:500] or None,
            }
        )
    return _insert(session, rows)


def _load_cms(session: Session, source: Any, payload: dict[str, Any]) -> int:
    data_source = ensure_source(session, source)
    fetched = dt.datetime.now(dt.UTC)
    rows: list[dict[str, Any]] = []
    data = payload.get("data") or {}
    for section, fields in CMS_SECTIONS.items():
        for index, item in enumerate(data.get(section) or []):
            if not isinstance(item, dict):
                continue
            identity = str(item.get("id") or index)
            observed = _parse_cms_date(item.get("startDate")) or fetched
            title_hi = fields[0]
            rows.append(
                {
                    "source_id": data_source.id,
                    "kind": ExternalRecordKind.SCHEME,
                    "dedupe_key": f"{source.key}:{section}:{identity}"[:255],
                    "fetched_at": fetched,
                    "observed_at": observed,
                    # ``_section`` is injected so the observer can read the section back
                    # without re-deriving it from the shape of the record.
                    "payload": {**item, "_section": section},
                    "summary": str(item.get(title_hi, ""))[:500] or None,
                }
            )
    return _insert(session, rows)


def load_source(session: Session, source: Any) -> int:
    """Land one batch-3 source. Idempotent."""
    path = GENERATED_DIR / source.batch_dir / f"{source.key}.json"
    if not path.is_file():
        return 0
    payload = json.loads(path.read_text())
    if "orders" in payload:
        return _load_government_orders(session, source, payload)
    if "data" in payload:
        return _load_cms(session, source, payload)
    return 0


def load_schemes(session: Session) -> dict[str, int]:
    """Land both batch-3 sources."""
    return {
        source.key: load_source(session, source)
        for source in registry().SOURCES
        if str(source.domain) == "scheme"
    }
