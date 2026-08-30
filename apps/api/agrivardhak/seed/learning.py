"""Last season's closed loop — the rows that let the Impact panel say anything at all.

The rest of the seed builds a collective that has *not yet made a decision*: farmers, land,
crops, prices, conflicts. That is correct for a fresh install, and it leaves `/impact` empty,
which is also correct — the panel is honest about having nothing to report.

But a demo has to be able to show the loop closing, and the loop is the product's actual
claim: advice → approval → execution → **adherence** → outcome → attribution. So this module
seeds two prior seasons of it.

What makes this seed honest rather than a highlight reel
--------------------------------------------------------
**The attribution is not written down here.** Every scenario supplies only inputs — what was
advised, how faithfully it was followed, how late, what the outcome was, and which
confounders were present. The strength (HIGH / MODERATE / UNCERTAIN / CONFOUNDED) is decided
by :func:`agrivardhak.learning.attribution.attribute`, the same ladder the running system
uses. If that ladder is made stricter tomorrow, this seed gets stricter with it, and the demo
cannot drift away from the code.

**The majority are not clean wins.** Of fifteen executed actions, two earn HIGH, four
MODERATE, three come back UNCERTAIN, two are CONFOUNDED, and four are refused a score
outright — three because the advice was not followed and one because it was followed too
loosely to mean anything. That distribution is the point of the screen (SAF-12): a panel
reporting only successes would be measuring our own selection.

**Nothing reaches EXECUTED without an Approval row.** INV-1 is a property of the data, not
just of the API, so the seeded history has to satisfy it too — every recommendation here
carries a signed approval by a user holding the role that was entitled to give it.

Everything below is SYNTHETIC — DEMO ONLY. The yield figures it moves around come from the
same unsourced placeholders as the rest of the seed (`reference.CROPS`, pending
`seed/sources.md` A1-A5), which is why the snapshots carry that label in their payload.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import random
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from agrivardhak.domain import enums
from agrivardhak.domain.models.crops import CropCycle
from agrivardhak.domain.models.decisions import (
    Approval,
    DecisionPacket,
    EvidenceSnapshot,
    Intervention,
    Prediction,
    Recommendation,
)
from agrivardhak.domain.models.organization import Organization, RoleGrant, User
from agrivardhak.learning import attribution
from agrivardhak.orchestrator.engine import content_hash

#: Matches the orchestrator's own version string, so a seeded packet and a live one are
#: replayed by the same code path.
PROMPT_VERSION = "packet-v1"
MODEL_ID = "deterministic"

#: Stamped into every seeded snapshot payload so a historical figure is traceable to the
#: model that produced it rather than to a survey.
SYNTHETIC_NOTE = "modelled from the district profile"


@dataclasses.dataclass(frozen=True)
class Scenario:
    """One closed loop, described by its *inputs* only.

    ``expected_strength`` is documentation, not instruction — it records what the ladder
    should make of these inputs so a reader can see the intent, and
    :func:`seed_learning_loop` asserts the ladder agreed. If someone changes
    ``MATERIAL_CHANGE`` and this seed's shape shifts, the assertion says so loudly instead of
    the demo quietly becoming a highlight reel.
    """

    key: str
    rec_type: enums.RecommendationType
    title: str
    reasoning: str
    action_taken: str
    followed: enums.Adherence
    fidelity: float | None
    delay_days: int
    #: Relative move against baseline, e.g. ``+0.18`` for eighteen percent better.
    change: float
    conditions: dict[str, Any]
    confidence: float
    value_paise: int | None
    expected_strength: str | None
    note: str


_C = enums.RecommendationType
_A = enums.Adherence

#: Fifteen scenarios. Ordered by outcome quality only so the table is readable; they are
#: distributed across packets and seasons below.
SCENARIOS: tuple[Scenario, ...] = (
    # -- followed closely, moved materially, nothing else explains it -> HIGH ------------
    Scenario(
        key="stagger-paddy",
        rec_type=_C.LOT_ALLOCATION,
        title="Stagger the Paddy sale across the post-harvest months",
        reasoning=(
            "Paddy harvests into its annual price trough. Releasing the lot in three "
            "tranches rather than one moves most of the volume past the November floor."
        ),
        action_taken="Released the lot in three tranches: November, December, January.",
        followed=_A.YES,
        fidelity=0.95,
        delay_days=2,
        change=0.18,
        conditions={},
        confidence=0.72,
        value_paise=1_84_00_000,
        expected_strength="HIGH",
        note="The clean case. Followed, moved, no confounder we track.",
    ),
    Scenario(
        key="grade-before-sale",
        rec_type=_C.PROCUREMENT,
        title="Grade the Potato lot before offering it",
        reasoning=(
            "Ungraded lots price to their worst fraction. Grading at the collection centre "
            "costs two days and moves the A-grade share out of the blended price."
        ),
        action_taken="Graded at the collection centre; A-grade offered separately.",
        followed=_A.YES,
        fidelity=0.92,
        delay_days=0,
        change=0.21,
        conditions={},
        confidence=0.68,
        value_paise=96_50_000,
        expected_strength="HIGH",
        note="Second clean case, from a different module.",
    ),
    # -- followed, moved, but less decisively -> MODERATE ---------------------------------
    Scenario(
        key="wheat-buyer",
        rec_type=_C.BUYER_SELECTION,
        title="Sell the Wheat lot to the nearer mill despite the lower headline price",
        reasoning=(
            "The distant buyer's headline price is higher; after freight, a 21-day payment "
            "delay and its rejection history, the nearer mill nets more."
        ),
        action_taken="Sold to the nearer mill.",
        followed=_A.YES,
        fidelity=0.80,
        delay_days=3,
        change=0.17,
        conditions={},
        confidence=0.70,
        value_paise=1_12_00_000,
        expected_strength="MODERATE",
        note="Moved well, but fidelity under 0.85 keeps it off HIGH.",
    ),
    Scenario(
        key="ipm-first",
        rec_type=_C.CROP_PROTECTION,
        title="Run the IPM ladder on the Paddy blocks before any spray",
        reasoning=(
            "Prevention and cultural controls first; chemical only if scouting thresholds "
            "are crossed. Consult the label and a local agronomist before any application."
        ),
        action_taken="Scouted weekly; pheromone traps set; no chemical application needed.",
        followed=_A.YES,
        fidelity=0.88,
        delay_days=1,
        change=0.09,
        conditions={},
        confidence=0.61,
        value_paise=None,
        expected_strength="MODERATE",
        note="Real but modest move.",
    ),
    Scenario(
        key="input-bulk",
        rec_type=_C.PROCUREMENT,
        title="Buy Rabi seed and fertiliser as one collective order",
        reasoning=(
            "Two hundred members bought the same inputs individually last season. One order "
            "clears the supplier's bulk threshold."
        ),
        action_taken="Placed a single order for 140 of the 200 members who opted in.",
        followed=_A.PARTIAL,
        fidelity=0.72,
        delay_days=5,
        change=0.11,
        conditions={},
        confidence=0.66,
        value_paise=42_00_000,
        expected_strength="MODERATE",
        note="Partial uptake — 140 of 200 — is the ordinary case, not the exception.",
    ),
    Scenario(
        key="storage-hold",
        rec_type=_C.LOT_ALLOCATION,
        title="Hold a quarter of the Potato lot into the February recovery",
        reasoning=(
            "Cold-store capacity covers a quarter of the lot. Storage cost and weight loss "
            "are charged against the expected recovery, not ignored."
        ),
        action_taken="Held 18% rather than 25% — cold store was already part-committed.",
        followed=_A.PARTIAL,
        fidelity=0.68,
        delay_days=4,
        change=-0.08,
        conditions={},
        confidence=0.58,
        value_paise=28_00_000,
        expected_strength="MODERATE",
        note="A real, material move in the WRONG direction. It belongs on the panel.",
    ),
    # -- inside ordinary variation -> UNCERTAIN -------------------------------------------
    Scenario(
        key="sowing-window",
        rec_type=_C.SCHEDULE,
        title="Bring the Wheat sowing window forward by eight days",
        reasoning=(
            "Late sowing runs grain-fill into the March heat. Eight days earlier keeps the "
            "window inside the historical band."
        ),
        action_taken="Sowing advisory issued; most members sowed within the window.",
        followed=_A.YES,
        fidelity=0.90,
        delay_days=1,
        change=0.02,
        conditions={},
        confidence=0.64,
        value_paise=None,
        expected_strength="UNCERTAIN",
        note="Followed well and barely moved. Honest answer: we cannot tell.",
    ),
    Scenario(
        key="moisture-check",
        rec_type=_C.SCHEDULE,
        title="Test moisture at intake rather than at the mandi gate",
        reasoning=(
            "Moisture deductions are applied at the buyer's gate on the buyer's meter. "
            "Testing at intake gives the collective its own number to argue from."
        ),
        action_taken="Meter bought; intake testing ran for the season.",
        followed=_A.YES,
        fidelity=0.86,
        delay_days=0,
        change=-0.03,
        conditions={},
        confidence=0.59,
        value_paise=None,
        expected_strength="UNCERTAIN",
        note="No detectable effect either way.",
    ),
    Scenario(
        key="mustard-share",
        rec_type=_C.CROP_PLAN,
        title="Lift the Mustard share on the Yamuna-Par tract",
        reasoning=(
            "Highest return per rupee of the options this tract's water and season allow, "
            "ranked on the pessimistic end of the price band."
        ),
        action_taken="Roughly a third of the intended area shifted.",
        followed=_A.PARTIAL,
        fidelity=0.75,
        delay_days=6,
        change=0.01,
        conditions={},
        confidence=0.50,
        value_paise=1_35_62_607,
        expected_strength="UNCERTAIN",
        note="Partial shift, no measurable result.",
    ),
    # -- something else explains it equally well -> CONFOUNDED (still scored) -------------
    Scenario(
        key="paddy-buyer",
        rec_type=_C.BUYER_SELECTION,
        title="Move the Paddy lot to the procurement centre at MSP",
        reasoning=(
            "The procurement centre pays MSP with a 21-day settlement; the private mill "
            "pays sooner but below it on this grade."
        ),
        action_taken="Sold to the procurement centre.",
        followed=_A.YES,
        fidelity=0.93,
        delay_days=2,
        change=0.16,
        conditions={"price_moved_favourably": True},
        confidence=0.70,
        value_paise=2_04_00_000,
        expected_strength="CONFOUNDED",
        note="Went well AND the market rose on its own. We do not get to claim this one.",
    ),
    Scenario(
        key="late-irrigation",
        rec_type=_C.RISK_MITIGATION,
        title="Bring the second Wheat irrigation forward ahead of the dry spell",
        reasoning=(
            "The climatological record puts a dry window across the crown-root stage in "
            "roughly a third of years. Irrigating early hedges it."
        ),
        action_taken="Irrigation ran, but three weeks after the advisory.",
        followed=_A.YES,
        fidelity=0.90,
        delay_days=21,
        change=0.19,
        conditions={},
        confidence=0.63,
        value_paise=None,
        expected_strength="CONFOUNDED",
        note="Acted 21 days late: timing, not advice, is the plausible cause.",
    ),
    # -- refused a score entirely: not scoreable, so no Attribution row at all -------------
    Scenario(
        key="drip-partial",
        rec_type=_C.FUNDING_ALLOCATION,
        title="Fund drip irrigation on the Doab vegetable plots",
        reasoning=(
            "Water is the binding constraint on this tract. Drip on the vegetable plots "
            "releases the most area per rupee of working capital."
        ),
        action_taken="Installed on a handful of plots; the rest of the allocation went elsewhere.",
        followed=_A.PARTIAL,
        fidelity=0.42,
        delay_days=3,
        change=0.14,
        conditions={},
        confidence=0.55,
        value_paise=35_00_000,
        expected_strength=None,
        note="Below the fidelity floor. What was done and what was advised are different things.",
    ),
    Scenario(
        key="pmfby-enrolment",
        rec_type=_C.SCHEME_PURSUIT,
        title="Prepare Pradhan Mantri Fasal Bima Yojana applications for eligible members",
        reasoning=(
            "These members meet every criterion the system can check. The FPO assembles the "
            "paperwork; each farmer files their own application."
        ),
        action_taken="Not taken up — the enrolment window closed before the paperwork was ready.",
        followed=_A.NO,
        fidelity=None,
        delay_days=0,
        change=0.06,
        conditions={},
        confidence=0.55,
        value_paise=None,
        expected_strength=None,
        note="INV-7: the season still moved, but this advice had nothing to do with it.",
    ),
    Scenario(
        key="warehouse-receipt",
        rec_type=_C.FUNDING_ALLOCATION,
        title="Raise working capital against a warehouse receipt instead of a trade advance",
        reasoning=(
            "A receipt-backed loan prices below the trade advance the collective has been "
            "using, and does not commit the lot to one buyer."
        ),
        action_taken="Not taken up — the board preferred the existing trade relationship.",
        followed=_A.NO,
        fidelity=None,
        delay_days=0,
        change=-0.04,
        conditions={},
        confidence=0.60,
        value_paise=50_00_000,
        expected_strength=None,
        note="A rejected recommendation that still gets an intervention row saying so.",
    ),
    Scenario(
        key="residue-management",
        rec_type=_C.CROP_PROTECTION,
        title="Incorporate Paddy residue rather than burning it",
        reasoning=(
            "Residue incorporation keeps organic matter on the plot and avoids the burning "
            "penalty. It costs a pass with the implement."
        ),
        action_taken="No record of what was done on most plots.",
        followed=_A.UNKNOWN,
        fidelity=None,
        delay_days=0,
        change=0.07,
        conditions={},
        confidence=0.52,
        value_paise=None,
        expected_strength=None,
        note="UNKNOWN adherence. Attribution is refused outright (FR-1004).",
    ),
)

#: This season's open decisions — seeded SUGGESTED, with no intervention behind them.
#:
#: Demo beat 1 promises a briefing with items waiting on a human, and the dashboard's
#: "awaiting your approval" tile is the only number on that screen that represents work the
#: collective has already paid for and is not yet getting. Both read zero on a fresh seed
#: until something creates a recommendation, and nothing did: the seed built a collective
#: that had never made a decision, so the console's most important tile opened empty.
PENDING: tuple[tuple[str, enums.RecommendationType, str, float, int | None], ...] = (
    (
        "Sell the Kharif Paddy lot to the procurement centre rather than the mill",
        _C.BUYER_SELECTION,
        "The mill's headline price is higher. After freight, its 21-day settlement and its "
        "rejection history, the procurement centre nets more per kilogram.",
        0.71,
        2_18_00_000,
    ),
    (
        "Stagger this season's Paddy release across three months",
        _C.LOT_ALLOCATION,
        "November arrivals run far above the median month and the price follows. Releasing "
        "in tranches moves most of the volume past the floor.",
        0.68,
        1_92_00_000,
    ),
    (
        "Prepare Pradhan Mantri Fasal Bima Yojana applications before the window closes",
        _C.SCHEME_PURSUIT,
        "These members meet every criterion the system can check. The FPO assembles the "
        "paperwork; each farmer files their own application.",
        0.55,
        None,
    ),
    (
        "Bring the second irrigation forward on the Yamuna-Par blocks",
        _C.RISK_MITIGATION,
        "The climatological record puts a dry window across the crown-root stage in roughly "
        "a third of years. Irrigating early hedges it at the cost of one pass.",
        0.63,
        None,
    ),
    (
        "Release working capital against the warehouse receipt, not the trade advance",
        _C.FUNDING_ALLOCATION,
        "A receipt-backed facility prices below the trade advance in use, and does not "
        "commit the lot to one buyer before the price is known.",
        0.66,
        50_00_000,
    ),
)

#: Which scenarios belong to which historical question. Grouping them into four packets
#: rather than fifteen keeps the decision history readable, and matches how the assistant
#: actually behaves — one question yields several recommendations.
PACKETS: tuple[tuple[str, enums.Season, int, tuple[str, ...]], ...] = (
    (
        "What should we do this season to maximize sustainable farmer income?",
        enums.Season.KHARIF,
        2025,
        ("stagger-paddy", "ipm-first", "residue-management", "paddy-buyer"),
    ),
    (
        "Who should we sell the Kharif lots to?",
        enums.Season.KHARIF,
        2025,
        ("wheat-buyer", "moisture-check", "warehouse-receipt"),
    ),
    (
        "What should we plant this Rabi, and how should we fund it?",
        enums.Season.RABI,
        2025,
        ("mustard-share", "input-bulk", "drip-partial", "grade-before-sale", "storage-hold"),
    ),
    (
        "What is the risk to this harvest?",
        enums.Season.RABI,
        2025,
        ("late-irrigation", "sowing-window", "pmfby-enrolment"),
    ),
)


@dataclasses.dataclass(frozen=True)
class LearningLoopResult:
    packets: int
    recommendations: int
    pending: int
    interventions: int
    outcomes: int
    attributions: int
    predictions_scored: int
    #: strength -> count, as the ladder actually decided it.
    strengths: dict[str, int]
    adherence: dict[str, int]


def seed_learning_loop(
    session: Session, org: Organization, rng: random.Random
) -> LearningLoopResult:
    """Build two prior seasons of closed decision loops. Idempotent via ``seed_all``."""
    ceo, ceo_role = _approver(session, org)
    cycles = _closed_cycles(session)
    if not cycles:  # pragma: no cover - only if the crop-cycle seed changed shape
        return LearningLoopResult(0, 0, 0, 0, 0, 0, 0, {}, {})

    by_key = {s.key: s for s in SCENARIOS}
    strengths: dict[str, int] = {}
    adherence: dict[str, int] = {}
    packets = recommendations = interventions = outcomes = attributions = 0

    cycle_pool = list(cycles)
    rng.shuffle(cycle_pool)
    pool = iter(cycle_pool)

    for question, season, year, keys in PACKETS:
        scenarios = [by_key[k] for k in keys]
        # Harvest is done and the money is in before anyone judges the advice, so the
        # packet is dated at the start of its season and the outcomes land after it.
        asked_at = _season_start(season, year)
        snapshot = _snapshot(session, question=question, season=season, year=year, at=asked_at)

        built: list[tuple[Scenario, Recommendation, CropCycle]] = []
        for scenario in scenarios:
            cycle = next(pool, None) or rng.choice(cycles)
            recommendation = Recommendation(
                organization_id=org.id,
                snapshot_id=snapshot.id,
                type=scenario.rec_type,
                target_type="crop_cycle",
                target_id=cycle.id,
                title=scenario.title,
                reasoning=scenario.reasoning,
                evidence=_evidence(cycle, at=asked_at),
                confidence=scenario.confidence,
                expected_impact={"synthetic": True, "note": SYNTHETIC_NOTE},
                risks=[scenario.note],
                alternatives=[],
                recommended_value=scenario.value_paise,
                value_unit="paise" if scenario.value_paise else None,
                status=enums.RecommendationStatus.SUGGESTED,
                generator="seed",
                prompt_version=PROMPT_VERSION,
                model_id=MODEL_ID,
            )
            session.add(recommendation)
            built.append((scenario, recommendation, cycle))
        session.flush()

        packet = DecisionPacket(
            organization_id=org.id,
            snapshot_id=snapshot.id,
            asked_by=ceo.id,
            question=question,
            scope={
                "organization_id": str(org.id),
                "audience": "FPO",
                "season": season.value,
                "season_year": year,
            },
            body=_packet_body(
                org=org,
                question=question,
                season=season,
                year=year,
                snapshot_id=snapshot.id,
                at=asked_at,
                built=built,
            ),
            overall_confidence=round(sum(s.confidence for s, _r, _c in built) / len(built), 3),
            generated_at=asked_at,
            prompt_version=PROMPT_VERSION,
            model_id=MODEL_ID,
        )
        session.add(packet)
        session.flush()
        packets += 1

        for scenario, recommendation, cycle in built:
            recommendation.packet_id = packet.id
            _close_the_loop(
                session,
                org=org,
                ceo=ceo,
                ceo_role=ceo_role,
                scenario=scenario,
                recommendation=recommendation,
                cycle=cycle,
                asked_at=asked_at,
                counters=(strengths, adherence),
            )
            recommendations += 1
            interventions += 1
            outcomes += 1
            if scenario.expected_strength is not None:
                attributions += 1

    pending = _seed_open_decisions(session, org, ceo, cycles, rng)
    packets += 1
    recommendations += pending

    scored = _seed_predictions(session, cycles, rng)
    session.flush()

    return LearningLoopResult(
        packets=packets,
        recommendations=recommendations,
        pending=pending,
        interventions=interventions,
        outcomes=outcomes,
        attributions=attributions,
        predictions_scored=scored,
        strengths=strengths,
        adherence=adherence,
    )


# --------------------------------------------------------------------------- one loop


def _close_the_loop(
    session: Session,
    *,
    org: Organization,
    ceo: User,
    ceo_role: enums.Role,
    scenario: Scenario,
    recommendation: Recommendation,
    cycle: CropCycle,
    asked_at: dt.datetime,
    counters: tuple[dict[str, int], dict[str, int]],
) -> None:
    """Approval → execution → adherence → outcome → attribution, for one recommendation."""
    strengths, adherence = counters
    decided_at = asked_at + dt.timedelta(days=3)
    executed_at = decided_at + dt.timedelta(days=scenario.delay_days + 1)

    took_it = scenario.followed is not enums.Adherence.NO

    # INV-1: nothing reaches EXECUTED without a signed approval by an entitled role. A
    # recommendation the board declined gets a REJECTED approval row and stops there.
    session.add(
        Approval(
            recommendation_id=recommendation.id,
            approver_user_id=ceo.id,
            role_exercised=ceo_role,
            decision=(
                enums.ApprovalDecision.APPROVED if took_it else enums.ApprovalDecision.REJECTED
            ),
            approved_value=recommendation.recommended_value if took_it else None,
            rationale=scenario.note,
            decided_at=decided_at,
        )
    )
    recommendation.status = (
        enums.RecommendationStatus.EXECUTED if took_it else enums.RecommendationStatus.REJECTED
    )
    session.flush()

    # The intervention is written even when the advice was declined or ignored. That row is
    # the whole of INV-7: without it, the season's outcome would read as a verdict on advice
    # nobody took.
    intervention = Intervention(
        recommendation_id=recommendation.id,
        crop_cycle_id=cycle.id,
        action_taken=scenario.action_taken,
        executed_at=executed_at,
        executed_by=ceo.id,
        cost_paise=None,
    )
    session.add(intervention)
    # No flush here on purpose: adherence is part of the intervention's INSERT, not a later
    # UPDATE, because the row is append-only (DR-04). See record_adherence's docstring.
    attribution.record_adherence(
        session,
        intervention=intervention,
        followed=scenario.followed,
        fidelity=scenario.fidelity,
        delay_days=scenario.delay_days,
        deviation_notes=scenario.note,
    )
    adherence[scenario.followed.value] = adherence.get(scenario.followed.value, 0) + 1

    baseline = _baseline_kg(cycle)
    outcome = attribution.record_outcome(
        session,
        target_type="crop_cycle",
        target_id=cycle.id,
        metric="net_realisation_paise_per_kg",
        baseline_value=baseline,
        observed_value=round(baseline * (1 + scenario.change), 4),
        unit="paise_per_kg",
        intervention_id=intervention.id,
        period_start=asked_at.date(),
        period_end=(executed_at + dt.timedelta(days=120)).date(),
        external_conditions={**scenario.conditions, "note": SYNTHETIC_NOTE},
    )

    result = attribution.attribute(intervention=intervention, outcome=outcome)
    row = attribution.persist_attribution(
        session, outcome=outcome, intervention=intervention, result=result
    )

    if row is not None:
        strengths[row.strength.value] = strengths.get(row.strength.value, 0) + 1

    # The ladder is the authority; the scenario's expectation is a comment that has to stay
    # true. If these part company, the seed's honest distribution has silently changed.
    actual = row.strength.value if row is not None else None
    if actual != scenario.expected_strength:  # pragma: no cover - guards the seed's intent
        raise AssertionError(
            f"scenario {scenario.key!r} expected {scenario.expected_strength!r} from the "
            f"attribution ladder but got {actual!r}. Either the scenario's inputs or the "
            f"ladder's thresholds changed; reconcile them rather than editing this check."
        )


# --------------------------------------------------------------------------- open decisions


def _seed_open_decisions(
    session: Session,
    org: Organization,
    ceo: User,
    cycles: list[CropCycle],
    rng: random.Random,
) -> int:
    """This season's packet, left un-approved on purpose.

    No approval row, no intervention, no outcome — these are proposals and nothing else, and
    the console should say so. Their whole job is to make INV-1 visible on the first screen
    a CEO opens: five things the system has proposed and not one of them has happened.
    """
    asked_at = dt.datetime(2026, 8, 20, 6, 0, tzinfo=dt.UTC)
    question = "What should we do this season to maximize sustainable farmer income?"
    snapshot = _snapshot(
        session,
        question=question + " (open)",
        season=enums.Season.KHARIF,
        year=2026,
        at=asked_at,
    )

    built: list[tuple[Scenario, Recommendation, CropCycle]] = []
    for title, rec_type, reasoning, confidence, value in PENDING:
        cycle = rng.choice(cycles)
        recommendation = Recommendation(
            organization_id=org.id,
            snapshot_id=snapshot.id,
            type=rec_type,
            target_type="crop_cycle",
            target_id=cycle.id,
            title=title,
            reasoning=reasoning,
            evidence=_evidence(cycle, at=asked_at),
            confidence=confidence,
            expected_impact={"synthetic": True, "note": SYNTHETIC_NOTE},
            risks=[],
            alternatives=[],
            recommended_value=value,
            value_unit="paise" if value else None,
            status=enums.RecommendationStatus.SUGGESTED,
            generator="seed",
            prompt_version=PROMPT_VERSION,
            model_id=MODEL_ID,
        )
        session.add(recommendation)
        built.append(
            (
                Scenario(
                    key="open",
                    rec_type=rec_type,
                    title=title,
                    reasoning=reasoning,
                    action_taken="",
                    followed=enums.Adherence.UNKNOWN,
                    fidelity=None,
                    delay_days=0,
                    change=0.0,
                    conditions={},
                    confidence=confidence,
                    value_paise=value,
                    expected_strength=None,
                    note="Awaiting a decision.",
                ),
                recommendation,
                cycle,
            )
        )
    session.flush()

    packet = DecisionPacket(
        organization_id=org.id,
        snapshot_id=snapshot.id,
        asked_by=ceo.id,
        question=question,
        scope={
            "organization_id": str(org.id),
            "audience": "FPO",
            "season": enums.Season.KHARIF.value,
            "season_year": 2026,
        },
        body=_packet_body(
            org=org,
            question=question,
            season=enums.Season.KHARIF,
            year=2026,
            snapshot_id=snapshot.id,
            at=asked_at,
            built=built,
        ),
        overall_confidence=round(sum(c for _t, _r, _s, c, _v in PENDING) / len(PENDING), 3),
        generated_at=asked_at,
        prompt_version=PROMPT_VERSION,
        model_id=MODEL_ID,
    )
    session.add(packet)
    session.flush()
    for _scenario, recommendation, _cycle in built:
        recommendation.packet_id = packet.id
    session.flush()
    return len(built)


# --------------------------------------------------------------------------- predictions


def _seed_predictions(session: Session, cycles: list[CropCycle], rng: random.Random) -> int:
    """INV-6: yield forecasts scored against what actually happened.

    Kept apart from attribution on purpose. A forecast can be accurate while the advice built
    on it was wrong; collapsing the two makes both unanswerable. This is what fills the
    "forecast error" tile with a real mean absolute error rather than an em-dash.
    """
    scored = 0
    for cycle in cycles[:24]:
        # Synthetic: a flat 3.8 t/ha stand-in, in the same spirit as reference.CROPS, whose
        # yield figures are also placeholders pending seed/sources.md A1-A5.
        predicted = float(cycle.area_sqm) / 10_000 * 3_800
        if predicted <= 0:
            continue
        prediction = Prediction(
            module="quality_intelligence",
            module_version="1",
            subject_type="crop_cycle",
            subject_id=cycle.id,
            metric="yield_kg",
            value_numeric=round(predicted, 4),
            unit="kg",
            confidence=round(rng.uniform(0.55, 0.82), 3),
            issued_at=dt.datetime.combine(
                cycle.sowing_date or dt.date(2025, 6, 20), dt.time(6, 0), dt.UTC
            ),
            horizon_end=cycle.expected_harvest_date,
        )
        session.add(prediction)
        session.flush()
        # Realised yield lands within roughly ±18% of the forecast. Synthetic, like every
        # other yield number in this seed.
        actual = predicted * (1 + rng.uniform(-0.18, 0.18))
        attribution.score_prediction(
            session,
            prediction=prediction,
            actual=round(actual, 4),
            at=dt.datetime.combine(
                cycle.actual_harvest_date or dt.date(2026, 3, 1), dt.time(6, 0), dt.UTC
            ),
        )
        scored += 1
    return scored


# --------------------------------------------------------------------------- helpers


def _approver(session: Session, org: Organization) -> tuple[User, enums.Role]:
    grant = session.execute(
        select(RoleGrant).where(
            RoleGrant.organization_id == org.id, RoleGrant.role == enums.Role.FPO_CEO
        )
    ).scalar_one()
    user = session.get(User, grant.user_id)
    assert user is not None
    return user, grant.role


def _closed_cycles(session: Session) -> list[CropCycle]:
    """Closed cycles, ordered so the seed is reproducible run to run."""
    return list(
        session.execute(
            select(CropCycle)
            .where(CropCycle.status == enums.CropCycleStatus.CLOSED)
            .order_by(CropCycle.id)
            .limit(400)
        ).scalars()
    )


def _season_start(season: enums.Season, year: int) -> dt.datetime:
    month = 6 if season is enums.Season.KHARIF else 11
    return dt.datetime(year, month, 25, 6, 0, tzinfo=dt.UTC)


def _baseline_kg(cycle: CropCycle) -> float:
    """A per-kg baseline realisation. SYNTHETIC — stands in for last season's blended price."""
    return 1_850.0 + (cycle.id.int % 260)


def _evidence(cycle: CropCycle, *, at: dt.datetime) -> list[dict[str, Any]]:
    """FR-804: never empty. A claim with no evidence does not render, and must not persist."""
    return [
        {
            "kind": "domain_row",
            "id": str(cycle.id),
            "label": f"Crop cycle {cycle.season.value} {cycle.season_year}",
            "as_of": at.isoformat(),
        }
    ]


def _snapshot(
    session: Session,
    *,
    question: str,
    season: enums.Season,
    year: int,
    at: dt.datetime,
) -> EvidenceSnapshot:
    """INV-2: a frozen, hashed payload, so a seeded decision is as explainable as a live one."""
    payload: dict[str, Any] = {
        "note": SYNTHETIC_NOTE,
        "origin": "seed.learning",
        "question": question,
        "season": season.value,
        "season_year": year,
        "captured_at": at.isoformat(),
        "module_versions": {"quality_intelligence": "1", "market_intelligence": "1"},
        "prompt_version": PROMPT_VERSION,
        "model_id": MODEL_ID,
    }
    snapshot = EvidenceSnapshot(
        captured_at=at,
        payload=payload,
        content_hash=content_hash(payload),
        payload_version="1",
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def _packet_body(
    *,
    org: Organization,
    question: str,
    season: enums.Season,
    year: int,
    snapshot_id: uuid.UUID,
    at: dt.datetime,
    built: list[tuple[Scenario, Recommendation, CropCycle]],
) -> dict[str, Any]:
    """The rendered packet, in the live schema.

    Built through the same Pydantic models the orchestrator emits, so a seeded packet cannot
    drift out of shape: if the schema gains a required field, this stops compiling rather
    than producing a decision page that renders half-empty.
    """
    from agrivardhak.intelligence.contracts import EvidenceRef
    from agrivardhak.orchestrator.packet import (
        AssignedAction,
        Claim,
        ConfidenceBlock,
        DrilldownRefs,
        PacketProposedAction,
        PacketScope,
    )
    from agrivardhak.orchestrator.packet import (
        DecisionPacket as PacketSchema,
    )

    refs = [
        EvidenceRef(
            kind="domain_row",
            id=cycle.id,
            label=f"Crop cycle {cycle.season.value} {cycle.season_year}",
            as_of=at,
        )
        for _s, _r, cycle in built
    ]
    confidences = [s.confidence for s, _r, _c in built]
    overall = round(sum(confidences) / len(confidences), 3)

    packet = PacketSchema(
        question=question,
        scope=PacketScope(
            organization_id=org.id,
            audience="FPO",
            season=season.value,
            season_year=year,
        ),
        situation=[
            Claim(
                statement=(
                    f"{season.value.title()} {year} closed with {len(built)} decisions on the "
                    f"table for the collective."
                ),
                confidence=overall,
                evidence=refs[:2],
            )
        ],
        impact=[
            Claim(
                statement=(
                    "Each proposal below names the crop cycle it acts on, so its outcome can "
                    "be measured against a baseline rather than against a hope."
                ),
                confidence=overall,
                evidence=refs[:2],
            )
        ],
        recommendation=[
            PacketProposedAction(
                title=scenario.title,
                rationale=scenario.reasoning,
                recommendation_type=scenario.rec_type.value,
                target_type="crop_cycle",
                target_id=cycle.id,
                value_paise=scenario.value_paise,
                value_unit="paise" if scenario.value_paise else None,
                expected_impact={"synthetic": True, "note": SYNTHETIC_NOTE},
                risks=[scenario.note],
                confidence=scenario.confidence,
                evidence=[ref],
            )
            for (scenario, _rec, cycle), ref in zip(built, refs, strict=True)
        ],
        expected_outcome=[
            Claim(
                statement=(
                    f"{scenario.title}: net realisation per kg expected to change. Stated as a "
                    f"direction and a range, never a promised figure."
                ),
                confidence=scenario.confidence,
                evidence=[ref],
            )
            for (scenario, _rec, _cycle), ref in zip(built, refs, strict=True)
        ],
        confidence=ConfidenceBlock(
            overall=overall,
            per_section={"quality_intelligence": overall, "market_intelligence": overall},
            below_floor=overall < 0.45,
            what_would_raise_it=[
                "A field visit on the cycles with no recent observation.",
                "Verification of the plot areas that carry an open conflict.",
            ],
            degraded_inputs=[SYNTHETIC_NOTE],
        ),
        evidence=refs,
        actions=[
            AssignedAction(
                role=enums.Role.FIELD_OFFICER.value,
                task=f"Record the outcome of: {scenario.title}",
                due_on=(at + dt.timedelta(days=150)).date(),
                related_target_type="crop_cycle",
                related_target_id=cycle.id,
            )
            for scenario, _rec, cycle in built
        ],
        drilldown=DrilldownRefs(crop_cycle_ids=[c.id for _s, _r, c in built]),
        generated_at=at,
        snapshot_id=snapshot_id,
        prompt_version=PROMPT_VERSION,
        model_id=MODEL_ID,
    )
    return packet.model_dump(mode="json")
