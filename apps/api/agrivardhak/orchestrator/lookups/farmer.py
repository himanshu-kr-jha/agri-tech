"""Farmer-scoped lookups — one member's own world, and nothing else (INV-5).

**This module shares no query code with** :mod:`agrivardhak.orchestrator.lookups.fpo`, and
that is deliberate. The information boundary must not depend on a ``ContextScope`` argument
being threaded correctly through a shared helper: it should be impossible to reach an
organization-wide query from a farmer turn because the function is not in scope here. This
is the pattern the ``/farmer/today`` endpoint already set — build farmer-scoped from the
start rather than filter an organization result down, so org-internal rows are never in the
result set at all and no later bug can leak them.

Every query below begins from ``Farm.operator_farmer_id == farmer_id`` or from a row that
carries the farmer's own id. There is no code path here that reads another member's data, the
collective's buyer negotiations, or anything whose visibility is ``ORG_INTERNAL``.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from agrivardhak.domain import enums, irrigation
from agrivardhak.domain.models.crops import Crop, CropCycle, Variety
from agrivardhak.domain.models.decisions import Recommendation
from agrivardhak.domain.models.land import Farm, Plot
from agrivardhak.domain.models.operations import CalendarEvent
from agrivardhak.domain.models.organization import Announcement, Farmer
from agrivardhak.domain.units import format_lakh
from agrivardhak.intelligence import quality, scheme
from agrivardhak.intelligence.contracts import AffectedSet, EvidenceRef
from agrivardhak.orchestrator.assistant_contracts import LookupKey
from agrivardhak.orchestrator.packet import Claim
from agrivardhak.provenance import resolver

RECORD_FACT = 1.0
MAX_CLAIMS = 6

#: Active cycle statuses. A harvested cycle is history, not something to act on today.
_ACTIVE = (
    enums.CropCycleStatus.SOWN,
    enums.CropCycleStatus.GROWING,
    enums.CropCycleStatus.HARVEST_READY,
)

#: What a farmer is allowed to see cross the boundary from the organization. ``ORG_INTERNAL``
#: is absent on purpose and must stay absent — not even for rows that are *about* this
#: farmer. Buyer negotiation state concerning their own lot is still the collective's until
#: the collective shares it (context.md §4).
_VISIBLE_TO_MEMBERS = (
    enums.VisibilityScope.SHARED_WITH_MEMBERS,
    enums.VisibilityScope.PUBLIC,
)


def run(
    session: Session,
    *,
    key: LookupKey,
    farmer_id: uuid.UUID,
    as_of: dt.datetime,
    entities: dict[str, Any] | None = None,
) -> list[Claim]:
    """Dispatch one farmer lookup. Unknown keys return nothing rather than guessing."""
    del entities
    if key is LookupKey.MY_FARM_PROFILE:
        return _my_farm_profile(session, farmer_id=farmer_id, as_of=as_of)
    if key is LookupKey.MY_YIELD_GAP:
        return _my_yield_gap(session, farmer_id=farmer_id, as_of=as_of)
    if key is LookupKey.MY_TASKS_TODAY:
        return _my_tasks_today(session, farmer_id=farmer_id, as_of=as_of)
    if key is LookupKey.MY_SCHEMES:
        return _my_schemes(session, farmer_id=farmer_id, as_of=as_of)
    if key is LookupKey.MY_ANNOUNCEMENTS:
        return _my_announcements(session, farmer_id=farmer_id, as_of=as_of)
    return []


def _my_cycles(session: Session, farmer_id: uuid.UUID) -> list[tuple[CropCycle, str, str, Plot]]:
    """This farmer's active cycles. The only entry point to crop data in this module."""
    return [
        tuple(row)
        for row in session.execute(
            select(CropCycle, Crop.name, Variety.name, Plot)
            .join(Variety, CropCycle.variety_id == Variety.id)
            .join(Crop, Variety.crop_id == Crop.id)
            .join(Plot, CropCycle.plot_id == Plot.id)
            .join(Farm, Plot.farm_id == Farm.id)
            .where(Farm.operator_farmer_id == farmer_id, CropCycle.status.in_(_ACTIVE))
        ).all()
    ]


# --------------------------------------------------------------------------- my farm


def _my_farm_profile(session: Session, *, farmer_id: uuid.UUID, as_of: dt.datetime) -> list[Claim]:
    """ "How much land do I have?" — the farmer's own plain facts.

    The mirror of the collective's membership question. A farmer asking how many acres they
    farm should not be routed into a yield-gap decomposition, which was the only place that
    number appeared before this existed.
    """
    subject = session.get(Farmer, farmer_id)
    if subject is None:
        return []

    rows = list(
        session.execute(
            select(Plot)
            .join(Farm, Plot.farm_id == Farm.id)
            .where(Farm.operator_farmer_id == farmer_id)
        ).scalars()
    )
    where = ", ".join(p for p in (subject.village, subject.block) if p) or "your area"
    if not rows:
        return [
            Claim(
                statement=(
                    f"You are on the register in {where}, but no plots are recorded against "
                    f"your name yet. A field officer can add them."
                ),
                confidence=RECORD_FACT,
                evidence=[
                    EvidenceRef(
                        kind="domain_row",
                        id=farmer_id,
                        label=f"{subject.full_name}, no plots recorded",
                        as_of=as_of,
                    )
                ],
            )
        ]

    total_sqm = sum((Decimal(str(p.area_sqm)) for p in rows), Decimal(0))
    acres = float(total_sqm) / 4046.86
    irrigated = [p for p in rows if irrigation.water_assured(p.irrigation_source)]
    cycles = _my_cycles(session, farmer_id)

    claims = [
        Claim(
            statement=(
                f"You farm {acres:.2f} acres across {len(rows)} "
                f"{'plot' if len(rows) == 1 else 'plots'} in {where}."
            ),
            magnitude=Decimal(str(round(float(total_sqm), 2))),
            unit="sqm",
            confidence=RECORD_FACT,
            evidence=[
                EvidenceRef(
                    kind="domain_row",
                    id=p.id,
                    label=f"{p.label or 'plot'} · {float(p.area_sqm) / 4046.86:.2f} acres",
                    as_of=as_of,
                )
                for p in rows[:4]
            ],
            affected=AffectedSet(plot_ids=[p.id for p in rows]),
        ),
        Claim(
            statement=(
                f"{len(irrigated)} of your {len(rows)} "
                f"{'plot has' if len(rows) == 1 else 'plots have'} an assured water source"
                + ("; the rest are rain-fed." if len(irrigated) < len(rows) else ".")
            ),
            magnitude=Decimal(len(irrigated)),
            unit="plots",
            confidence=RECORD_FACT,
            evidence=[
                EvidenceRef(
                    kind="domain_row",
                    id=(irrigated or rows)[0].id,
                    label=f"irrigation source on {len(rows)} plots",
                    as_of=as_of,
                )
            ],
        ),
    ]

    if cycles:
        growing = ", ".join(sorted({crop for _c, crop, _v, _p in cycles}))
        claims.append(
            Claim(
                statement=(
                    f"You currently have {len(cycles)} crop "
                    f"{'cycle' if len(cycles) == 1 else 'cycles'} growing: {growing}."
                ),
                magnitude=Decimal(len(cycles)),
                unit="crop cycles",
                confidence=RECORD_FACT,
                evidence=[
                    EvidenceRef(
                        kind="domain_row",
                        id=c.id,
                        label=f"{crop} cycle",
                        as_of=as_of,
                    )
                    for c, crop, _v, _p in cycles[:3]
                ],
                affected=AffectedSet(crop_cycle_ids=[c.id for c, _cr, _v, _p in cycles]),
            )
        )
    return claims[:MAX_CLAIMS]


# --------------------------------------------------------------------------- yield gap


#: How each yield multiplier reads to a farmer, and whether it is something they can change.
#: Naming the lever is the whole value of the answer — "your yield is low" helps nobody.
_FACTOR_LABEL: dict[str, tuple[str, str]] = {
    "health": ("crop health", "a field visit and the right intervention can move this"),
    "water": (
        "irrigation",
        "this plot is recorded as rain-fed; assured water is the single "
        "largest factor the model can see",
    ),
    "nutrient": ("nutrient plan", "the recorded plan was not followed"),
    "stress": (
        "season weather",
        "not something any farmer controls — it is here so the rest "
        "of the gap is not blamed on you",
    ),
    "tract": ("soil in your tract", "a property of where the plot is, not of how it is farmed"),
}


def _my_yield_gap(session: Session, *, farmer_id: uuid.UUID, as_of: dt.datetime) -> list[Claim]:
    """ "How can I increase my yield?" — answered by decomposition, not by advice.

    This deliberately invents no agronomy. ``quality.expected_yield_kg`` already returns the
    multipliers it applied, so the honest answer to "how do I get more" is to show which
    multiplier is costing the most and say plainly which ones are levers and which are not.
    Every coefficient traces to ``seed/sources.md``; none is made up here.

    What it does *not* do is prescribe a treatment. That is crop-health territory, where the
    knowledge base is unfilled and confidence is capped below the recommendation floor.
    """
    model = quality.YieldModel()
    claims: list[Claim] = []

    for cycle, crop_name, variety_name, plot in _my_cycles(session, farmer_id):
        variety = session.get(Variety, cycle.variety_id)
        base = (
            float(variety.base_yield_kg_per_ha)
            if variety and variety.base_yield_kg_per_ha
            else None
        )
        if not base:
            continue
        health = resolver.resolve(
            session,
            subject_type="crop_cycle",
            subject_id=cycle.id,
            attribute="crop_health_pct",
            as_of=as_of,
        )
        cycle_input = quality.CycleInput(
            cycle_id=cycle.id,
            crop_name=crop_name,
            variety_name=variety_name,
            farmer_id=farmer_id,
            plot_id=plot.id,
            area_sqm=Decimal(str(cycle.area_sqm)),
            sowing_date=cycle.sowing_date,
            duration_days=variety.duration_days if variety else None,
            base_yield_kg_per_ha=base,
            health=health,
            water_assured=irrigation.water_assured(plot.irrigation_source),
        )
        expected, factors = quality.expected_yield_kg(cycle_input, model)
        if "unavailable" in factors or expected <= 0:
            continue

        area_ha = factors["area_ha"]
        potential = base * area_ha
        # Rank the multipliers by how much each one costs, largest first. A multiplier of
        # 1.0 costs nothing and is not worth a farmer's attention.
        losses = sorted(
            ((name, 1.0 - float(factors[name])) for name in _FACTOR_LABEL if name in factors),
            key=lambda pair: -pair[1],
        )
        biggest = [(n, gap) for n, gap in losses if gap > 0.01][:2]
        if not biggest:
            continue

        reasons = "; ".join(
            f"{_FACTOR_LABEL[n][0]} is costing about {gap:.0%} ({_FACTOR_LABEL[n][1]})"
            for n, gap in biggest
        )
        claims.append(
            Claim(
                statement=(
                    f"Your {crop_name} ({variety_name}) is on track for about "
                    f"{float(expected):,.0f} kg against roughly {potential:,.0f} kg if every "
                    f"factor were ideal. The gap is mostly two things: {reasons}."
                ),
                magnitude=expected,
                unit="kg",
                # The prediction's own confidence, which already reflects how good the health
                # reading behind it is. Asserting more would be asserting the reading.
                confidence=health.confidence if health else 0.4,
                evidence=(
                    [health.evidence]
                    if health
                    else [
                        EvidenceRef(
                            kind="domain_row",
                            id=cycle.id,
                            label=f"{crop_name} cycle, no health reading on record",
                            as_of=as_of,
                        )
                    ]
                ),
                affected=AffectedSet(crop_cycle_ids=[cycle.id], plot_ids=[plot.id]),
            )
        )
        if len(claims) >= MAX_CLAIMS:
            break

    if not claims:
        return [
            Claim(
                statement=(
                    "There is not enough recorded about your crops yet to say where yield is "
                    "being lost. A health reading on each plot would change that more than "
                    "anything else."
                ),
                confidence=RECORD_FACT,
                evidence=[
                    EvidenceRef(
                        kind="domain_row",
                        id=farmer_id,
                        label="no cycle with both a yield coefficient and a health reading",
                        as_of=as_of,
                    )
                ],
            )
        ]
    return claims


# --------------------------------------------------------------------------- today


def _my_tasks_today(session: Session, *, farmer_id: uuid.UUID, as_of: dt.datetime) -> list[Claim]:
    """ "What should I do on my farm today?"

    Three sources, in order of how binding they are: an approved calendar event about one of
    this farmer's own cycles, an approved recommendation that targets them, and — failing
    both — where each crop actually is in its cycle. Only *approved* items appear: a
    suggestion nobody has signed off is not this farmer's instruction (INV-1).
    """
    cycles = _my_cycles(session, farmer_id)
    cycle_ids = [c.id for c, _cn, _vn, _p in cycles]
    claims: list[Claim] = []

    if cycle_ids:
        for event in session.execute(
            select(CalendarEvent)
            .where(
                CalendarEvent.subject_type == "crop_cycle",
                CalendarEvent.subject_id.in_(cycle_ids),
                CalendarEvent.status == enums.CalendarStatus.APPROVED,
                CalendarEvent.visibility.in_(_VISIBLE_TO_MEMBERS),
            )
            .order_by(CalendarEvent.starts_at)
            .limit(3)
        ).scalars():
            claims.append(
                Claim(
                    statement=f"{event.title} — scheduled for {event.starts_at:%d %b}.",
                    confidence=RECORD_FACT,
                    evidence=[
                        EvidenceRef(
                            kind="domain_row",
                            id=event.id,
                            label=f"approved calendar event: {event.title}",
                            as_of=event.starts_at,
                        )
                    ],
                )
            )

        for rec in session.execute(
            select(Recommendation)
            .where(
                Recommendation.target_type == "crop_cycle",
                Recommendation.target_id.in_(cycle_ids),
                Recommendation.status.in_(
                    (
                        enums.RecommendationStatus.APPROVED,
                        enums.RecommendationStatus.EXECUTED,
                    )
                ),
            )
            .order_by(Recommendation.created_at.desc())
            .limit(3)
        ).scalars():
            claims.append(
                Claim(
                    statement=f"Approved for your farm: {rec.title}. {rec.reasoning}",
                    confidence=float(rec.confidence),
                    evidence=[
                        EvidenceRef(
                            kind="domain_row",
                            id=rec.id,
                            label=f"approved recommendation: {rec.title}",
                            as_of=rec.created_at,
                        )
                    ],
                )
            )

    if not claims:
        for cycle, crop_name, _variety, _plot in cycles[:MAX_CLAIMS]:
            if cycle.expected_harvest_date is None:
                continue
            days = (cycle.expected_harvest_date - as_of.date()).days
            when = (
                f"about {days} days away"
                if days > 0
                else f"{abs(days)} days past its expected date"
            )
            claims.append(
                Claim(
                    statement=(
                        f"Your {crop_name} is {cycle.status.value.replace('_', ' ').lower()}; "
                        f"harvest is {when} ({cycle.expected_harvest_date:%d %b}). Nothing has "
                        f"been scheduled for you today."
                    ),
                    confidence=RECORD_FACT,
                    evidence=[
                        EvidenceRef(
                            kind="domain_row",
                            id=cycle.id,
                            label=f"{crop_name} cycle, expected harvest "
                            f"{cycle.expected_harvest_date:%d %b}",
                            as_of=as_of,
                        )
                    ],
                    affected=AffectedSet(crop_cycle_ids=[cycle.id]),
                )
            )

    return claims[:MAX_CLAIMS] or [
        Claim(
            statement="You have no active crop cycles on record, so there is nothing scheduled.",
            confidence=RECORD_FACT,
            evidence=[
                EvidenceRef(kind="domain_row", id=farmer_id, label="no active cycles", as_of=as_of)
            ],
        )
    ]


# --------------------------------------------------------------------------- schemes


def _my_schemes(session: Session, *, farmer_id: uuid.UUID, as_of: dt.datetime) -> list[Claim]:
    """ "What schemes may apply to me?" — including the ones blocked on a missing fact.

    Assessed live against ``scheme.SCHEMES`` rather than read from ``eligibility_assessment``,
    because nothing writes that table: the module computes assessments on demand and the FPO
    path does the same. Reading a table that is always empty would have produced a confident
    "no schemes apply to you", which is the worst possible wrong answer here.

    ``INSUFFICIENT_DATA`` is reported rather than hidden. A farmer told only about schemes
    they already qualify for never learns that one missing document stands between them and
    another one — and that is the more useful half of the answer (FR-563).
    """
    plots = list(
        session.execute(
            select(Plot)
            .join(Farm, Plot.farm_id == Farm.id)
            .where(Farm.operator_farmer_id == farmer_id)
        ).scalars()
    )
    subject = session.get(Farmer, farmer_id)
    if subject is None:
        return []

    holding_sqm = sum((Decimal(str(p.area_sqm)) for p in plots), Decimal(0))
    facts: dict[str, Any] = {
        "is_landholder": bool(plots),
        "has_land_record": bool(plots),
        "has_crop_cycle": bool(_my_cycles(session, farmer_id)),
        "holding_ha": float(holding_sqm / Decimal(10000)),
        # Aadhaar seeding, bank account and tax status are deliberately absent rather than
        # guessed. Absent becomes INSUFFICIENT_DATA and a named gap, which is actionable;
        # a guess becomes a false yes or a false no, neither of which anyone can act on.
    }
    evidence = [
        EvidenceRef(
            kind="domain_row",
            id=farmer_id,
            label=f"{subject.full_name}, {float(holding_sqm) / 4046.86:.2f} acres on record",
            as_of=as_of,
        )
    ]

    claims: list[Claim] = []
    for definition in scheme.SCHEMES:
        if definition.beneficiary != "FARMER":
            continue  # organization schemes are the collective's business, not this member's
        assessment = scheme.assess(
            definition,
            subject_type="farmer",
            subject_id=farmer_id,
            name=subject.full_name,
            facts=facts,
            evidence=evidence,
            as_of=as_of.date(),
            consented_purposes=frozenset({"SERVICE_DELIVERY"}),
        )
        blocked = ", ".join(assessment.unknown[:3])
        if assessment.status == "INSUFFICIENT_DATA" and blocked:
            statement = (
                f"{definition.name}: we cannot tell yet. What is missing is {blocked}. Once "
                f"that is on record the assessment completes — this is not a rejection."
            )
        elif assessment.status == "NOT_ELIGIBLE":
            continue  # a bare "no" with no lever in it is not worth a farmer's attention
        else:
            statement = (
                f"{definition.name}: {assessment.status.replace('_', ' ').lower()}. "
                f"{definition.summary}"
            )
        claims.append(
            Claim(
                statement=statement
                + (
                    f" Estimated benefit about Rs "
                    f"{format_lakh(assessment.estimated_benefit_paise)} lakh."
                    if assessment.estimated_benefit_paise
                    else ""
                ),
                magnitude=(
                    Decimal(assessment.estimated_benefit_paise)
                    if assessment.estimated_benefit_paise
                    else None
                ),
                unit="paise" if assessment.estimated_benefit_paise else None,
                confidence=assessment.confidence,
                evidence=assessment.evidence or evidence,
            )
        )
        if len(claims) >= MAX_CLAIMS:
            break

    return claims or [
        Claim(
            statement=(
                "No scheme in the catalogue currently matches what is on record for your holding."
            ),
            confidence=RECORD_FACT,
            evidence=evidence,
        )
    ]


# --------------------------------------------------------------------------- announcements


def _my_announcements(session: Session, *, farmer_id: uuid.UUID, as_of: dt.datetime) -> list[Claim]:
    """What the collective has actually shared — the whole of what crosses the boundary.

    ``Announcement`` is the *only* legitimate mechanism for organization information to reach
    a member (FR-105, INV-5), and the filter on ``visibility`` here is what makes that true
    rather than aspirational. An internal analysis stays internal until someone publishes it.
    """
    rows = list(
        session.execute(
            select(Announcement)
            .where(Announcement.visibility.in_(_VISIBLE_TO_MEMBERS))
            .order_by(Announcement.created_at.desc())
            .limit(MAX_CLAIMS)
        ).scalars()
    )
    if not rows:
        return [
            Claim(
                statement="The collective has not shared any announcements with members yet.",
                confidence=RECORD_FACT,
                evidence=[
                    EvidenceRef(
                        kind="domain_row",
                        id=farmer_id,
                        label="no announcements shared with members",
                        as_of=as_of,
                    )
                ],
            )
        ]
    return [
        Claim(
            statement=f"{row.title} — {row.body}",
            confidence=RECORD_FACT,
            evidence=[
                EvidenceRef(
                    kind="domain_row",
                    id=row.id,
                    label=f"announcement: {row.title}",
                    as_of=row.created_at,
                )
            ],
        )
        for row in rows
    ]
