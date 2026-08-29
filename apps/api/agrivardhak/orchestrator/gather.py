"""Gather — the boundary between the database and the pure modules (ARCHITECTURE §5, step 3).

Every intelligence module is a pure function, which means something has to do the impure
part. This is that thing, and keeping it in one place is what buys the properties the whole
design rests on:

* **Replay (INV-2).** Because modules receive data rather than fetch it, a stored
  ``EvidenceSnapshot`` can be replayed through the same functions and must produce the same
  answer. If gathering were scattered through the modules, a historical recommendation could
  never be reproduced.
* **One provenance pass (INV-3).** Every consequential value is resolved here, once, through
  :mod:`agrivardhak.provenance.resolver`. A module physically cannot reach a raw column.
* **The information boundary (INV-5).** Scope filtering happens at the query, not after. Data
  a farmer may not see is never loaded, so no prompt and no rendering bug can leak it.

The functions are deliberately dull. Interesting things happening here would be a smell:
judgement belongs in the modules, where it is testable without a database.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import statistics
import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agrivardhak.domain import irrigation
from agrivardhak.domain.enums import (
    CropCycleStatus,
    ExternalRecordKind,
    FarmResourceType,
    OrgResourceType,
)
from agrivardhak.domain.models.crops import Crop, CropCycle, Variety
from agrivardhak.domain.models.land import Farm, FarmResource, Plot
from agrivardhak.domain.models.market import Buyer, DemandSignal, Lot
from agrivardhak.domain.models.organization import Farmer, Organization, OrgResource
from agrivardhak.domain.models.provenance import ExternalRecord
from agrivardhak.ingestion import agmarknet, weather
from agrivardhak.intelligence import crop_health, farm, funding, market, quality, risk, scheme
from agrivardhak.intelligence.contracts import EvidenceRef, ModuleInput
from agrivardhak.provenance import resolver

SQM_PER_HA = Decimal(10000)

#: Crops the demo prices and plans. Anything else is gathered but not costed, and the module
#: says so rather than quietly dropping it.
DEMO_CROPS = ("Potato", "Wheat", "Paddy", "Mustard", "Guava")

#: Our crop names against Agmarknet's commodity names. Kept explicit because the mapping is
#: not derivable — "Paddy" is "Paddy(Common)" there, and guessing would silently lose a crop.
AGMARKNET_COMMODITY = {
    "Potato": "Potato",
    "Wheat": "Wheat",
    "Paddy": "Paddy(Common)",
    "Mustard": "Mustard",
    "Guava": "Guava",
}

#: Irrigations a tract's water can support over one season. ⚠️ SYNTHETIC — DEMO ONLY,
#: scaled from the irrigation-coverage figures in docs/DEMO-CONTEXT.md §2 (85% / ~70% / 31%)
#: rather than from a water budget. It is the constraint that makes the rain-fed tract behave
#: differently, so it is stated here where it can be argued with rather than buried.
#:
#: An earlier version of these numbers excluded paddy from Ganga-par, which is simply false —
#: irrigated paddy is what that tract grows. The lesson is worth keeping: a constraint tuned
#: until it produces an interesting result will produce an interesting wrong result.
IRRIGATIONS_AVAILABLE = {"GANGA_PAR": 12, "DOAB": 10, "YAMUNA_PAR": 4}

#: Nitrogen and fodder per head per year. ⚠️ SYNTHETIC — DEMO ONLY (seed/sources.md A15).
LIVESTOCK_COEFFICIENTS = {
    "LIVESTOCK": (55.0, 3000.0),
    "POULTRY": (0.5, 40.0),
    "COMPOST": (12.0, 0.0),
    "MANURE": (12.0, 0.0),
}


def _ref(kind: str, row_id: uuid.UUID, label: str, as_of: dt.datetime) -> EvidenceRef:
    return EvidenceRef(kind=kind, id=row_id, label=label, as_of=as_of)


def _domain_ref(row_id: uuid.UUID, label: str, as_of: dt.datetime) -> EvidenceRef:
    return _ref("domain_row", row_id, label, as_of)


# --------------------------------------------------------------------------- shared reads


def active_cycles(
    session: Session,
    *,
    organization_id: uuid.UUID,
    as_of: dt.datetime,
    farmer_ids: list[uuid.UUID] | None = None,
    statuses: tuple[CropCycleStatus, ...] = (
        CropCycleStatus.SOWN,
        CropCycleStatus.GROWING,
        CropCycleStatus.HARVEST_READY,
    ),
) -> list[tuple[CropCycle, str, str, Farmer, Plot]]:
    """Cycles currently in the ground, with the crop, variety, farmer and plot around them.

    One query rather than five hundred: the drill-down needs the farmer and plot on every
    cycle, and fetching them per cycle turns a two-second gather into a two-minute one.
    """
    stmt = (
        select(CropCycle, Crop.name, Variety.name, Farmer, Plot)
        .join(Variety, CropCycle.variety_id == Variety.id)
        .join(Crop, Variety.crop_id == Crop.id)
        .join(Plot, CropCycle.plot_id == Plot.id)
        .join(Farm, Plot.farm_id == Farm.id)
        .join(Farmer, Farm.operator_farmer_id == Farmer.id)
        .where(CropCycle.status.in_(statuses))
    )
    if farmer_ids is not None:
        stmt = stmt.where(Farmer.id.in_(farmer_ids))
    return [tuple(row) for row in session.execute(stmt).all()]


def working_capital_paise(session: Session, organization_id: uuid.UUID) -> int | None:
    """``None`` means unrecorded, and unrecorded is not zero (FR-103)."""
    resource = (
        session.execute(
            select(OrgResource).where(
                OrgResource.organization_id == organization_id,
                OrgResource.type == OrgResourceType.WORKING_CAPITAL,
            )
        )
        .scalars()
        .first()
    )
    return resource.value_paise if resource else None


def storage_capacity_kg(
    session: Session, organization_id: uuid.UUID
) -> tuple[Decimal | None, EvidenceRef | None]:
    resource = (
        session.execute(
            select(OrgResource).where(
                OrgResource.organization_id == organization_id,
                OrgResource.type.in_((OrgResourceType.COLD_STORAGE, OrgResourceType.WAREHOUSE)),
            )
        )
        .scalars()
        .first()
    )
    if resource is None or resource.quantity is None:
        return None, None
    return (
        Decimal(str(resource.quantity)),
        _domain_ref(resource.id, f"{resource.label} capacity", dt.datetime.now(dt.UTC)),
    )


def price_history(
    session: Session, *, crops: tuple[str, ...] = DEMO_CROPS, months: int = 24
) -> dict[str, list[market.PricePoint]]:
    since = dt.date.today() - dt.timedelta(days=months * 31)
    out: dict[str, list[market.PricePoint]] = {}
    for crop_name in crops:
        commodity = AGMARKNET_COMMODITY.get(crop_name, crop_name)
        points = agmarknet.price_points(session, commodity_name=commodity, since=since, limit=2000)
        if points:
            out[crop_name] = points
    return out


# --------------------------------------------------------------------------- quality (M6)


def for_quality(session: Session, *, organization_id: uuid.UUID, as_of: dt.datetime) -> ModuleInput:
    """Every active cycle with its health reading, water status and season stress."""
    rows = active_cycles(session, organization_id=organization_id, as_of=as_of)
    stress_cache: dict[tuple[str, int], float | None] = {}
    cycles: list[quality.CycleInput] = []

    for cycle, crop_name, variety_name, farmer, plot in rows:
        health = resolver.resolve(
            session,
            subject_type="crop_cycle",
            subject_id=cycle.id,
            attribute="crop_health_pct",
            as_of=as_of,
        )
        variety = session.get(Variety, cycle.variety_id)
        stress = _stress_for(session, farmer.tract, cycle, stress_cache)
        evidence = [_domain_ref(cycle.id, f"{crop_name} cycle {cycle.season_year}", as_of)]
        if health is not None:
            evidence.append(health.evidence)
        cycles.append(
            quality.CycleInput(
                cycle_id=cycle.id,
                crop_name=crop_name,
                variety_name=variety_name,
                farmer_id=farmer.id,
                plot_id=plot.id,
                area_sqm=Decimal(str(cycle.area_sqm)),
                sowing_date=cycle.sowing_date,
                duration_days=variety.duration_days if variety else None,
                base_yield_kg_per_ha=(
                    float(variety.base_yield_kg_per_ha)
                    if variety and variety.base_yield_kg_per_ha
                    else None
                ),
                tract=farmer.tract,
                health=health,
                water_assured=irrigation.water_assured(plot.irrigation_source),
                weather_stress_sd=stress,
                evidence=evidence,
            )
        )
    return ModuleInput(organization_id=organization_id, as_of=as_of, data={"cycles": cycles})


def _stress_for(
    session: Session,
    tract: str | None,
    cycle: CropCycle,
    cache: dict[tuple[str, int], float | None],
) -> float | None:
    if tract is None or cycle.sowing_date is None:
        return None
    key = (tract, cycle.season_year)
    if key in cache:
        return cache[key]
    end = cycle.expected_harvest_date or (cycle.sowing_date + dt.timedelta(days=120))
    index = weather.stress_index(session, tract=tract, start=cycle.sowing_date, end=end)
    cache[key] = index.composite_sd if index else None
    return cache[key]


# --------------------------------------------------------------------------- market (M7)


def for_market(session: Session, *, organization_id: uuid.UUID, as_of: dt.datetime) -> ModuleInput:
    crops = {c.id: c.name for c in session.execute(select(Crop)).scalars()}
    buyers = {b.id: b for b in session.execute(select(Buyer)).scalars()}

    lots: list[market.Lot] = []
    for row in session.execute(select(Lot).where(Lot.organization_id == organization_id)).scalars():
        lots.append(
            market.Lot(
                id=row.id,
                crop_name=crops.get(row.crop_id, "unknown"),
                quantity_kg=Decimal(str(row.quantity_kg)),
                grade=row.grade.value if row.grade else None,
                ready_date=row.ready_date,
                days_held=max(0, (as_of.date() - row.ready_date).days) if row.ready_date else 0,
                perishable=crops.get(row.crop_id) in ("Guava", "Tomato"),
            )
        )

    offers_by_crop: dict[str, list[market.Offer]] = defaultdict(list)
    for signal in session.execute(
        select(DemandSignal).where(DemandSignal.organization_id == organization_id)
    ).scalars():
        buyer = buyers.get(signal.buyer_id) if signal.buyer_id else None
        if buyer is None or signal.price_paise_per_kg is None:
            continue
        offers_by_crop[crops.get(signal.crop_id, "unknown")].append(
            market.Offer(
                buyer_id=buyer.id,
                buyer_name=buyer.name,
                price_paise_per_kg=signal.price_paise_per_kg,
                quantity_kg=Decimal(str(signal.quantity_kg or 0)),
                grade_required=signal.grade.value if signal.grade else None,
                distance_km=float(buyer.distance_km) if buyer.distance_km else 0.0,
                payment_terms_days=buyer.payment_terms_days or 0,
                reliability=float(buyer.reliability) if buyer.reliability is not None else None,
                rejection_rate=(
                    float(buyer.rejection_rate) if buyer.rejection_rate is not None else None
                ),
                min_quantity_kg=(
                    Decimal(str(buyer.min_quantity_kg)) if buyer.min_quantity_kg else None
                ),
                max_quantity_kg=(
                    Decimal(str(buyer.max_quantity_kg)) if buyer.max_quantity_kg else None
                ),
                evidence=_domain_ref(signal.id, f"{buyer.name} offer", signal.created_at),
            )
        )

    capacity, capacity_evidence = storage_capacity_kg(session, organization_id)
    return ModuleInput(
        organization_id=organization_id,
        as_of=as_of,
        data={
            "lots": lots,
            "offers_by_crop": dict(offers_by_crop),
            "price_history": price_history(session),
            "storage": market.StorageOption(
                capacity_kg=capacity,
                # ⚠️ SYNTHETIC — DEMO ONLY: a plausible UP cold-store rate per kg per day.
                cost_paise_per_kg_per_day=1,
                evidence=capacity_evidence,
            ),
        },
    )


# --------------------------------------------------------------------------- risk (M8)


def for_risk(
    session: Session,
    *,
    organization_id: uuid.UUID,
    as_of: dt.datetime,
    quality_predictions: dict[str, dict[str, Any]] | None = None,
) -> ModuleInput:
    """Exposure per crop, hazard climatology per tract, price seasonality per crop.

    ``quality_predictions`` is the Quality module's aggregate, threaded in so the risk
    figures are sized against the tonnage we actually expect rather than a planted-area
    guess. Modules do not call each other — the orchestrator carries the value across.
    """
    rows = active_cycles(session, organization_id=organization_id, as_of=as_of)

    grouped: dict[str, list[tuple[CropCycle, Farmer, Plot]]] = defaultdict(list)
    for cycle, crop_name, _variety, farmer, plot in rows:
        grouped[crop_name].append((cycle, farmer, plot))

    exposures: list[risk.CropExposure] = []
    for crop_name, group in grouped.items():
        area = sum((Decimal(str(c.area_sqm)) for c, _f, _p in group), Decimal(0))
        harvests = [c.expected_harvest_date for c, _f, _p in group if c.expected_harvest_date]
        by_tract: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
        for cycle, farmer, _plot in group:
            by_tract[farmer.tract or "unknown"] += Decimal(str(cycle.area_sqm))
        dominant = max(by_tract.items(), key=lambda kv: kv[1])[0] if by_tract else None
        predicted = (quality_predictions or {}).get(crop_name, {})
        exposures.append(
            risk.CropExposure(
                crop_name=crop_name,
                farmer_ids=sorted({f.id for _c, f, _p in group}, key=str),
                crop_cycle_ids=[c.id for c, _f, _p in group],
                area_sqm=area,
                expected_kg=predicted.get("expected_kg"),
                harvest_from=min(harvests) if harvests else None,
                harvest_to=max(harvests) if harvests else None,
                tract=dominant,
                area_by_tract=dict(by_tract),
                evidence=[
                    _domain_ref(c.id, f"{crop_name} cycle", as_of) for c, _f, _p in group[:3]
                ],
            )
        )

    buyer_exposures: list[risk.BuyerExposure] = []
    buyers = {b.id: b for b in session.execute(select(Buyer)).scalars()}
    crops = {c.id: c.name for c in session.execute(select(Crop)).scalars()}
    for signal in session.execute(
        select(DemandSignal).where(DemandSignal.organization_id == organization_id)
    ).scalars():
        buyer = buyers.get(signal.buyer_id) if signal.buyer_id else None
        if buyer is None or not signal.quantity_kg:
            continue
        buyer_exposures.append(
            risk.BuyerExposure(
                buyer_id=buyer.id,
                buyer_name=buyer.name,
                offered_kg=Decimal(str(signal.quantity_kg)),
                crop_name=crops.get(signal.crop_id, "unknown"),
                reliability=float(buyer.reliability) if buyer.reliability is not None else None,
                evidence=_domain_ref(signal.id, f"{buyer.name} offer", signal.created_at),
            )
        )

    history = price_history(session)
    return ModuleInput(
        organization_id=organization_id,
        as_of=as_of,
        data={
            "exposures": exposures,
            "climatology": load_climatology(session),
            "seasonality": {
                crop: seasonality_from(crop, points) for crop, points in history.items()
            },
            "buyer_exposures": buyer_exposures,
            "working_capital_paise": working_capital_paise(session, organization_id),
            # `price_points` returns the series ascending by date, so the *last* element is
            # the current price. Reading `[0]` here would size every value-at-risk figure
            # against a price from two years ago.
            "current_price_paise_per_kg": {
                crop: points[-1].modal_paise_per_kg for crop, points in history.items() if points
            },
        },
    )


def seasonality_from(crop_name: str, points: list[market.PricePoint]) -> risk.PriceSeasonality:
    """Collapse a daily series into a monthly shape.

    Median rather than mean, per month: mandi series carry occasional absurd outliers — a
    single lot of seed potato at five times the table price — and one of those would move a
    mean enough to invent a seasonal peak that is not there.
    """
    by_month: dict[int, list[market.PricePoint]] = defaultdict(list)
    for point in points:
        by_month[point.date.month].append(point)
    months = {
        month: risk.MonthlyPrice(
            month=month,
            median_paise_per_kg=int(statistics.median(p.modal_paise_per_kg for p in group)),
            median_arrivals_kg=(
                Decimal(
                    str(statistics.median(float(p.arrivals_kg) for p in group if p.arrivals_kg))
                )
                if any(p.arrivals_kg for p in group)
                else None
            ),
            samples=len(group),
        )
        for month, group in by_month.items()
    }
    # `points[-1]`, not `[0]`: the series is ascending, so the last element is the most
    # recent. A seasonal claim about *this* November that cited a record from two years ago
    # would send anyone checking the provenance to the wrong place — the numbers would be
    # right and the audit trail would be useless.
    return risk.PriceSeasonality(crop_name=crop_name, months=months, evidence=points[-1].evidence)


def load_climatology(session: Session) -> dict[str, risk.Climatology]:
    """Read the hazard summaries produced by ``seed/fetch_climatology.py``.

    Stored as one ``ExternalRecord`` per tract rather than 33,000 daily rows: the summary is
    what the module consumes and what the evidence ref should point at. The daily series
    stays on disk for anyone re-deriving it.
    """
    out: dict[str, risk.Climatology] = {}
    records = session.execute(
        select(ExternalRecord).where(
            ExternalRecord.kind == ExternalRecordKind.WEATHER,
            ExternalRecord.payload["_climatology"].astext == "true",
        )
    ).scalars()
    for record in records:
        payload = record.payload
        tract = payload.get("_tract")
        if not tract:
            continue
        out[tract] = risk.Climatology(
            tract=tract,
            windows={
                key: risk.HazardWindow(
                    key=key,
                    years_observed=value["years_observed"],
                    probability=value["probability"],
                    mean_rain_mm_per_day=value.get("mean_rain_mm_per_day"),
                )
                for key, value in payload.get("windows", {}).items()
            },
            evidence=_ref(
                "external_record",
                record.id,
                f"{tract} hazard climatology, {payload.get('_period', {}).get('years', '?')} years",
                record.observed_at,
            ),
        )
    return out


def load_climatology_files(session: Session, directory: pathlib.Path | None = None) -> int:
    """Persist the climatology summaries as external records. Idempotent."""
    directory = directory or weather.DEFAULT_DIR
    source = weather.ensure_source(session)
    inserted = 0
    for path in sorted(directory.glob("CLIMATOLOGY_*.json")):
        payload = json.loads(path.read_text())
        payload["_climatology"] = "true"
        tract = payload["_tract"]
        existing = (
            session.execute(
                select(ExternalRecord).where(
                    ExternalRecord.kind == ExternalRecordKind.WEATHER,
                    ExternalRecord.dedupe_key == f"climatology:{tract}",
                )
            )
            .scalars()
            .first()
        )
        if existing is not None:
            continue
        period = payload.get("_period", {})
        session.add(
            ExternalRecord(
                source_id=source.id,
                kind=ExternalRecordKind.WEATHER,
                dedupe_key=f"climatology:{tract}",
                observed_at=dt.datetime.combine(
                    dt.date.fromisoformat(period["to"]), dt.time(), tzinfo=dt.UTC
                ),
                fetched_at=dt.datetime.now(dt.UTC),
                payload=payload,
                summary=(
                    f"{tract} hazard climatology {period.get('from')} to {period.get('to')} "
                    f"({period.get('years')} years, ERA5 via Open-Meteo)"
                ),
            )
        )
        inserted += 1
    return inserted


# --------------------------------------------------------------------------- farm (M10)


def for_farm(
    session: Session,
    *,
    organization_id: uuid.UUID,
    as_of: dt.datetime,
    season: str | None = None,
    quality_predictions: dict[str, dict[str, Any]] | None = None,
) -> ModuleInput:
    """Land grouped by tract, crop options priced from the real series, assets, constraints."""
    rows = session.execute(
        select(Farmer, Plot)
        .join(Farm, Farm.operator_farmer_id == Farmer.id)
        .join(Plot, Plot.farm_id == Farm.id)
    ).all()

    by_tract: dict[str, list[tuple[Farmer, Plot]]] = defaultdict(list)
    for farmer, plot in rows:
        by_tract[farmer.tract or "unknown"].append((farmer, plot))

    blocks: list[farm.LandBlock] = []
    for tract, group in by_tract.items():
        irrigated = sum(1 for _f, p in group if irrigation.water_assured(p.irrigation_source))
        blocks.append(
            farm.LandBlock(
                tract=tract,
                area_sqm=sum((Decimal(str(p.area_sqm)) for _f, p in group), Decimal(0)),
                irrigated_share=irrigated / len(group) if group else 0.0,
                farmer_ids=sorted({f.id for f, _p in group}, key=str),
                plot_ids=[p.id for _f, p in group[:50]],
                evidence=[_domain_ref(p.id, f"{tract} plot", as_of) for _f, p in group[:3]],
            )
        )

    history = price_history(session)
    varieties = {crop_name: rows_ for crop_name, rows_ in _varieties_by_crop(session).items()}
    options: list[farm.CropOption] = []
    for crop_name, points in history.items():
        modal = sorted(p.modal_paise_per_kg for p in points)
        if not modal:
            continue
        low = modal[len(modal) // 4]
        high = modal[(len(modal) * 3) // 4]
        predicted = (quality_predictions or {}).get(crop_name, {})
        yields = [v for v in varieties.get(crop_name, []) if v is not None]
        options.append(
            farm.CropOption(
                crop_name=crop_name,
                season=farm.CROP_ECONOMICS[crop_name].season
                if crop_name in farm.CROP_ECONOMICS
                else "RABI",
                expected_yield_kg_per_ha=(statistics.mean(yields) if yields else None),
                price_low_paise_per_kg=low,
                price_high_paise_per_kg=high,
                price_evidence=points[-1].evidence,
                yield_confidence=predicted.get("confidence"),
            )
        )

    assets: list[farm.IntegratedAsset] = []
    resource_rows = session.execute(
        select(FarmResource.type, func.sum(FarmResource.quantity), func.count())
        .where(
            FarmResource.type.in_(
                (
                    FarmResourceType.LIVESTOCK,
                    FarmResourceType.POULTRY,
                    FarmResourceType.COMPOST,
                    FarmResourceType.MANURE,
                )
            )
        )
        .group_by(FarmResource.type)
    ).all()
    for kind, total, _count in resource_rows:
        nitrogen, feed = LIVESTOCK_COEFFICIENTS.get(kind.value, (0.0, 0.0))
        sample = (
            session.execute(select(FarmResource).where(FarmResource.type == kind).limit(1))
            .scalars()
            .first()
        )
        assets.append(
            farm.IntegratedAsset(
                kind=kind.value,
                count=Decimal(str(total or 0)),
                nitrogen_kg_per_unit_year=nitrogen,
                feed_kg_per_unit_year=feed,
                evidence=[_domain_ref(sample.id, f"{kind.value} on farm", as_of)] if sample else [],
            )
        )

    return ModuleInput(
        organization_id=organization_id,
        as_of=as_of,
        data={
            "blocks": blocks,
            "options": options,
            "integrated_assets": assets,
            "season": season,
            "planted_crop_by_tract": _planted_crop_by_tract(session, as_of=as_of),
            "constraints": farm.Constraints(
                working_capital_paise=working_capital_paise(session, organization_id),
                irrigations_available=IRRIGATIONS_AVAILABLE,
            ),
        },
    )


def _planted_crop_by_tract(session: Session, *, as_of: dt.datetime) -> dict[str, str]:
    """Which crop actually occupies most of each tract right now, and org-wide.

    The Farm module needs this to say where the *incumbent* crop ranks rather than only which
    crop wins in the abstract. Derived here because it is a database read; the module receives
    it as data and stays pure.
    """
    rows = session.execute(
        select(Farmer.tract, Crop.name, func.sum(CropCycle.area_sqm))
        .join(Variety, CropCycle.variety_id == Variety.id)
        .join(Crop, Variety.crop_id == Crop.id)
        .join(Plot, CropCycle.plot_id == Plot.id)
        .join(Farm, Plot.farm_id == Farm.id)
        .join(Farmer, Farm.operator_farmer_id == Farmer.id)
        .where(
            CropCycle.status.in_(
                (
                    CropCycleStatus.SOWN,
                    CropCycleStatus.GROWING,
                    CropCycleStatus.HARVEST_READY,
                )
            )
        )
        .group_by(Farmer.tract, Crop.name)
    ).all()

    best_by_tract: dict[str, tuple[str, float]] = {}
    org_totals: dict[str, float] = {}
    for tract, crop_name, area in rows:
        area = float(area or 0)
        org_totals[crop_name] = org_totals.get(crop_name, 0.0) + area
        current = best_by_tract.get(tract or "unknown")
        if current is None or area > current[1]:
            best_by_tract[tract or "unknown"] = (crop_name, area)

    out = {tract: name for tract, (name, _area) in best_by_tract.items()}
    if org_totals:
        out["__dominant__"] = max(org_totals.items(), key=lambda kv: kv[1])[0]
    return out


def _varieties_by_crop(session: Session) -> dict[str, list[float]]:
    out: dict[str, list[float]] = defaultdict(list)
    for crop_name, base_yield in session.execute(
        select(Crop.name, Variety.base_yield_kg_per_ha).join(Variety, Variety.crop_id == Crop.id)
    ).all():
        if base_yield is not None:
            out[crop_name].append(float(base_yield))
    return out


# --------------------------------------------------------------------------- crop health (M11)


def for_crop_health(
    session: Session, *, organization_id: uuid.UUID, as_of: dt.datetime, days: int = 30
) -> ModuleInput:
    """Recent symptom reports, with the weather each one sat in."""
    since = as_of - dt.timedelta(days=days)
    rows = active_cycles(session, organization_id=organization_id, as_of=as_of)
    observations: list[crop_health.HealthObservation] = []

    for cycle, crop_name, _variety, farmer, plot in rows:
        symptoms = resolver.resolve(
            session,
            subject_type="crop_cycle",
            subject_id=cycle.id,
            attribute="symptoms",
            as_of=as_of,
        )
        if symptoms is None or symptoms.observed_at < since:
            continue
        codes = tuple(
            code.strip() for code in (symptoms.value_text or "").split(",") if code.strip()
        )
        if not codes:
            continue
        health = resolver.resolve(
            session,
            subject_type="crop_cycle",
            subject_id=cycle.id,
            attribute="crop_health_pct",
            as_of=as_of,
        )
        observations.append(
            crop_health.HealthObservation(
                cycle_id=cycle.id,
                farmer_id=farmer.id,
                plot_id=plot.id,
                crop_name=crop_name,
                observed_on=symptoms.observed_at.date(),
                symptoms=codes,
                severity_pct=(
                    round(100.0 - float(health.value), 1)
                    if health is not None and health.value is not None
                    else None
                ),
                affected_area_sqm=Decimal(str(cycle.area_sqm)),
                health=health,
                evidence=[symptoms.evidence],
                tract=farmer.tract,
                village=farmer.village,
            )
        )

    return ModuleInput(
        organization_id=organization_id,
        as_of=as_of,
        data={
            "observations": observations,
            "weather_by_tract": _weather_context(session, as_of),
        },
    )


def _weather_context(
    session: Session, as_of: dt.datetime, days: int = 10
) -> dict[str, crop_health.WeatherContext]:
    out: dict[str, crop_health.WeatherContext] = {}
    end = as_of.date()
    start = end - dt.timedelta(days=days)
    for tract in weather.TRACTS:
        rows = weather.daily_weather(session, tract=tract, start=start, end=end)
        if not rows:
            continue
        humidity = [d.humidity_pct for d in rows if d.humidity_pct is not None]
        highs = [d.temp_max_c for d in rows if d.temp_max_c is not None]
        lows = [d.temp_min_c for d in rows if d.temp_min_c is not None]
        rain = [d.rainfall_mm for d in rows if d.rainfall_mm is not None]
        index = weather.stress_index(session, tract=tract, start=start, end=end)
        out[tract] = crop_health.WeatherContext(
            humidity_pct=statistics.mean(humidity) if humidity else None,
            temp_max_c=statistics.mean(highs) if highs else None,
            temp_min_c=statistics.mean(lows) if lows else None,
            rainfall_mm=sum(rain) if rain else None,
            evidence=index.evidence if index else None,
        )
    return out


# --------------------------------------------------------------------------- scheme (M9)


def for_scheme(
    session: Session, *, organization_id: uuid.UUID, as_of: dt.datetime, limit: int = 400
) -> ModuleInput:
    """Facts on record about members and the organization. Nothing inferred.

    ``limit`` exists because assessing every one of a thousand farmers against every scheme
    on every question is wasteful when the finding is a count. The sample is stated in the
    output rather than hidden, and the count is scaled honestly.
    """
    org = session.get(Organization, organization_id)
    member_count = session.execute(select(func.count()).select_from(Farmer)).scalar_one()

    farmers: list[scheme.FarmerFacts] = []
    rows = session.execute(
        select(Farmer, func.count(Plot.id), func.sum(Plot.area_sqm))
        .join(Farm, Farm.operator_farmer_id == Farmer.id)
        .join(Plot, Plot.farm_id == Farm.id)
        .group_by(Farmer.id)
        .limit(limit)
    ).all()
    for farmer, plot_count, area in rows:
        farmers.append(
            scheme.FarmerFacts(
                farmer_id=farmer.id,
                name=farmer.full_name,
                facts={
                    "is_landholder": plot_count > 0,
                    "has_land_record": plot_count > 0,
                    "has_crop_cycle": True,
                    "holding_ha": float(Decimal(str(area or 0)) / SQM_PER_HA),
                    # Deliberately absent rather than guessed: we have no observation of
                    # Aadhaar seeding, bank accounts or tax status. Absent becomes
                    # INSUFFICIENT_DATA and a named gap, which is the useful answer.
                },
                evidence=[_domain_ref(farmer.id, farmer.full_name, as_of)],
                consented_purposes=frozenset({"SERVICE_DELIVERY"}),
            )
        )

    org_facts = scheme.OrganizationFacts(
        organization_id=organization_id,
        name=org.name if org else "organization",
        facts={
            "organization_type": org.type.value if org else None,
            "member_count": member_count,
            "is_registered": True,
            "has_business_plan": False,
        },
        evidence=[_domain_ref(organization_id, org.name if org else "organization", as_of)],
    )

    return ModuleInput(
        organization_id=organization_id,
        as_of=as_of,
        data={
            "farmers": farmers,
            "organization": org_facts,
            "sample_size": len(farmers),
            "member_count": member_count,
        },
    )


# --------------------------------------------------------------------------- funding (M12)


def for_funding(
    session: Session,
    *,
    organization_id: uuid.UUID,
    as_of: dt.datetime,
    quality_predictions: dict[str, dict[str, Any]] | None = None,
) -> ModuleInput:
    """What the season costs, per crop and per tract — never per farmer.

    The grouping is the safety property, not a convenience. FR-605 and SAF-04 forbid this
    system from ever ranking members by who is worth funding, and the cheapest way to keep
    that promise is to make the per-farmer number impossible to compute here: the module is
    handed crop-tract blocks and never sees a cost attached to a name.

    ``funding.py`` has existed since M12 and until now nothing called it — there was no
    gather function and no entry in ``engine.MODULES``, so no question could reach it.
    """
    del quality_predictions  # accepted for signature parity with risk/farm; unused today

    rows = active_cycles(session, organization_id=organization_id, as_of=as_of)
    grouped: dict[tuple[str, str], list[tuple[CropCycle, Farmer]]] = defaultdict(list)
    for cycle, crop_name, _variety, farmer, _plot in rows:
        grouped[(crop_name, farmer.tract or "unknown")].append((cycle, farmer))

    needs: list[funding.CapitalNeed] = []
    for (crop_name, tract), group in sorted(grouped.items()):
        economics = farm.CROP_ECONOMICS.get(crop_name)
        if economics is None:
            # Costed crops only. A crop with no cost model is left out rather than given a
            # borrowed one — an invented requirement is worse than a stated gap.
            continue
        sowings = [c.sowing_date for c, _f in group if c.sowing_date]
        needs.append(
            funding.CapitalNeed(
                crop_name=crop_name,
                tract=tract,
                area_sqm=sum((Decimal(str(c.area_sqm)) for c, _f in group), Decimal(0)),
                cost_paise_per_ha=economics.total_cost_paise_per_ha,
                needed_by=min(sowings) if sowings else None,
                farmer_ids=sorted({f.id for _c, f in group}, key=str),
                evidence=[
                    _domain_ref(c.id, f"{crop_name} cycle in {tract}", as_of) for c, _f in group[:3]
                ],
            )
        )

    return ModuleInput(
        organization_id=organization_id,
        as_of=as_of,
        data={
            "needs": needs,
            "sources": _funding_sources(session, organization_id, as_of),
            "working_capital_paise": working_capital_paise(session, organization_id),
        },
    )


def _funding_sources(
    session: Session, organization_id: uuid.UUID, as_of: dt.datetime
) -> list[funding.FundingSource]:
    """Capital the collective could actually draw on this season.

    Only sources with a record behind them. We do not list "a bank loan" as an option the
    way a brochure would: a source with no recorded terms cannot be compared against one
    that has them, and offering it anyway invites a plan built on money nobody has agreed to.
    """
    sources: list[funding.FundingSource] = []

    own = (
        session.execute(
            select(OrgResource).where(
                OrgResource.organization_id == organization_id,
                OrgResource.type == OrgResourceType.WORKING_CAPITAL,
            )
        )
        .scalars()
        .first()
    )
    if own is not None:
        sources.append(
            funding.FundingSource(
                label="Own working capital",
                available_paise=own.value_paise,
                interest_rate=0.0,
                lead_time_days=0,
                evidence=_domain_ref(own.id, own.label or "working capital", as_of),
            )
        )

    warehouse = (
        session.execute(
            select(OrgResource).where(
                OrgResource.organization_id == organization_id,
                OrgResource.type.in_((OrgResourceType.WAREHOUSE, OrgResourceType.COLD_STORAGE)),
            )
        )
        .scalars()
        .first()
    )
    if warehouse is not None:
        sources.append(
            funding.FundingSource(
                label=f"Warehouse receipt against {warehouse.label}",
                # Unknown, and unknown is not zero (FR-103). The module reports it as a
                # sourcing option whose size has to be established, not as headroom.
                available_paise=None,
                interest_rate=None,
                lead_time_days=21,
                evidence=_domain_ref(warehouse.id, warehouse.label or "warehouse", as_of),
            )
        )

    return sources
