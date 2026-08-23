"""FPO console endpoints — the 10-card dashboard and the drill-down (UI-01, FR-806).

Everything here goes through :class:`ContextScope`, so a farmer hitting these gets their own
data or nothing. The boundary is not a UI concern (INV-5).

The cards are deliberately *few*. A dashboard with forty tiles is a dashboard nobody reads;
UI-01 fixes ten because that is roughly what a CEO can hold in mind before opening the
assistant, which is where the actual thinking happens.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agrivardhak.api.auth import CurrentScope
from agrivardhak.api.scope import ContextScope
from agrivardhak.db.session import get_session
from agrivardhak.domain.enums import (
    CropCycleStatus,
    DiscrepancyStatus,
    MembershipStatus,
    RecommendationStatus,
    Role,
)
from agrivardhak.domain.models.crops import Crop, CropCycle, Variety
from agrivardhak.domain.models.decisions import Recommendation
from agrivardhak.domain.models.land import Farm, Plot
from agrivardhak.domain.models.market import Buyer, DemandSignal, Lot, LotItem
from agrivardhak.domain.models.organization import Farmer, Membership, Organization, OrgResource
from agrivardhak.domain.models.provenance import DataDiscrepancy
from agrivardhak.domain.models.schemes import EligibilityAssessment
from agrivardhak.domain.units import sqm_to_acres
from agrivardhak.provenance import resolver

router = APIRouter(prefix="/api/v1/fpo", tags=["fpo"])

SessionDep = Annotated[Session, Depends(get_session)]


def _require_org_view(scope: ContextScope) -> uuid.UUID:
    """Organization-wide reads are staff-only.

    A farmer asking for the FPO dashboard is not shown a filtered version of it — they are
    told no. A partial org view is still an org view, and the boundary is meant to be a wall
    rather than a filter (INV-5).
    """
    scope.require_any_role(
        Role.FPO_CEO, Role.FIELD_OFFICER, Role.MARKET_OFFICER, Role.FINANCE_OFFICER
    )
    return scope.require_org()


def _maybe_float(value: float | None) -> float | None:
    """Numeric columns arrive as Decimal-or-None; the API contract wants float-or-None."""
    return float(value) if value is not None else None


def _card(
    key: str,
    label: str,
    value: Any,
    *,
    unit: str | None = None,
    confidence: float | None = None,
    detail: str | None = None,
    href: str | None = None,
    synthetic: bool = True,
) -> dict[str, Any]:
    """One dashboard tile.

    ``confidence`` is carried on the card itself rather than computed in the UI, so a number
    cannot reach a screen without the thing that says how much to trust it (UI-02).

    ``href`` must name a route the web app actually serves. This API decides web routes,
    which is a wart, but it means a card can advertise a screen that was never built — four
    of these tiles once linked to ``/production``, ``/schemes`` and ``/discrepancies`` and
    three of them 404'd. ``test_dashboard_hrefs_are_built_routes`` now holds that line.
    """
    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "confidence": confidence,
        "detail": detail,
        "href": href,
        "synthetic": synthetic,
    }


@router.get("/dashboard")
def dashboard(session: SessionDep, scope: CurrentScope) -> dict[str, Any]:
    """UI-01: the ten cards.

    Deliberately does not run the intelligence modules — those take seconds and belong
    behind the assistant. This is the at-a-glance state of the collective, which must render
    in under two seconds (NFR-101).
    """
    org_id = _require_org_view(scope)
    org = session.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="organization not found")

    now = dt.datetime.now(dt.UTC)

    farmers = session.execute(
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.organization_id == org_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    ).scalar_one()

    area_sqm = session.execute(
        select(func.coalesce(func.sum(Plot.area_sqm), 0))
        .select_from(Plot)
        .join(Farm, Plot.farm_id == Farm.id)
        .join(Farmer, Farm.operator_farmer_id == Farmer.id)
        .join(Membership, Membership.farmer_id == Farmer.id)
        .where(Membership.organization_id == org_id)
    ).scalar_one()

    active_cycles = session.execute(
        select(func.count())
        .select_from(CropCycle)
        .where(CropCycle.status == CropCycleStatus.GROWING)
    ).scalar_one()

    crop_mix = session.execute(
        select(Crop.name, func.count(), func.coalesce(func.sum(CropCycle.area_sqm), 0))
        .select_from(CropCycle)
        .join(Variety, CropCycle.variety_id == Variety.id)
        .join(Crop, Variety.crop_id == Crop.id)
        .where(CropCycle.status == CropCycleStatus.GROWING)
        .group_by(Crop.name)
        .order_by(func.sum(CropCycle.area_sqm).desc())
    ).all()

    lots = session.execute(
        select(func.count(), func.coalesce(func.sum(Lot.quantity_kg), 0)).where(
            Lot.organization_id == org_id
        )
    ).one()

    offers = session.execute(
        select(func.count()).select_from(DemandSignal).where(DemandSignal.organization_id == org_id)
    ).scalar_one()

    open_discrepancies = session.execute(
        select(func.count())
        .select_from(DataDiscrepancy)
        .where(DataDiscrepancy.status == DiscrepancyStatus.OPEN)
    ).scalar_one()

    pending_approvals = session.execute(
        select(func.count())
        .select_from(Recommendation)
        .where(
            Recommendation.organization_id == org_id,
            Recommendation.status.in_(
                [RecommendationStatus.SUGGESTED, RecommendationStatus.REVIEWED]
            ),
        )
    ).scalar_one()

    scheme_opportunity = session.execute(
        select(func.coalesce(func.sum(EligibilityAssessment.estimated_benefit_paise), 0)).where(
            EligibilityAssessment.organization_id == org_id
        )
    ).scalar_one()

    working_capital = (
        session.execute(
            select(OrgResource).where(
                OrgResource.organization_id == org_id,
                OrgResource.type == "WORKING_CAPITAL",
            )
        )
        .scalars()
        .first()
    )

    cold_store = (
        session.execute(
            select(OrgResource).where(
                OrgResource.organization_id == org_id,
                OrgResource.type == "COLD_STORAGE",
            )
        )
        .scalars()
        .first()
    )

    cards = [
        _card("farmers", "Member farmers", farmers, href="/farmers"),
        _card(
            "area",
            "Operated area",
            round(float(sqm_to_acres(float(area_sqm))), 0),
            unit="acres",
            detail=f"{float(area_sqm) / 10_000:,.0f} ha",
        ),
        _card(
            "crop_mix",
            "Crops in the ground",
            len(crop_mix),
            detail=", ".join(
                f"{name} {float(sqm_to_acres(float(sqm))):,.0f} ac" for name, _n, sqm in crop_mix
            )
            or "nothing sown",
            # No href: there is no production screen. A card that links to a 404 is worse
            # than a card that does not link — see the note on _card().
        ),
        _card("active_cycles", "Active crop cycles", active_cycles),
        _card(
            "expected_production",
            "Aggregated for sale",
            round(float(lots[1]) / 1000, 1),
            unit="tonnes",
            detail=f"across {lots[0]} lots",
            href="/market",
        ),
        _card(
            "market_opportunities",
            "Live buyer offers",
            offers,
            detail="anchored to mandi modal prices",
            href="/market",
            synthetic=False,
        ),
        _card(
            "data_conflicts",
            "Unresolved data conflicts",
            open_discrepancies,
            detail="sources disagree; awaiting verification",
            href="/discrepancies",
        ),
        _card(
            "pending_actions",
            "Awaiting your approval",
            pending_approvals,
            detail="AI recommends; you decide",
            href="/decisions",
        ),
        _card(
            "scheme_opportunity",
            "Unclaimed scheme benefit",
            round((scheme_opportunity or 0) / 100, 0),
            unit="₹",
            detail="identified across members"
            if scheme_opportunity
            else "scheme engine not yet run",
            # No href: scheme detail lives inside the decision packet, not on its own screen.
        ),
        _card(
            "capital",
            "Working capital",
            round((working_capital.value_paise or 0) / 100, 0) if working_capital else None,
            unit="₹",
            detail=(
                "cold store capacity unknown"
                if cold_store is not None and cold_store.quantity is None
                else None
            ),
        ),
    ]

    return {
        "organization": {
            "id": str(org.id),
            "name": org.name,
            "type": org.type.value,
            "district": org.district,
            "state": org.state,
            "is_synthetic": org.is_synthetic,
        },
        "generated_at": now.isoformat(),
        "cards": cards,
    }


@router.get("/farmers")
def farmers(
    session: SessionDep,
    scope: CurrentScope,
    tract: Annotated[str | None, Query()] = None,
    block: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    """FR-806 / NFR-103: the drill-down list, filterable by the facets that matter.

    Tract and block are the filters the risk story needs — "show me the exposed farmers"
    resolves to a tract, and the CEO then wants to see them.
    """
    org_id = _require_org_view(scope)

    base = (
        select(Farmer)
        .join(Membership, Membership.farmer_id == Farmer.id)
        .where(
            Membership.organization_id == org_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    )
    if tract:
        base = base.where(Farmer.tract == tract)
    if block:
        base = base.where(Farmer.block == block)

    total = session.execute(select(func.count()).select_from(base.subquery())).scalar_one()

    rows = list(
        session.execute(base.order_by(Farmer.full_name).limit(limit).offset(offset)).scalars()
    )
    farmer_ids = [f.id for f in rows]

    areas: dict[uuid.UUID, float] = {}
    if farmer_ids:
        areas = {
            farmer_id: float(total)
            for farmer_id, total in session.execute(
                select(Farm.operator_farmer_id, func.coalesce(func.sum(Plot.area_sqm), 0))
                .join(Plot, Plot.farm_id == Farm.id)
                .where(Farm.operator_farmer_id.in_(farmer_ids))
                .group_by(Farm.operator_farmer_id)
            ).all()
        }

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "farmers": [
            {
                "id": str(f.id),
                "name": f.full_name,
                "village": f.village,
                "block": f.block,
                "tract": f.tract,
                "area_acres": round(float(sqm_to_acres(areas.get(f.id, 0.0))), 2),
                "is_synthetic": f.is_synthetic,
            }
            for f in rows
        ],
    }


@router.get("/farmers/{farmer_id}")
def farmer_detail(farmer_id: uuid.UUID, session: SessionDep, scope: CurrentScope) -> dict[str, Any]:
    """One farmer, all the way down to plots and crop cycles.

    A farmer may open their own record; org staff may open any member's. Anyone else is
    refused rather than shown a redacted version.
    """
    scope.require_farmer_access(farmer_id)
    farmer = session.get(Farmer, farmer_id)
    if farmer is None:
        raise HTTPException(status_code=404, detail="farmer not found")

    now = dt.datetime.now(dt.UTC)
    farms = list(
        session.execute(select(Farm).where(Farm.operator_farmer_id == farmer_id)).scalars()
    )
    plots = (
        list(session.execute(select(Plot).where(Plot.farm_id.in_([f.id for f in farms]))).scalars())
        if farms
        else []
    )

    cycles = (
        list(
            session.execute(
                select(CropCycle, Crop.name, Variety.name)
                .join(Variety, CropCycle.variety_id == Variety.id)
                .join(Crop, Variety.crop_id == Crop.id)
                .where(CropCycle.plot_id.in_([p.id for p in plots]))
                .order_by(CropCycle.season_year.desc())
            ).all()
        )
        if plots
        else []
    )

    plot_payload = []
    for plot in plots:
        area = resolver.resolve(
            session,
            subject_type="plot",
            subject_id=plot.id,
            attribute="area_sqm",
            as_of=now,
        )
        plot_payload.append(
            {
                "id": str(plot.id),
                "label": plot.label,
                "area_acres": round(float(sqm_to_acres(float(plot.area_sqm))), 2),
                "soil_type": plot.soil_type,
                "irrigation_source": plot.irrigation_source,
                # UI-02 / UI-10: the value travels with how much to trust it and whether
                # anyone disagrees about it.
                "provenance": {
                    "confidence": round(area.confidence, 3),
                    "source_type": area.source_type,
                    "observed_at": area.observed_at.isoformat(),
                    "is_stale": area.is_stale,
                    "has_open_discrepancy": area.has_open_discrepancy,
                }
                if area
                else None,
            }
        )

    cycle_payload = []
    for cycle, crop_name, variety_name in cycles:
        health = resolver.resolve(
            session,
            subject_type="crop_cycle",
            subject_id=cycle.id,
            attribute="crop_health_pct",
            as_of=now,
        )
        cycle_payload.append(
            {
                "id": str(cycle.id),
                "crop": crop_name,
                "variety": variety_name,
                "season": f"{cycle.season.value.title()} {cycle.season_year}",
                "status": cycle.status.value,
                "area_acres": round(float(sqm_to_acres(float(cycle.area_sqm))), 2),
                "sowing_date": cycle.sowing_date.isoformat() if cycle.sowing_date else None,
                "expected_harvest": cycle.expected_harvest_date.isoformat()
                if cycle.expected_harvest_date
                else None,
                "crop_health_pct": float(health.value) if health and health.value else None,
                "health_confidence": round(health.confidence, 3) if health else None,
                "health_is_stale": health.is_stale if health else None,
            }
        )

    contributions = list(
        session.execute(
            select(LotItem, Lot.label, Crop.name)
            .join(Lot, LotItem.lot_id == Lot.id)
            .join(Crop, Lot.crop_id == Crop.id)
            .where(LotItem.farmer_id == farmer_id)
        ).all()
    )

    return {
        "farmer": {
            "id": str(farmer.id),
            "name": farmer.full_name,
            "village": farmer.village,
            "block": farmer.block,
            "tract": farmer.tract,
            "district": farmer.district,
            "is_synthetic": farmer.is_synthetic,
        },
        "plots": plot_payload,
        "crop_cycles": cycle_payload,
        "lot_contributions": [
            {
                "lot": lot_label,
                "crop": crop_name,
                "quantity_kg": float(item.quantity_kg),
                "grade": item.grade.value if item.grade else None,
            }
            for item, lot_label, crop_name in contributions
        ],
    }


@router.get("/discrepancies")
def discrepancies(session: SessionDep, scope: CurrentScope) -> dict[str, Any]:
    """UI-10: conflicts surfaced at the point of use, never hidden in an admin screen."""
    _require_org_view(scope)
    rows = list(
        session.execute(
            select(DataDiscrepancy)
            .where(DataDiscrepancy.status == DiscrepancyStatus.OPEN)
            .order_by(DataDiscrepancy.spread_pct.desc())
            .limit(100)
        ).scalars()
    )
    return {
        "total": len(rows),
        "discrepancies": [
            {
                "id": str(d.id),
                "subject_type": d.subject_type,
                "subject_id": str(d.subject_id),
                "attribute": d.attribute,
                "claims": d.claims,
                "spread_pct": float(d.spread_pct),
                "tolerance_pct": float(d.tolerance_pct),
                # Shown, but never as a settled answer — the conflict travels with it.
                "best_supported_value": float(d.effective_value) if d.effective_value else None,
                "effective_confidence": float(d.effective_confidence)
                if d.effective_confidence
                else None,
            }
            for d in rows
        ],
    }


@router.get("/market")
def market(session: SessionDep, scope: CurrentScope) -> dict[str, Any]:
    """Lots and the offers against them, with the effective-price breakdown."""
    org_id = _require_org_view(scope)
    crops = {c.id: c.name for c in session.execute(select(Crop)).scalars()}
    buyers = {b.id: b for b in session.execute(select(Buyer)).scalars()}

    payload = []
    for lot in session.execute(select(Lot).where(Lot.organization_id == org_id)).scalars():
        contributors = session.execute(
            select(func.count()).select_from(LotItem).where(LotItem.lot_id == lot.id)
        ).scalar_one()
        offers = list(
            session.execute(
                select(DemandSignal).where(DemandSignal.crop_id == lot.crop_id)
            ).scalars()
        )
        payload.append(
            {
                "id": str(lot.id),
                "label": lot.label,
                "crop": crops.get(lot.crop_id),
                "quantity_kg": float(lot.quantity_kg),
                "grade": lot.grade.value if lot.grade else None,
                "ready_date": lot.ready_date.isoformat() if lot.ready_date else None,
                "contributors": contributors,
                "offers": [
                    {
                        "buyer": buyers[o.buyer_id].name if o.buyer_id in buyers else None,
                        "price_paise_per_kg": o.price_paise_per_kg,
                        "grade_required": o.grade.value if o.grade else None,
                        "distance_km": _maybe_float(
                            buyers[o.buyer_id].distance_km if o.buyer_id in buyers else None
                        ),
                        "payment_terms_days": buyers[o.buyer_id].payment_terms_days
                        if o.buyer_id in buyers
                        else None,
                        "rejection_rate": _maybe_float(
                            buyers[o.buyer_id].rejection_rate if o.buyer_id in buyers else None
                        ),
                    }
                    for o in offers
                ],
            }
        )
    return {"lots": payload}
