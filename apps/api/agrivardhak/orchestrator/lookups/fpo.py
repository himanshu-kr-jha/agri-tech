"""Organization-scoped lookups (FPO / PACS / SHG staff).

Every function returns ``list[Claim]``, reusing the packet's own ``Claim`` type rather than
inventing a parallel one. That single choice is what keeps citation mandatory —
``Claim.evidence`` is ``Field(min_length=1)``, so a lookup physically cannot return a
sentence with nothing behind it — and it lets one renderer and one grounding validator serve
both the lookup and the decision paths.

Most lookups are a thin shell over an intelligence module that already exists and is already
tested. That is not laziness: a lookup that re-derived production figures with its own query
would drift from the module the Decision Packet uses, and then the same collective would
have two different expected tonnages depending on how you asked.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agrivardhak.domain import enums, irrigation
from agrivardhak.domain.models.crops import Crop, CropCycle, Variety
from agrivardhak.domain.models.land import Farm, Plot
from agrivardhak.domain.models.market import RiskRegisterEntry
from agrivardhak.domain.models.organization import Farmer, Membership
from agrivardhak.domain.models.provenance import DataDiscrepancy, Observation
from agrivardhak.intelligence import quality
from agrivardhak.intelligence.contracts import AffectedSet, EvidenceRef
from agrivardhak.orchestrator import briefing as briefing_service
from agrivardhak.orchestrator import engine, gather, reconcile
from agrivardhak.orchestrator.assistant_contracts import LookupKey
from agrivardhak.orchestrator.packet import Claim

#: Confidence for a statement about our own rows — "three recommendations are awaiting
#: approval", "eight data conflicts are open". These are not predictions and hedging them
#: would be false modesty. Whether the underlying row is *right* is a separate question,
#: which provenance already carries on the row itself (INV-3).
RECORD_FACT = 1.0

#: How many claims a lookup may return. A lookup that answers with twenty claims has not
#: answered; it has forwarded the database.
MAX_CLAIMS = 6

#: Price movement worth reporting as news, as a fraction. Below this, mandi series noise
#: dominates and every crop looks like it is doing something.
PRICE_MOVE_THRESHOLD = 0.08

#: How far back "recently" reaches for WHATS_CHANGED.
CHANGE_WINDOW_DAYS = 14

#: Which intelligence module answers which lookup, and what must run first for it to be
#: sized correctly. Risk needs Quality's tonnage or its exposure figures fall back to
#: planted area — a quietly worse answer rather than a visibly missing one.
_MODULE_BACKED: dict[LookupKey, tuple[list[str], str]] = {
    LookupKey.PRODUCTION_FORECAST: (["quality"], "quality"),
    LookupKey.RISK_SUMMARY: (["quality", "risk"], "risk"),
    LookupKey.SCHEME_ELIGIBILITY: (["scheme"], "scheme"),
    LookupKey.MARKET_SNAPSHOT: (["market"], "market"),
    LookupKey.FUNDING_POSITION: (["funding"], "funding"),
}


def run(
    session: Session,
    *,
    key: LookupKey,
    organization_id: uuid.UUID,
    as_of: dt.datetime,
    entities: dict[str, Any] | None = None,
) -> list[Claim]:
    """Dispatch one lookup. Unknown keys return nothing rather than guessing."""
    entities = entities or {}
    if key in _MODULE_BACKED:
        plan, primary = _MODULE_BACKED[key]
        return _from_module(
            session,
            organization_id=organization_id,
            as_of=as_of,
            plan=plan,
            primary=primary,
            focus_subject=entities.get("crop"),
        )
    if key is LookupKey.MEMBERSHIP_SUMMARY:
        return _membership_summary(session, organization_id=organization_id, as_of=as_of)
    if key is LookupKey.LAND_SUMMARY:
        return _land_summary(session, organization_id=organization_id, as_of=as_of)
    if key is LookupKey.TODAYS_PRIORITIES:
        return _todays_priorities(session, organization_id=organization_id, as_of=as_of)
    if key is LookupKey.FARMERS_NEEDING_ATTENTION:
        return _farmers_needing_attention(session, organization_id=organization_id, as_of=as_of)
    if key is LookupKey.WHATS_CHANGED:
        return _whats_changed(session, organization_id=organization_id, as_of=as_of)
    return []


# --------------------------------------------------------------------------- module-backed


def _from_module(
    session: Session,
    *,
    organization_id: uuid.UUID,
    as_of: dt.datetime,
    plan: list[str],
    primary: str,
    focus_subject: str | None = None,
) -> list[Claim]:
    """Run the module the orchestrator would run, and return its findings as claims.

    Ranked by the same ``impact x confidence x urgency`` the Decision Packet uses — including
    the same subject focus — so the first claim in a lookup is the first claim a packet would
    have led with. Two different answers to the same underlying question, ordered
    differently, would be worse than either.
    """
    outputs, _inputs = engine.run_modules(
        session, organization_id=organization_id, as_of=as_of, plan=plan
    )
    output = outputs.get(primary)
    if output is None:
        return []
    ranked = reconcile.rank_findings([output], as_of, focus_subject)
    claims = [reconcile.to_claim(r.finding) for r in ranked[:MAX_CLAIMS]]
    if focus_subject and not any(focus_subject.lower() in r.finding.key.lower() for r in ranked):
        # Say it rather than quietly answer a different question. A CEO who asked about
        # guava and is shown paddy needs to know which one they are reading.
        claims.insert(
            0,
            Claim(
                statement=(
                    f"Nothing on record is specific to {focus_subject}. What follows is the "
                    f"collective's wider position rather than an answer about "
                    f"{focus_subject}."
                ),
                confidence=RECORD_FACT,
                evidence=[
                    EvidenceRef(
                        kind="domain_row",
                        id=organization_id,
                        label=f"no {focus_subject}-specific findings in {primary}",
                        as_of=as_of,
                    )
                ],
            ),
        )
    return claims[:MAX_CLAIMS]


# --------------------------------------------------------------------------- who we are


def _org_ref(organization_id: uuid.UUID, label: str, as_of: dt.datetime) -> EvidenceRef:
    return EvidenceRef(kind="domain_row", id=organization_id, label=label, as_of=as_of)


def _membership_summary(
    session: Session, *, organization_id: uuid.UUID, as_of: dt.datetime
) -> list[Claim]:
    """ "How many farmers do we have?" — and who they are.

    The plainest question a CEO can ask, and until this existed the assistant answered it
    with a season-long crop plan: the lookup vocabulary had been designed around decisions
    and left out plain facts, so the router had nothing to route to.

    Reports the composition, not just the count. Women members, social category and holding
    size are the figures every FPO is asked for by a funder or a scheme, and they are already
    on the record — leaving them out would make this a worse answer for no saving.
    """
    active = session.execute(
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.organization_id == organization_id,
            Membership.status == enums.MembershipStatus.ACTIVE,
        )
    ).scalar_one()
    total = session.execute(
        select(func.count())
        .select_from(Membership)
        .where(Membership.organization_id == organization_id)
    ).scalar_one()

    claims: list[Claim] = [
        Claim(
            statement=(
                f"The collective has {active:,} active members"
                + (f" of {total:,} on the register." if total != active else ".")
            ),
            magnitude=Decimal(active),
            unit="members",
            confidence=RECORD_FACT,
            evidence=[_org_ref(organization_id, f"{active} active memberships", as_of)],
        )
    ]

    women, disabled, households = session.execute(
        select(
            func.count().filter(Farmer.is_woman_farmer.is_(True)),
            func.count().filter(Farmer.has_disability.is_(True)),
            func.avg(Farmer.household_size),
        )
        .select_from(Farmer)
        .join(Membership, Membership.farmer_id == Farmer.id)
        .where(Membership.organization_id == organization_id)
    ).one()
    if women:
        claims.append(
            Claim(
                statement=(
                    f"{women:,} members are women farmers — {women / max(total, 1):.0%} of the "
                    f"register"
                    + (
                        f". Average household size is {float(households):.1f}."
                        if households
                        else "."
                    )
                ),
                magnitude=Decimal(women),
                unit="members",
                confidence=RECORD_FACT,
                evidence=[_org_ref(organization_id, f"{women} women members on record", as_of)],
            )
        )
    if disabled:
        claims.append(
            Claim(
                statement=f"{disabled:,} members have a recorded disability.",
                magnitude=Decimal(disabled),
                unit="members",
                confidence=RECORD_FACT,
                evidence=[
                    _org_ref(organization_id, f"{disabled} members with a disability", as_of)
                ],
            )
        )

    categories = session.execute(
        select(Farmer.category, func.count())
        .join(Membership, Membership.farmer_id == Farmer.id)
        .where(Membership.organization_id == organization_id, Farmer.category.is_not(None))
        .group_by(Farmer.category)
        .order_by(func.count().desc())
    ).all()
    if categories:
        mix = ", ".join(f"{name} {count:,}" for name, count in categories)
        claims.append(
            Claim(
                statement=f"Social category mix on the register: {mix}.",
                confidence=RECORD_FACT,
                evidence=[_org_ref(organization_id, "member category breakdown", as_of)],
            )
        )

    villages, blocks, tracts = session.execute(
        select(
            func.count(func.distinct(Farmer.village)),
            func.count(func.distinct(Farmer.block)),
            func.count(func.distinct(Farmer.tract)),
        )
        .select_from(Farmer)
        .join(Membership, Membership.farmer_id == Farmer.id)
        .where(Membership.organization_id == organization_id)
    ).one()
    claims.append(
        Claim(
            statement=(
                f"Members are spread across {villages:,} villages in {blocks:,} blocks and "
                f"{tracts} agro-climatic tracts."
            ),
            magnitude=Decimal(villages),
            unit="villages",
            confidence=RECORD_FACT,
            evidence=[_org_ref(organization_id, f"{villages} villages on the register", as_of)],
        )
    )

    synthetic = session.execute(
        select(func.count())
        .select_from(Farmer)
        .join(Membership, Membership.farmer_id == Farmer.id)
        .where(Membership.organization_id == organization_id, Farmer.is_synthetic.is_(True))
    ).scalar_one()
    if synthetic:
        # CLAUDE.md §5: synthetic data is labelled in the data *and* wherever it is presented.
        # A membership count is exactly the number someone would quote in a pitch.
        claims.append(
            Claim(
                statement=(
                    f"{synthetic:,} of these member records are SYNTHETIC — DEMO ONLY. They "
                    f"model a real Prayagraj district profile but describe no real person."
                ),
                magnitude=Decimal(synthetic),
                unit="members",
                confidence=RECORD_FACT,
                evidence=[
                    _org_ref(organization_id, f"{synthetic} synthetic member records", as_of)
                ],
            )
        )
    return claims[:MAX_CLAIMS]


def _land_summary(
    session: Session, *, organization_id: uuid.UUID, as_of: dt.datetime
) -> list[Claim]:
    """ "How much land do we have?" — area, plots, water, and where it is."""
    plots, area = session.execute(
        select(func.count(Plot.id), func.sum(Plot.area_sqm))
        .join(Farm, Plot.farm_id == Farm.id)
        .join(Farmer, Farm.operator_farmer_id == Farmer.id)
        .join(Membership, Membership.farmer_id == Farmer.id)
        .where(Membership.organization_id == organization_id)
    ).one()
    if not plots:
        return [
            Claim(
                statement="No plots are recorded against this collective's members yet.",
                confidence=RECORD_FACT,
                evidence=[_org_ref(organization_id, "no plots on record", as_of)],
            )
        ]

    acres = float(area or 0) / 4046.86
    claims = [
        Claim(
            statement=(
                f"Members operate {acres:,.0f} acres ({float(area or 0) / 10_000:,.0f} ha) "
                f"across {plots:,} plots — an average of {acres / plots:.2f} acres a plot."
            ),
            magnitude=Decimal(str(round(float(area or 0), 2))),
            unit="sqm",
            confidence=RECORD_FACT,
            evidence=[
                _org_ref(organization_id, f"{plots} plots totalling {acres:,.0f} acres", as_of)
            ],
        )
    ]

    irrigated = session.execute(
        select(func.count())
        .select_from(Plot)
        .join(Farm, Plot.farm_id == Farm.id)
        .join(Farmer, Farm.operator_farmer_id == Farmer.id)
        .join(Membership, Membership.farmer_id == Farmer.id)
        .where(
            Membership.organization_id == organization_id,
            func.upper(func.trim(func.coalesce(Plot.irrigation_source, ""))).not_in(
                sorted(irrigation.RAINFED_MARKERS)
            ),
        )
    ).scalar_one()
    claims.append(
        Claim(
            statement=(
                f"{irrigated:,} plots have an assured water source and "
                f"{plots - irrigated:,} are rain-fed — {irrigated / plots:.0%} irrigated. "
                f"Water is the single largest yield factor the model can see."
            ),
            magnitude=Decimal(irrigated),
            unit="plots",
            confidence=RECORD_FACT,
            evidence=[_org_ref(organization_id, f"{irrigated} irrigated plots", as_of)],
        )
    )

    by_tract = session.execute(
        select(Farmer.tract, func.sum(Plot.area_sqm))
        .join(Farm, Farm.operator_farmer_id == Farmer.id)
        .join(Plot, Plot.farm_id == Farm.id)
        .join(Membership, Membership.farmer_id == Farmer.id)
        .where(Membership.organization_id == organization_id, Farmer.tract.is_not(None))
        .group_by(Farmer.tract)
        .order_by(func.sum(Plot.area_sqm).desc())
    ).all()
    if by_tract:
        spread = ", ".join(
            f"{tract.replace('_', '-').title()} {float(a or 0) / 4046.86:,.0f} acres"
            for tract, a in by_tract
        )
        claims.append(
            Claim(
                statement=f"By tract: {spread}.",
                confidence=RECORD_FACT,
                evidence=[_org_ref(organization_id, "operated area by tract", as_of)],
            )
        )
    return claims[:MAX_CLAIMS]


# --------------------------------------------------------------------------- priorities


def _todays_priorities(
    session: Session, *, organization_id: uuid.UUID, as_of: dt.datetime
) -> list[Claim]:
    """ "What should I prioritise today?" — the briefing, spoken rather than laid out.

    Wraps ``briefing.build`` instead of re-deriving it. The briefing already encodes the
    editorial judgement about what earns a place on a fifteen-second screen, and a second
    implementation of that judgement would drift from the first within a week.
    """
    briefing = briefing_service.build(session, organization_id=organization_id, as_of=as_of)

    if briefing.is_quiet:
        return [
            Claim(
                statement=(
                    "Nothing is waiting on a decision, no deadline falls inside the next "
                    "two weeks, and no high-impact risk is open. A quiet day is a real "
                    "answer, not an empty screen."
                ),
                confidence=RECORD_FACT,
                evidence=[
                    EvidenceRef(
                        kind="domain_row",
                        id=organization_id,
                        label="organization decision queue, checked and empty",
                        as_of=as_of,
                    )
                ],
            )
        ]

    claims: list[Claim] = []
    sections = (
        ("Needs a decision", briefing.needs_decision),
        ("Closing soon", briefing.closing_soon),
        ("Worth watching", briefing.watch),
        ("Data health", briefing.data_health),
    )
    for label, items in sections:
        for item in items:
            if len(claims) >= MAX_CLAIMS:
                return claims
            claims.append(
                Claim(
                    statement=f"{label}: {item.headline}"
                    + (f" — {item.detail}" if item.detail else ""),
                    magnitude=Decimal(item.value_paise) if item.value_paise else None,
                    unit=item.unit,
                    confidence=RECORD_FACT,
                    evidence=[
                        EvidenceRef(
                            kind="domain_row",
                            id=item.subject_id or organization_id,
                            label=item.headline,
                            as_of=as_of,
                        )
                    ],
                )
            )
    return claims


# --------------------------------------------------------------------------- attention


def _farmers_needing_attention(
    session: Session, *, organization_id: uuid.UUID, as_of: dt.datetime
) -> list[Claim]:
    """Who needs a field officer, and why — grouped by reason, never ranked by worth.

    Three reasons, in the order a field officer would care about them: a crop below the
    grade-B health line, a cycle nobody has ever looked at, and a value two sources disagree
    about. The health threshold is ``YieldModel.grade_b_health`` rather than a number chosen
    here, so "needing attention" means the same thing as it does in the yield model.

    Deliberately *not* a ranked list of farmers. FR-605 and SAF-04 forbid anything resembling
    an ordering of members by merit, and a list headed "farmers needing attention" sorted
    worst-first is exactly that with a friendlier title.
    """
    threshold = quality.YieldModel().grade_b_health
    claims: list[Claim] = []

    latest = (
        select(
            Observation.subject_id.label("cycle_id"),
            func.max(Observation.observed_at).label("seen_at"),
        )
        .where(
            Observation.subject_type == "crop_cycle",
            Observation.attribute == "crop_health_pct",
            Observation.superseded_by.is_(None),
        )
        .group_by(Observation.subject_id)
        .subquery()
    )

    rows = session.execute(
        select(CropCycle.id, Crop.name, Farmer.id, Farmer.full_name, Farmer.village, Observation)
        .join(Variety, CropCycle.variety_id == Variety.id)
        .join(Crop, Variety.crop_id == Crop.id)
        .join(Plot, CropCycle.plot_id == Plot.id)
        .join(Farm, Plot.farm_id == Farm.id)
        .join(Farmer, Farm.operator_farmer_id == Farmer.id)
        .outerjoin(latest, latest.c.cycle_id == CropCycle.id)
        .outerjoin(
            Observation,
            (Observation.subject_id == latest.c.cycle_id)
            & (Observation.observed_at == latest.c.seen_at)
            & (Observation.attribute == "crop_health_pct"),
        )
        .where(
            CropCycle.status.in_(
                (
                    enums.CropCycleStatus.SOWN,
                    enums.CropCycleStatus.GROWING,
                    enums.CropCycleStatus.HARVEST_READY,
                )
            )
        )
    ).all()

    ailing: list[tuple[str, str, Observation]] = []
    unseen: list[tuple[uuid.UUID, str, str]] = []
    seen_cycles: set[uuid.UUID] = set()
    for cycle_id, crop_name, farmer_id, farmer_name, village, observation in rows:
        if cycle_id in seen_cycles:  # ties on observed_at can duplicate a cycle
            continue
        seen_cycles.add(cycle_id)
        if observation is None or observation.value_numeric is None:
            unseen.append((cycle_id, farmer_name, crop_name))
        elif float(observation.value_numeric) < threshold:
            ailing.append(
                (farmer_name, f"{crop_name} in {village or 'their village'}", observation)
            )
        del farmer_id

    if ailing:
        # Named by person, not by cycle. A farmer with two struggling plots is one person to
        # visit, and listing them twice reads as a bug rather than as thoroughness.
        by_person: dict[str, str] = {}
        for name, what, _o in ailing:
            by_person.setdefault(name, what)
        shown = list(by_person.items())[:4]
        named = ", ".join(f"{name} ({what})" for name, what in shown)
        claims.append(
            Claim(
                statement=(
                    f"{len(ailing)} crop cycles across {len(by_person)} farmers are below "
                    f"the grade-B health line of {threshold:.0f}%, which is where a cycle "
                    f"starts losing a grade rather than only losing yield. {named}"
                    + (
                        f", and {len(by_person) - len(shown)} more."
                        if len(by_person) > len(shown)
                        else "."
                    )
                ),
                magnitude=Decimal(len(ailing)),
                unit="crop cycles",
                # The resolver's own confidence in the weakest reading behind this claim.
                # Reporting 1.0 would assert the readings are right, which is a different
                # claim from "this is what the readings say".
                confidence=min(float(o.confidence) for _n, _w, o in ailing),
                evidence=[
                    EvidenceRef(
                        kind="observation",
                        id=o.id,
                        label=f"crop_health_pct = {o.value_numeric} ({name})",
                        as_of=o.observed_at,
                    )
                    for name, _w, o in ailing[:5]
                ],
            )
        )

    if unseen:
        claims.append(
            Claim(
                statement=(
                    f"{len(unseen)} active cycles have no health reading at all. These are "
                    f"not healthy cycles — they are unobserved ones, and every production "
                    f"figure that includes them carries the gap (FR-103)."
                ),
                magnitude=Decimal(len(unseen)),
                unit="crop cycles",
                confidence=RECORD_FACT,
                evidence=[
                    EvidenceRef(
                        kind="domain_row",
                        id=cycle_id,
                        label=f"{crop} cycle for {name}, never observed",
                        as_of=as_of,
                    )
                    for cycle_id, name, crop in unseen[:5]
                ],
                affected=AffectedSet(crop_cycle_ids=[c for c, _n, _cr in unseen[:200]]),
            )
        )

    disputed = list(
        session.execute(
            select(DataDiscrepancy)
            .where(DataDiscrepancy.status == enums.DiscrepancyStatus.OPEN)
            .order_by(DataDiscrepancy.spread_pct.desc())
            .limit(5)
        ).scalars()
    )
    if disputed:
        claims.append(
            Claim(
                statement=(
                    f"{len(disputed)} values are disputed between sources and are waiting on "
                    f"someone with verification authority. The widest disagreement is "
                    f"{float(disputed[0].spread_pct):.0f}% on "
                    f"'{disputed[0].attribute}'. Nothing derived from these is wrong — it is "
                    f"carrying reduced confidence until a human decides (INV-4)."
                ),
                magnitude=Decimal(len(disputed)),
                unit="disputed values",
                confidence=RECORD_FACT,
                evidence=[
                    EvidenceRef(
                        kind="domain_row",
                        id=d.id,
                        label=f"{d.attribute} disputed, {float(d.spread_pct):.0f}% spread",
                        as_of=as_of,
                    )
                    for d in disputed
                ],
            )
        )

    if not claims:
        claims.append(
            Claim(
                statement=(
                    "No cycle is below the grade-B health line, every active cycle has been "
                    "observed, and no value is in dispute."
                ),
                confidence=RECORD_FACT,
                evidence=[
                    EvidenceRef(
                        kind="domain_row",
                        id=organization_id,
                        label="member health and data-conflict check, all clear",
                        as_of=as_of,
                    )
                ],
            )
        )
    return claims[:MAX_CLAIMS]


# --------------------------------------------------------------------------- what changed


def _whats_changed(
    session: Session, *, organization_id: uuid.UUID, as_of: dt.datetime
) -> list[Claim]:
    """What moved recently, from data we actually hold.

    Not the causal-chain engine the product vision describes — that needs an ingested news
    feed this repository does not have, and a fabricated headline driving a fabricated chain
    would be worse than saying less. What it does report is real: mandi prices from the
    Agmarknet backfill, conflicts that opened, and risks that were registered.
    """
    claims: list[Claim] = []
    since = as_of - dt.timedelta(days=CHANGE_WINDOW_DAYS)

    for crop_name, points in gather.price_history(session).items():
        if len(points) < 2:
            continue
        latest = points[-1]
        # The series is ascending, so walk back to the last point at least a fortnight old.
        earlier = next(
            (p for p in reversed(points) if (latest.date - p.date).days >= CHANGE_WINDOW_DAYS),
            None,
        )
        if earlier is None or not earlier.modal_paise_per_kg:
            continue
        move = (latest.modal_paise_per_kg - earlier.modal_paise_per_kg) / earlier.modal_paise_per_kg
        if abs(move) < PRICE_MOVE_THRESHOLD:
            continue
        claims.append(
            Claim(
                statement=(
                    f"{crop_name} modal price has moved {move:+.0%} in "
                    f"{(latest.date - earlier.date).days} days, from Rs "
                    f"{earlier.modal_paise_per_kg / 100:.2f} to Rs "
                    f"{latest.modal_paise_per_kg / 100:.2f} per kg. Any decision that assumed "
                    f"the earlier price is worth re-reading."
                ),
                magnitude=Decimal(latest.modal_paise_per_kg),
                unit="paise_per_kg",
                # Observed mandi records, not a forecast. The arithmetic is exact; what it
                # means for next month is a different claim this one does not make.
                confidence=RECORD_FACT,
                evidence=[latest.evidence, earlier.evidence],
            )
        )

    fresh_conflicts = session.execute(
        select(func.count())
        .select_from(DataDiscrepancy)
        .where(
            DataDiscrepancy.status == enums.DiscrepancyStatus.OPEN,
            DataDiscrepancy.created_at >= since,
        )
    ).scalar_one()
    if fresh_conflicts:
        claims.append(
            Claim(
                statement=(
                    f"{fresh_conflicts} new data conflicts opened in the last "
                    f"{CHANGE_WINDOW_DAYS} days. Sources began disagreeing about values that "
                    f"were previously settled."
                ),
                magnitude=Decimal(fresh_conflicts),
                unit="conflicts",
                confidence=RECORD_FACT,
                evidence=[
                    EvidenceRef(
                        kind="domain_row",
                        id=organization_id,
                        label=f"{fresh_conflicts} discrepancies opened since {since:%d %b}",
                        as_of=as_of,
                    )
                ],
            )
        )

    for entry in session.execute(
        select(RiskRegisterEntry)
        .where(
            RiskRegisterEntry.organization_id == organization_id,
            RiskRegisterEntry.created_at >= since,
        )
        .order_by(RiskRegisterEntry.created_at.desc())
        .limit(3)
    ).scalars():
        claims.append(
            Claim(
                statement=(
                    f"New on the risk register: {entry.title} — "
                    f"{entry.likelihood.value.lower()} likelihood, "
                    f"{entry.impact.value.lower()} impact."
                ),
                magnitude=Decimal(entry.value_at_risk_paise) if entry.value_at_risk_paise else None,
                unit="paise" if entry.value_at_risk_paise else None,
                confidence=RECORD_FACT,
                evidence=[
                    EvidenceRef(
                        kind="domain_row", id=entry.id, label=entry.title, as_of=entry.created_at
                    )
                ],
            )
        )

    if not claims:
        claims.append(
            Claim(
                statement=(
                    f"Nothing material has changed in the last {CHANGE_WINDOW_DAYS} days: no "
                    f"crop price moved more than {PRICE_MOVE_THRESHOLD:.0%}, no new conflicts "
                    f"opened, and no risk was registered."
                ),
                confidence=RECORD_FACT,
                evidence=[
                    EvidenceRef(
                        kind="domain_row",
                        id=organization_id,
                        label=f"change check over {CHANGE_WINDOW_DAYS} days, nothing material",
                        as_of=as_of,
                    )
                ],
            )
        )
    return claims[:MAX_CLAIMS]
