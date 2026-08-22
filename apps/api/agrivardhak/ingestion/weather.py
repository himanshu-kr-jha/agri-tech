"""Weather ingestion and the crop-stress index.

`seed/fetch_weather.py` fetches; this module persists and derives. The derivation is the
interesting half: a crop cycle does not care about a temperature, it cares about whether the
season it lived through was normal for its tract.

So :func:`stress_index` returns **standard deviations from that tract's own normal**, not
absolute millimetres — the comparison that says whether *this* season was unusual *here*.

A finding worth knowing before you build on this: **the three tracts do not get meaningfully
different weather at this resolution.** Their centroids are ~40 km apart and ERA5's grid is
coarse, so Kharif 2025 came out at 0.95 / 0.90 / 1.05 SD across Ganga-par, doab and
Yamuna-par — the same season, essentially.

That does not undermine the tract model; it relocates the mechanism. Yamuna-par is more
exposed not because less rain falls on it but because **31% of it is irrigated against 85%
in Ganga-par**, so the same deficit hurts far more. The differentiation lives in
``water_assured`` and the tract yield factor, not in the rainfall series. Claiming the
weather differs by tract would be asserting a precision the data does not have.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import statistics
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from agrivardhak.domain.enums import ExternalRecordKind, SourceType
from agrivardhak.domain.models.provenance import DataSource, ExternalRecord
from agrivardhak.intelligence.contracts import EvidenceRef

SOURCE_KEY = "open-meteo"
DEFAULT_DIR = pathlib.Path(__file__).resolve().parents[4] / "seed" / "generated" / "weather"

TRACTS = ("GANGA_PAR", "DOAB", "YAMUNA_PAR")


@dataclass(frozen=True)
class DayWeather:
    date: dt.date
    temp_max_c: float | None
    temp_min_c: float | None
    rainfall_mm: float | None
    humidity_pct: float | None
    et0_mm: float | None


@dataclass(frozen=True)
class StressIndex:
    """How unusual a crop cycle's season was, in standard deviations from tract normal.

    Signed per component so the direction is legible — a wet year and a dry year are not the
    same problem, and an FPO acting on "1.8 SD" without knowing which way is being told
    nothing useful.
    """

    rainfall_sd: float
    heat_sd: float
    humidity_sd: float
    #: Magnitude used by the Quality module. Combines the components without cancelling
    #: them out: drought and heat together are worse than either alone, not neutral.
    composite_sd: float
    days_observed: int
    evidence: EvidenceRef | None
    notes: list[str]


def ensure_source(session: Session) -> DataSource:
    source = (
        session.execute(select(DataSource).where(DataSource.key == SOURCE_KEY)).scalars().first()
    )
    if source is not None:
        return source
    source = DataSource(
        key=SOURCE_KEY,
        label="Open-Meteo historical archive (ERA5)",
        source_type=SourceType.EXTERNAL_SOURCE,
        base_trust=0.85,
        url="https://archive-api.open-meteo.com/v1/archive",
        cadence="daily",
        is_fixture=False,
    )
    session.add(source)
    session.flush()
    return source


def load_weather(session: Session, directory: pathlib.Path | None = None) -> int:
    """Load fetched tract payloads into ``external_record``. Idempotent.

    One row per tract-day, keyed by tract and date, so a re-run inserts nothing.
    """
    path = directory or DEFAULT_DIR
    if not path.is_dir():
        return 0

    source = ensure_source(session)
    now = dt.datetime.now(dt.UTC)
    rows: list[dict[str, object]] = []

    for tract in TRACTS:
        payload_path = path / f"{tract}.json"
        if not payload_path.is_file():
            continue
        payload = json.loads(payload_path.read_text())
        daily = payload.get("daily") or {}
        dates = daily.get("time") or []

        # Open-Meteo returns parallel arrays; zip them into per-day tuples up front rather
        # than closing over the loop index, which is the classic late-binding trap.
        columns = {
            name: (daily.get(source_field) or [])
            for name, source_field in (
                ("temp_max_c", "temperature_2m_max"),
                ("temp_min_c", "temperature_2m_min"),
                ("rainfall_mm", "precipitation_sum"),
                ("humidity_pct", "relative_humidity_2m_mean"),
                ("et0_mm", "et0_fao_evapotranspiration"),
            )
        }

        for index, day in enumerate(dates):
            measures = {
                name: (
                    float(values[index])
                    if index < len(values) and values[index] is not None
                    else None
                )
                for name, values in columns.items()
            }
            rows.append(
                {
                    "kind": ExternalRecordKind.WEATHER,
                    "source_id": source.id,
                    "dedupe_key": f"open-meteo:{tract}:{day}",
                    "fetched_at": now,
                    "observed_at": dt.datetime.fromisoformat(day).replace(tzinfo=dt.UTC),
                    "payload": {
                        "tract": tract,
                        "date": day,
                        "latitude": payload.get("latitude"),
                        "longitude": payload.get("longitude"),
                        **measures,
                    },
                    "summary": f"{tract} {day}: {measures['rainfall_mm'] or 0:.1f} mm",
                }
            )

    inserted = 0
    for start in range(0, len(rows), 2000):
        chunk = rows[start : start + 2000]
        stmt = (
            pg_insert(ExternalRecord)
            .values(chunk)
            .on_conflict_do_nothing(index_elements=["kind", "dedupe_key"])
            .returning(ExternalRecord.id)
        )
        inserted += len(list(session.execute(stmt).scalars()))
    session.flush()
    return inserted


def daily_weather(
    session: Session, *, tract: str, start: dt.date, end: dt.date
) -> list[DayWeather]:
    stmt = (
        select(ExternalRecord)
        .where(
            ExternalRecord.kind == ExternalRecordKind.WEATHER,
            ExternalRecord.observed_at >= dt.datetime.combine(start, dt.time(), tzinfo=dt.UTC),
            ExternalRecord.observed_at <= dt.datetime.combine(end, dt.time(), tzinfo=dt.UTC),
        )
        .order_by(ExternalRecord.observed_at)
    )
    out: list[DayWeather] = []
    for record in session.execute(stmt).scalars():
        payload = record.payload
        if payload.get("tract") != tract:
            continue
        out.append(
            DayWeather(
                date=record.observed_at.date(),
                temp_max_c=payload.get("temp_max_c"),
                temp_min_c=payload.get("temp_min_c"),
                rainfall_mm=payload.get("rainfall_mm"),
                humidity_pct=payload.get("humidity_pct"),
                et0_mm=payload.get("et0_mm"),
            )
        )
    return out


def _normals(session: Session, tract: str) -> dict[str, tuple[float, float]]:
    """Mean and stdev per tract, computed from everything loaded for it.

    The baseline is the tract's own record, not a national or state average, because that is
    the comparison that says whether *this* farmer's season was unusual.
    """
    stmt = select(ExternalRecord).where(ExternalRecord.kind == ExternalRecordKind.WEATHER)
    rainfall: list[float] = []
    heat: list[float] = []
    humidity: list[float] = []
    for record in session.execute(stmt).scalars():
        payload = record.payload
        if payload.get("tract") != tract:
            continue
        if payload.get("rainfall_mm") is not None:
            rainfall.append(float(payload["rainfall_mm"]))
        if payload.get("temp_max_c") is not None:
            heat.append(float(payload["temp_max_c"]))
        if payload.get("humidity_pct") is not None:
            humidity.append(float(payload["humidity_pct"]))

    def stats(values: list[float]) -> tuple[float, float]:
        if len(values) < 2:
            return (0.0, 0.0)
        return (statistics.fmean(values), statistics.stdev(values))

    return {"rainfall": stats(rainfall), "heat": stats(heat), "humidity": stats(humidity)}


def stress_index(
    session: Session,
    *,
    tract: str,
    start: dt.date,
    end: dt.date,
) -> StressIndex | None:
    """How far a cycle's season deviated from its tract's normal.

    Returns ``None`` when there is not enough weather to say anything — the caller then
    records a gap rather than assuming a normal season, which is the difference between
    "we do not know" and "it was fine".
    """
    days = daily_weather(session, tract=tract, start=start, end=end)
    if len(days) < 14:
        return None

    normals = _normals(session, tract)
    notes: list[str] = []

    def deviation(values: list[float], key: str) -> float:
        mean, stdev = normals[key]
        if stdev == 0 or not values:
            return 0.0
        return (statistics.fmean(values) - mean) / stdev

    rainfall = deviation([d.rainfall_mm for d in days if d.rainfall_mm is not None], "rainfall")
    heat = deviation([d.temp_max_c for d in days if d.temp_max_c is not None], "heat")
    humidity = deviation([d.humidity_pct for d in days if d.humidity_pct is not None], "humidity")

    if rainfall < -0.8:
        notes.append(f"Rainfall ran {abs(rainfall):.1f} SD below this tract's normal.")
    elif rainfall > 0.8:
        notes.append(f"Rainfall ran {rainfall:.1f} SD above this tract's normal.")
    if heat > 0.8:
        notes.append(f"Daytime temperatures ran {heat:.1f} SD above normal.")
    elif heat < -1.0:
        # Cold is a Rabi hazard, not a relief: frost damages gram, mustard and potato at
        # flowering and tuber-set. A one-sided heat check would miss the whole risk.
        notes.append(
            f"Daytime temperatures ran {abs(heat):.1f} SD below normal — cold-wave and frost "
            f"risk for Rabi crops."
        )
    if humidity > 1.0:
        notes.append(f"Humidity ran {humidity:.1f} SD above normal — raises disease pressure.")

    # Root-sum-square rather than a signed sum: a dry *and* hot season is worse than either
    # alone, and a signed sum would let them cancel into a falsely calm number.
    composite = (rainfall**2 + heat**2 + humidity**2) ** 0.5

    return StressIndex(
        rainfall_sd=round(rainfall, 3),
        heat_sd=round(heat, 3),
        humidity_sd=round(humidity, 3),
        composite_sd=round(composite, 3),
        days_observed=len(days),
        evidence=EvidenceRef(
            kind="external_record",
            id=_any_record_id(session, tract, start),
            label=f"Open-Meteo {tract} {start:%b %Y}-{end:%b %Y} ({len(days)} days)",
            as_of=dt.datetime.combine(end, dt.time(), tzinfo=dt.UTC),
        )
        if _any_record_id(session, tract, start)
        else None,
        notes=notes,
    )


def _any_record_id(session: Session, tract: str, near: dt.date) -> uuid.UUID | None:
    """A representative record for the evidence ref."""
    stmt = (
        select(ExternalRecord)
        .where(
            ExternalRecord.kind == ExternalRecordKind.WEATHER,
            ExternalRecord.observed_at >= dt.datetime.combine(near, dt.time(), tzinfo=dt.UTC),
        )
        .order_by(ExternalRecord.observed_at)
        .limit(40)
    )
    for record in session.execute(stmt).scalars():
        if record.payload.get("tract") == tract:
            return record.id
    return None
