"""Landing the fetched batches as ``ExternalRecord`` rows (ADR-0013, FR-405).

``seed/`` fetches ten public sources into ``seed/generated/batch*/``, hashes them, writes a
manifest and commits the payloads so the demo runs offline. Until now nothing read them:
``grep -rn "generated/batch" apps/api`` returned nothing, and ``docs/DATA-SOURCING-HANDOFF.md``
described the state as *"gathering done, nothing wired"*. This module is the wire.

Three things worth knowing before changing it.

**Row-level, not file-level.** ADR-0013 puts external reference data in ``ExternalRecord``
so the orchestrator can resolve it per crop and per year and cite the exact figure it used.
One row per source record is what makes that possible; one row per file would force every
consumer to re-parse a 6.9 MB document to quote one number.

**Both payload envelopes are real.** Batches 1, 2 and 4 still carry the full data.gov.in
response wrapper (``index_name``, ``catalog_uuid``, ``org``, …) and have no ``fetched_count``;
batches 5 and 6 carry the trimmed ``{records, field, total, fetched_count}`` shape that
``fetch()`` produces today. The three older files predate that change and were never
rewritten, because unchanged content means no rewrite. Both must load.

**Names are not normalised here.** ADR-0017 puts aliasing at gather, failing loudly on an
unmapped name. ``R & M``/``Rapeseed/Mustard``/``Mustard`` stay exactly as published, and
``district_name`` stays ``ALLAHABAD`` — the series predates the 2018 rename, and rewriting it
to ``PRAYAGRAJ`` on ingest would destroy the only record of what the publisher actually said.
"""

from __future__ import annotations

import datetime as dt
import functools
import importlib.util
import json
import pathlib
import sys
import types
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from agrivardhak.domain.enums import ExternalRecordKind, SourceType
from agrivardhak.domain.models.provenance import DataSource, ExternalRecord

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
SEED_DIR = REPO_ROOT / "seed"
GENERATED_DIR = SEED_DIR / "generated"

#: Registry ``Domain`` value → the kind the record lands under.
DOMAIN_KIND: dict[str, ExternalRecordKind] = {
    "msp": ExternalRecordKind.MSP,
    "cost_of_cultivation": ExternalRecordKind.COST_OF_CULTIVATION,
    "scheme": ExternalRecordKind.SCHEME,
    "variety": ExternalRecordKind.VARIETY,
    "price": ExternalRecordKind.MARKET_PRICE,
    "production": ExternalRecordKind.PRODUCTION,
    "procurement": ExternalRecordKind.PROCUREMENT,
}

#: Natural key per source, in field order. A record's identity is what the publisher would
#: call the same row next year — never the array index, which shifts when a row is inserted.
#: A source absent here falls back to its position, which is honest but weaker.
#:
#: ``variety-field-crops`` is deliberately absent. It looks keyed by ``(type_of_crops,
#: name_of_crop)`` and is not: the payload is a flattened grid where each row is one *slot*
#: in a per-crop list, so ``CEREAL CROPS``/``Paddy`` names 38 different rows. Keying on it
#: dropped 189 of 255 records while reporting success. The series is a frozen 2008-2012
#: archive, so position is stable and is the only identity available.
KEY_FIELDS: dict[str, tuple[str, ...]] = {
    "msp-rabi": ("rabi_crop_wise",),
    "msp-kharif": ("kharif_crop_wise",),
    "coc-a2fl": ("crop", "state"),
    "coc-c2": ("crop", "state"),
    "crop-production-district": (
        "state_name",
        "district_name",
        "crop_year",
        "season",
        "crop",
    ),
    "procurement-paddy-statewise": ("state_ut",),
    "procurement-wheat-paddy": ("kms_rms",),
}

#: Trust before verification and decay. ADR-0012's advisory tier is guidance rather than a
#: figure a ranking may rest on, so it sits below the 0.85 that ``trust.BASE_TRUST`` gives an
#: external source, without being dismissed.
AUTHORITY_TRUST = {"authoritative": 0.85, "advisory": 0.70}


@functools.lru_cache(maxsize=1)
def registry() -> types.ModuleType:
    """Import ``seed/source_registry.py`` by path.

    The seed fetchers are deliberately standalone stdlib scripts that run without the API
    virtualenv (``DATA-SOURCING-HANDOFF.md`` §9), so ``seed/`` is not an installed package.
    Loading it by path keeps the registry the single source of truth for publisher, access
    route and licence rather than copying those strings into the API, where they would drift.
    """
    path = SEED_DIR / "source_registry.py"
    spec = importlib.util.spec_from_file_location("agrivardhak._source_registry", path)
    if spec is None or spec.loader is None:  # pragma: no cover - packaging accident
        raise RuntimeError(f"cannot load the source registry from {path}")
    module = importlib.util.module_from_spec(spec)
    # Registered before execution because ``dataclasses`` resolves a class's ``__module__``
    # through ``sys.modules`` while processing annotations; without this the frozen ``Source``
    # dataclass raises on a None module during import.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@functools.lru_cache(maxsize=1)
def fetch_state() -> dict[str, Any]:
    """Per-source fetch metadata written by ``seed/fetch_common.py``. Absent is fine."""
    path = GENERATED_DIR / "fetch_state.json"
    if not path.is_file():
        return {}
    try:
        loaded: dict[str, Any] = json.loads(path.read_text())
    except json.JSONDecodeError:  # pragma: no cover - corrupt state file
        return {}
    return loaded


def ensure_source(session: Session, source: Any) -> DataSource:
    """Find or create the ``DataSource`` row for a registry entry.

    ``label`` is the publisher, not the access route. The distinction is the registry's whole
    reason for existing: DES/CACP authored the cost tables; ``api.data.gov.in`` is merely
    where we fetched them, and a citation naming the latter would be wrong.
    """
    existing = (
        session.execute(select(DataSource).where(DataSource.key == source.key)).scalars().first()
    )
    if existing is not None:
        return existing
    created = DataSource(
        key=source.key,
        label=f"{source.title} — {source.publisher}",
        source_type=SourceType.EXTERNAL_SOURCE,
        base_trust=AUTHORITY_TRUST.get(str(source.authority), 0.85),
        url=source.url,
        cadence=f"{source.cadence_days}d",
        is_fixture=False,
    )
    session.add(created)
    session.flush()
    return created


def _dedupe_key(source_key: str, record: dict[str, Any], index: int) -> str:
    fields = KEY_FIELDS.get(source_key)
    if not fields:
        return f"{source_key}:{index}"
    parts = [str(record.get(field, "-")).strip() or "-" for field in fields]
    return f"{source_key}:{':'.join(parts)}"[:255]


def _observed_at(source: Any, record: dict[str, Any], fallback: dt.datetime) -> dt.datetime:
    """When the fact was true, as distinct from when we fetched it.

    Only the production series carries a per-row year. Everywhere else the payload is a
    cross-year table — MSP for four years sits in one row's columns — so the row as a whole
    is only meaningfully dated by the publication we took it from, and the fetch timestamp
    is the closest honest answer. Getting this wrong matters: ``observed_at`` is what decays.
    """
    year = record.get("crop_year")
    if isinstance(year, int) and 1900 < year < 2200:
        return dt.datetime(year, 7, 1, tzinfo=dt.UTC)
    return fallback


def _fetched_at(source_key: str) -> dt.datetime:
    state = fetch_state().get(source_key) or {}
    stamp = state.get("last_changed") or state.get("last_checked")
    if isinstance(stamp, str):
        try:
            parsed = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is not None:
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.UTC)
    return dt.datetime.now(dt.UTC)


def _records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull the record list out of either envelope."""
    records = payload.get("records")
    return [r for r in records if isinstance(r, dict)] if isinstance(records, list) else []


def load_source(session: Session, source: Any, *, batch_size: int = 2000) -> int:
    """Land one registry source. Idempotent — a re-run inserts nothing."""
    path = GENERATED_DIR / source.batch_dir / f"{source.key}.json"
    if not path.is_file():
        return 0
    payload = json.loads(path.read_text())
    records = _records(payload)
    if not records:
        return 0

    kind = DOMAIN_KIND[str(source.domain)]
    data_source = ensure_source(session, source)
    fetched = _fetched_at(source.key)

    keys = [_dedupe_key(source.key, record, i) for i, record in enumerate(records)]
    distinct = len(set(keys))
    if distinct != len(keys):
        # ON CONFLICT DO NOTHING would absorb the collision and report a smaller,
        # plausible-looking count. That is the failure this repository keeps naming:
        # "an unmapped name silently shortens a list" (DATA-SOURCING-HANDOFF.md §6).
        # ADR-0017's rule applies — raise rather than skip.
        raise ValueError(
            f"{source.key}: {len(keys)} records collapse to {distinct} dedupe keys using "
            f"{KEY_FIELDS.get(source.key) or 'positional'} — fix KEY_FIELDS before loading, "
            f"or {len(keys) - distinct} records would be dropped without an error"
        )

    rows: list[dict[str, Any]] = []
    inserted = 0

    def flush() -> int:
        if not rows:
            return 0
        statement = (
            pg_insert(ExternalRecord)
            .values(rows)
            # ``DO NOTHING`` against the (kind, dedupe_key) constraint is what makes a re-run
            # a no-op. RETURNING is used because the driver's rowcount is unreliable here.
            .on_conflict_do_nothing(index_elements=["kind", "dedupe_key"])
            .returning(ExternalRecord.id)
        )
        count = len(session.execute(statement).scalars().all())
        rows.clear()
        return count

    for index, record in enumerate(records):
        rows.append(
            {
                "source_id": data_source.id,
                "kind": kind,
                "dedupe_key": keys[index],
                "fetched_at": fetched,
                "observed_at": _observed_at(source, record, fetched),
                "payload": record,
                "summary": f"{source.title} — {source.publisher}",
            }
        )
        if len(rows) >= batch_size:
            inserted += flush()
    inserted += flush()
    return inserted


def load_batch(session: Session, batch: int) -> dict[str, int]:
    """Land every registry source in one batch. Batch 3 is handled by ``ingestion.schemes``."""
    from agrivardhak.ingestion import schemes

    out: dict[str, int] = {}
    for source in registry().in_batch(batch):
        if str(source.domain) == "scheme":
            out[source.key] = schemes.load_source(session, source)
        else:
            out[source.key] = load_source(session, source)
    return out


def load_all(session: Session) -> dict[str, int]:
    """Land every registered source. The entry point for ``make ingest`` and ``make seed``."""
    out: dict[str, int] = {}
    for batch in registry().batches():
        out.update(load_batch(session, batch))
    return out
