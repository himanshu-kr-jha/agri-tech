"""Load the Agmarknet backfill into the database, and read it back as evidence.

`seed/fetch_agmarknet.py` fetches and caches; this module persists and queries. The split
matters: fetching needs the network, loading must work offline from the cached payloads
(NFR-303).

Price rows are stored as :class:`ExternalRecord` and **not** as observations. An observation
is a claim about a domain subject — this plot's area, this crop cycle's health. A mandi price
is not about any of our subjects; it is a fact about the world that our claims cite. Modelling
it as an observation would put 23,000 rows about nobody into a table whose whole purpose is
attributing claims to subjects.
"""

from __future__ import annotations

import csv
import datetime as dt
import pathlib
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from agrivardhak.domain.enums import ExternalRecordKind, SourceType
from agrivardhak.domain.models.provenance import DataSource, ExternalRecord
from agrivardhak.domain.units import rupees_per_quintal_to_paise_per_kg
from agrivardhak.intelligence.contracts import EvidenceRef
from agrivardhak.intelligence.market import PricePoint

SOURCE_KEY = "agmarknet"
DEFAULT_CSV = (
    pathlib.Path(__file__).resolve().parents[4] / "seed" / "generated" / "agmarknet" / "series.csv"
)


def ensure_source(session: Session) -> DataSource:
    source = (
        session.execute(select(DataSource).where(DataSource.key == SOURCE_KEY)).scalars().first()
    )
    if source is not None:
        return source
    source = DataSource(
        key=SOURCE_KEY,
        label="Agmarknet (DMI, Ministry of Agriculture & Farmers Welfare)",
        source_type=SourceType.EXTERNAL_SOURCE,
        base_trust=0.85,
        url="https://api.agmarknet.gov.in/v1",
        cadence="daily",
        is_fixture=False,
    )
    session.add(source)
    session.flush()
    return source


def _price(raw: str | None) -> int | None:
    """Parse an optional Rs/quintal CSV field into paise/kg."""
    if not raw:
        return None
    return rupees_per_quintal_to_paise_per_kg(Decimal(raw))


def _dedupe_key(row: dict[str, str]) -> str:
    """Stable identity for a price row, so re-loading is a no-op.

    Includes variety because one market reports several varieties of a commodity on the
    same day, each with its own price.
    """
    return (
        f"agmarknet:{row['market_id']}:{row['commodity_id']}:{row['date']}"
        f":{row.get('variety') or '-'}:{row.get('grade') or '-'}"
    )


def load_series(
    session: Session,
    csv_path: pathlib.Path | None = None,
    *,
    batch_size: int = 2000,
) -> int:
    """Load the flattened backfill CSV into ``external_record``. Idempotent.

    Returns the number of rows inserted (rows already present are skipped, not updated —
    ``external_record`` is append-only, and a price that changed retrospectively would be a
    new observation of the world, not an edit to the old one).
    """
    path = csv_path or DEFAULT_CSV
    if not path.is_file():
        return 0

    source = ensure_source(session)
    now = dt.datetime.now(dt.UTC)

    inserted = 0
    batch: list[dict[str, object]] = []

    def flush(rows: list[dict[str, object]]) -> int:
        """Insert a batch, skipping rows already present.

        RETURNING is used rather than ``rowcount`` because with ON CONFLICT DO NOTHING the
        driver's rowcount is not a reliable count of what was actually written.
        """
        if not rows:
            return 0
        stmt = (
            pg_insert(ExternalRecord)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["kind", "dedupe_key"])
            .returning(ExternalRecord.id)
        )
        return len(list(session.execute(stmt).scalars()))

    with path.open() as handle:
        for row in csv.DictReader(handle):
            if not row.get("modal_price"):
                continue
            observed = dt.datetime.fromisoformat(row["date"]).replace(tzinfo=dt.UTC)
            # Agmarknet publishes Rs/quintal; see units.rupees_per_quintal_to_paise_per_kg
            # for why this conversion looks like a no-op and must not be "fixed".
            modal = rupees_per_quintal_to_paise_per_kg(Decimal(row["modal_price"]))
            batch.append(
                {
                    "kind": ExternalRecordKind.MARKET_PRICE,
                    "source_id": source.id,
                    "dedupe_key": _dedupe_key(row),
                    "fetched_at": now,
                    "observed_at": observed,
                    "payload": {
                        "market_id": int(row["market_id"]),
                        "market_name": row["market_name"],
                        "commodity_id": int(row["commodity_id"]),
                        "commodity_name": row["commodity_name"],
                        "variety": row.get("variety"),
                        "grade": row.get("grade"),
                        "modal_paise_per_kg": modal,
                        "min_paise_per_kg": _price(row.get("min_price")),
                        "max_paise_per_kg": _price(row.get("max_price")),
                        "arrivals_kg": float(row["arrivals"]) * 1000
                        if row.get("arrivals")
                        else None,
                        "source_units": "price in Rs/quintal, arrivals in metric tonnes",
                    },
                    "summary": (
                        f"{row['commodity_name']} at {row['market_name']} on {row['date']}: "
                        f"modal Rs {int(modal) / 100:.2f}/kg"
                    ),
                }
            )
            if len(batch) >= batch_size:
                inserted += flush(batch)
                batch = []

    inserted += flush(batch)
    session.flush()
    return inserted


def price_points(
    session: Session,
    *,
    commodity_name: str,
    since: dt.date | None = None,
    market_id: int | None = None,
    limit: int = 800,
) -> list[PricePoint]:
    """Read prices back as module input, each carrying a resolvable EvidenceRef.

    The ref points at the ``external_record`` row, so a recommendation built on these prices
    can be audited down to the exact payload we fetched — which is the whole point of keeping
    the raw responses (INV-2).
    """
    stmt = (
        select(ExternalRecord)
        .where(
            ExternalRecord.kind == ExternalRecordKind.MARKET_PRICE,
            ExternalRecord.payload["commodity_name"].astext == commodity_name,
        )
        .order_by(ExternalRecord.observed_at.desc())
        .limit(limit)
    )
    if since is not None:
        stmt = stmt.where(
            ExternalRecord.observed_at >= dt.datetime.combine(since, dt.time(), tzinfo=dt.UTC)
        )
    # market_id is filtered in Python below rather than in SQL: casting a JSONB field for
    # comparison defeats the index anyway, and the result set here is already bounded.
    records = list(session.execute(stmt).scalars())
    points: list[PricePoint] = []
    for record in records:
        payload = record.payload
        if market_id is not None and payload.get("market_id") != market_id:
            continue
        modal = payload.get("modal_paise_per_kg")
        if modal is None:
            continue
        arrivals = payload.get("arrivals_kg")
        points.append(
            PricePoint(
                date=record.observed_at.date(),
                modal_paise_per_kg=int(modal),
                arrivals_kg=Decimal(str(arrivals)) if arrivals is not None else None,
                market_name=payload.get("market_name", "unknown"),
                evidence=EvidenceRef(
                    kind="external_record",
                    id=record.id,
                    label=record.summary or f"Agmarknet {record.observed_at:%d %b %Y}",
                    as_of=record.observed_at,
                ),
            )
        )
    return sorted(points, key=lambda p: p.date)


def latest_modal_paise_per_kg(
    session: Session, *, commodity_name: str, market_id: int | None = None
) -> tuple[int, EvidenceRef] | None:
    """Most recent modal price for a commodity, with its evidence.

    Used to anchor seeded buyer offers to what the crop actually trades at. Returns ``None``
    when the commodity has never traded in the loaded window — callers must treat that as
    unknown rather than substituting a guess.
    """
    points = price_points(session, commodity_name=commodity_name, market_id=market_id, limit=40)
    if not points:
        return None
    latest = points[-1]
    return latest.modal_paise_per_kg, latest.evidence
