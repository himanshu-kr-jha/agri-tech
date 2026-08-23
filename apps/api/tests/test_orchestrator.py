"""The orchestrator, the approval gate and the replay property — M13, M14, INV-1, INV-2.

These are the invariant tests. They are written to fail loudly if someone ever makes the
system convenient in the way that breaks it.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from agrivardhak.api.scope import ContextScope
from agrivardhak.domain import enums
from agrivardhak.domain.models.decisions import Approval, EvidenceSnapshot, Recommendation
from agrivardhak.domain.models.operations import AuditRecord, DomainEvent
from agrivardhak.domain.models.organization import Organization, RoleGrant
from agrivardhak.orchestrator import engine, lifecycle, reconcile

pytestmark = pytest.mark.usefixtures("db")

QUESTION = "What should we do this season to maximize sustainable farmer income?"


@pytest.fixture(scope="module")
def seeded() -> dict[str, uuid.UUID]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from agrivardhak.config import get_settings

    db = create_engine(get_settings().database_url)
    with Session(db) as session:
        org = session.execute(select(Organization)).scalars().first()
        grant = (
            session.execute(select(RoleGrant).where(RoleGrant.role == enums.Role.FPO_CEO))
            .scalars()
            .first()
        )
    db.dispose()
    if org is None or grant is None:
        pytest.skip("database not seeded — run `make seed`")
    return {"org_id": org.id, "ceo_user_id": grant.user_id}


@pytest.fixture(scope="module")
def ceo(seeded) -> ContextScope:
    return ContextScope(
        actor_user_id=seeded["ceo_user_id"],
        roles=frozenset({enums.Role.FPO_CEO}),
        organization_id=seeded["org_id"],
    )


@pytest.fixture(scope="module")
def _module_session(db, ceo):
    """One connection, one packet, rolled back once at the end.

    Generating a packet costs about six seconds — five modules over a thousand farmers and
    two years of prices — so the per-test fixture the rest of the suite uses would turn this
    file into a two-minute run. The packet is built once here and each test gets its own
    savepoint, which gives the same isolation for a twentieth of the wall clock.
    """
    connection = db.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    result = engine.ask(session, scope=ceo, question=QUESTION)
    session.flush()
    try:
        yield session, result
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def session(_module_session):
    """Per-test savepoint over the shared module session."""
    sess, _result = _module_session
    savepoint = sess.begin_nested()
    try:
        yield sess
    finally:
        if savepoint.is_active:
            savepoint.rollback()


@pytest.fixture
def packet(_module_session):
    _sess, result = _module_session
    return result


# --------------------------------------------------------------------------- the packet


def test_the_ceos_question_produces_a_packet_with_every_section(packet) -> None:
    body = packet.packet
    assert body.situation and body.impact and body.recommendation
    assert body.expected_outcome
    assert body.evidence
    assert body.actions, "FR-805: an action with no owner is not an action"
    assert body.confidence.overall > 0


def test_every_claim_carries_evidence(packet) -> None:
    """FR-804. The last barrier between a plausible sentence and a screen."""
    for section in (packet.packet.situation, packet.packet.impact, packet.packet.expected_outcome):
        for claim in section:
            assert claim.evidence, f"claim reached the packet with no evidence: {claim.statement}"


def test_every_action_has_a_named_owning_role(packet) -> None:
    roles = {enums.Role(a.role) for a in packet.packet.actions}
    assert roles, "actions must be assigned"
    assert all(isinstance(r, enums.Role) for r in roles)


def test_expected_outcomes_are_ranges_not_promises(packet) -> None:
    """SAF-05. A point forecast presented as fact is the failure mode this exists to stop."""
    for claim in packet.packet.expected_outcome:
        lowered = claim.statement.lower()
        assert "guarantee" not in lowered
        assert "will earn" not in lowered


def test_the_answer_says_what_it_does_not_know(packet) -> None:
    """NFR-301 / FR-813. Silence about a gap reads as an absence of gaps."""
    assert packet.packet.confidence.degraded_inputs


def test_synthetic_coefficients_are_labelled_wherever_they_reach_a_claim(packet) -> None:
    """C-2 / SAF-07. An unsourced coefficient must never present itself as measured."""
    economic = [
        c
        for c in (*packet.packet.situation, *packet.packet.impact)
        if "per rupee" in c.statement or "cost" in c.statement.lower()
    ]
    for claim in economic:
        assert "SYNTHETIC" in claim.statement or any(
            "SYNTHETIC" in d for d in packet.packet.confidence.degraded_inputs
        )


# --------------------------------------------------------------------------- reconciliation


def test_the_status_quo_can_be_overridden_not_only_a_proposal(packet) -> None:
    """The correction that made the reconciler useful.

    An earlier version could only override something a module had proposed, which assumed
    the risky plan is always the one the AI suggests. On this collective the opposite holds:
    99% of area is already in one crop that two independent modules find problems with, and
    nobody proposed it. Overriding the plan nobody argued for is the more valuable half.
    """
    keys = {o.overridden_key for o in packet.packet.overrides}
    assert any(k.startswith("current_cropping.") for k in keys), (
        "expected the dominant planted crop to be challenged by the converging evidence"
    )


def test_an_override_shows_the_evidence_that_beat_the_thing_it_overrode(packet) -> None:
    """FR-802. A silent override is a trust failure."""
    for override in packet.packet.overrides:
        assert override.prevailing_evidence
        assert override.reason.strip()


def test_a_near_certain_climate_event_is_not_ranked_as_a_risk(packet) -> None:
    """A hazard at probability 1.0 is the climate, and carries no decision information.

    Heat-stress days above 40 C occur in the late-April window in 100% of the last 30 years
    at this point. Ranked naively that beat a 1,868-tonne price exposure to the top of the
    packet, because probability was being read as severity.
    """
    from agrivardhak.intelligence.contracts import Finding

    ref = packet.packet.evidence[0]
    climate = Finding(
        key="climate_normal.heat_stress.guava",
        statement="a heat-stress day fell in the harvest window in 100% of the last 30 years",
        confidence=0.8,
        evidence=[ref],
    )
    hazard = Finding(
        key="weather_hazard.heavy_rain.potato",
        statement="in 17% of the last 30 years a heavy-rain day fell in the harvest window",
        confidence=0.8,
        evidence=[ref],
    )
    now = dt.datetime.now(dt.UTC)
    assert reconcile.urgency_of(climate, now) < reconcile.urgency_of(hazard, now)


def test_impact_ordering_does_not_saturate_between_a_small_and_a_large_exposure() -> None:
    """A linear scale with a ceiling put a 9-acre finding above a 1,868-tonne one."""
    small = reconcile._log_scale(3_700_000, floor=10_000, ceiling=10_000_000_00)
    large = reconcile._log_scale(633_000_000, floor=10_000, ceiling=10_000_000_00)
    assert large > small + 0.15, "orders of magnitude must still separate after scaling"


# --------------------------------------------------------------------------- INV-1


def test_a_generated_recommendation_starts_at_suggested(session, packet) -> None:
    for rec_id in packet.recommendation_ids:
        row = session.get(Recommendation, rec_id)
        assert row.status is enums.RecommendationStatus.SUGGESTED


def test_an_unapproved_recommendation_cannot_execute(session, packet) -> None:
    """INV-1, the invariant this whole system exists to keep.

    Not "should not" — cannot. There is no argument to :func:`execute` that bypasses the
    approval lookup, because the approval is read back from the database.
    """
    row = session.get(Recommendation, packet.recommendation_ids[0])
    with pytest.raises(lifecycle.LifecycleViolation):
        lifecycle.execute(
            session,
            recommendation=row,
            executed_by=uuid.uuid4(),
            action_taken="tried to skip the gate",
        )
    assert row.status is enums.RecommendationStatus.SUGGESTED


def test_a_role_without_authority_cannot_approve(session, packet, seeded) -> None:
    row = session.get(Recommendation, packet.recommendation_ids[0])
    with pytest.raises(lifecycle.LifecycleViolation):
        lifecycle.decide(
            session,
            recommendation=row,
            approver_user_id=seeded["ceo_user_id"],
            roles=frozenset({enums.Role.RESEARCHER}),
            decision=enums.ApprovalDecision.APPROVED,
        )


def test_a_platform_admin_may_not_approve_a_collectives_decision(session, packet, seeded) -> None:
    """Operating the software is not the same authority as running the collective."""
    row = session.get(Recommendation, packet.recommendation_ids[0])
    with pytest.raises(lifecycle.LifecycleViolation):
        lifecycle.decide(
            session,
            recommendation=row,
            approver_user_id=seeded["ceo_user_id"],
            roles=frozenset({enums.Role.PLATFORM_ADMIN}),
            decision=enums.ApprovalDecision.APPROVED,
        )


def test_a_rejection_without_a_reason_is_refused(session, packet, seeded) -> None:
    """FR-706. An unexplained no is the most valuable signal thrown away."""
    row = session.get(Recommendation, packet.recommendation_ids[0])
    with pytest.raises(lifecycle.LifecycleViolation):
        lifecycle.decide(
            session,
            recommendation=row,
            approver_user_id=seeded["ceo_user_id"],
            roles=frozenset({enums.Role.FPO_CEO}),
            decision=enums.ApprovalDecision.REJECTED,
            rationale=None,
        )


def test_the_whole_loop_runs_and_records_who_authorised_what(session, packet, seeded) -> None:
    """ask -> approve with modification -> execute, with the trail INV-1 promises."""
    row = session.get(Recommendation, packet.recommendation_ids[0])
    original = row.recommended_value

    result = lifecycle.decide(
        session,
        recommendation=row,
        approver_user_id=seeded["ceo_user_id"],
        roles=frozenset({enums.Role.FPO_CEO}),
        decision=enums.ApprovalDecision.APPROVED_WITH_MODIFICATION,
        approved_value_paise=3_200_000,
        rationale="Board agreed a smaller first tranche.",
    )
    assert result.was_modified
    assert result.approved_value_paise == 3_200_000
    assert result.approved_value_paise != original or original is None

    intervention = lifecycle.execute(
        session,
        recommendation=row,
        executed_by=seeded["ceo_user_id"],
        action_taken="First tranche released.",
    )
    assert row.status is enums.RecommendationStatus.EXECUTED
    assert intervention.recommendation_id == row.id

    approval = (
        session.execute(select(Approval).where(Approval.recommendation_id == row.id))
        .scalars()
        .one()
    )
    assert approval.role_exercised is enums.Role.FPO_CEO

    events = {
        e.event_type
        for e in session.execute(
            select(DomainEvent).where(DomainEvent.aggregate_id == row.id)
        ).scalars()
    }
    assert {"RecommendationApproved", "RecommendationExecuted"} <= events

    audits = list(
        session.execute(select(AuditRecord).where(AuditRecord.subject_id == row.id)).scalars()
    )
    assert any(a.authority == enums.Role.FPO_CEO.value for a in audits)


def test_a_modified_approval_records_the_modified_value_not_the_proposed_one(
    session, packet, seeded
) -> None:
    """Recording a modification as a plain approval teaches the system its number was right."""
    row = session.get(Recommendation, packet.recommendation_ids[1])
    lifecycle.decide(
        session,
        recommendation=row,
        approver_user_id=seeded["ceo_user_id"],
        roles=frozenset({enums.Role.FPO_CEO}),
        decision=enums.ApprovalDecision.APPROVED_WITH_MODIFICATION,
        approved_value_paise=111,
        rationale="Trimmed.",
    )
    approval = (
        session.execute(select(Approval).where(Approval.recommendation_id == row.id))
        .scalars()
        .one()
    )
    assert approval.approved_value == 111


def test_modification_without_a_value_is_refused(session, packet, seeded) -> None:
    row = session.get(Recommendation, packet.recommendation_ids[2])
    with pytest.raises(lifecycle.LifecycleViolation):
        lifecycle.decide(
            session,
            recommendation=row,
            approver_user_id=seeded["ceo_user_id"],
            roles=frozenset({enums.Role.FPO_CEO}),
            decision=enums.ApprovalDecision.APPROVED_WITH_MODIFICATION,
            approved_value_paise=None,
        )


def test_a_rejected_recommendation_cannot_be_resurrected(session, packet, seeded) -> None:
    row = session.get(Recommendation, packet.recommendation_ids[3])
    lifecycle.decide(
        session,
        recommendation=row,
        approver_user_id=seeded["ceo_user_id"],
        roles=frozenset({enums.Role.FPO_CEO}),
        decision=enums.ApprovalDecision.REJECTED,
        rationale="Not this season.",
    )
    with pytest.raises(lifecycle.LifecycleViolation):
        lifecycle.decide(
            session,
            recommendation=row,
            approver_user_id=seeded["ceo_user_id"],
            roles=frozenset({enums.Role.FPO_CEO}),
            decision=enums.ApprovalDecision.APPROVED,
        )


def test_re_asking_supersedes_the_previous_unapproved_suggestion(session, ceo) -> None:
    """INV-10. Asking twice must not leave two identical decisions waiting.

    Five askings used to leave five identical SUGGESTED rows and a briefing that showed the
    same decision five times — the fastest way to teach a CEO to stop reading the briefing.
    """
    first = engine.ask(session, scope=ceo, question="Who should we sell the paddy to?")
    session.flush()
    second = engine.ask(session, scope=ceo, question="Who should we sell the paddy to?")
    session.flush()

    old = session.get(Recommendation, first.recommendation_ids[0])
    new = session.get(Recommendation, second.recommendation_ids[0])
    assert old.status is enums.RecommendationStatus.SUPERSEDED
    assert new.status is enums.RecommendationStatus.SUGGESTED
    assert old.id != new.id


def test_an_approved_recommendation_is_never_superseded_by_a_re_ask(session, ceo, seeded) -> None:
    """History is not rewritten. A decision that was made stays made."""
    first = engine.ask(session, scope=ceo, question="Who should we sell the paddy to?")
    row = session.get(Recommendation, first.recommendation_ids[0])
    lifecycle.decide(
        session,
        recommendation=row,
        approver_user_id=seeded["ceo_user_id"],
        roles=frozenset({enums.Role.FPO_CEO}),
        decision=enums.ApprovalDecision.APPROVED,
        rationale="Agreed.",
    )
    session.flush()
    engine.ask(session, scope=ceo, question="Who should we sell the paddy to?")
    session.flush()
    assert row.status is enums.RecommendationStatus.APPROVED


# --------------------------------------------------------------------------- INV-2


def test_the_evidence_snapshot_is_hashed_over_its_content(session, packet) -> None:
    snapshot = session.get(EvidenceSnapshot, packet.snapshot_id)
    assert snapshot.content_hash == engine.content_hash(snapshot.payload)
    assert len(snapshot.content_hash) == 64


def test_the_snapshot_records_the_coefficients_in_force(session, packet) -> None:
    """A historical answer is only reproducible if the constants behind it were kept."""
    payload = session.get(EvidenceSnapshot, packet.snapshot_id).payload
    assert payload["coefficients"]["quality_yield_model"]
    assert payload["module_versions"]


def test_replaying_a_snapshot_reproduces_the_same_answer(session, packet) -> None:
    """INV-2 / ARCHITECTURE §9. If this fails, a module stopped being pure."""
    replayed = engine.replay(session, packet.snapshot_id)
    original = packet.packet
    assert len(replayed["situation"]) == len(original.situation)
    assert [c["statement"] for c in replayed["situation"]] == [
        c.statement for c in original.situation
    ]
    assert [o["overridden_key"] for o in replayed["overrides"]] == [
        o.overridden_key for o in original.overrides
    ]


def test_replay_reads_no_live_data(session, packet) -> None:
    """The property that makes replay meaningful: it must work from the bytes alone.

    Asserted by replaying a snapshot whose organization rows are irrelevant to the call —
    if replay reached for live data, the module outputs would have to be re-gathered, and
    the function does not have an organization id to gather with.
    """
    replayed = engine.replay(session, packet.snapshot_id)
    assert replayed["content_hash"]
    assert replayed["confidence"]["overall"] == packet.packet.confidence.overall


def test_identical_inputs_reuse_the_snapshot_rather_than_forking_it(session, ceo) -> None:
    """Two packets built from the same frozen evidence should point at the same evidence."""
    at = dt.datetime(2026, 8, 22, 6, 0, tzinfo=dt.UTC)
    first = engine.ask(session, scope=ceo, question=QUESTION, as_of=at)
    second = engine.ask(session, scope=ceo, question=QUESTION, as_of=at)
    assert first.content_hash == second.content_hash
    assert first.snapshot_id == second.snapshot_id
    assert first.packet_row_id != second.packet_row_id, "but each asking is its own packet"


# --------------------------------------------------------------------------- planning


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Who should we sell the potato to?", "market"),
        ("What disease is on my wheat?", "crop_health"),
        ("Which subsidy can our members claim?", "scheme"),
        ("What is the risk to the harvest?", "risk"),
    ],
)
def test_planning_selects_the_modules_a_question_needs(question, expected) -> None:
    assert expected in engine.plan_for(question)


def test_an_unrecognised_question_runs_everything_rather_than_guessing(seeded) -> None:
    """Skipping a module that was needed is a wrong answer; running a spare one costs 200 ms."""
    assert set(engine.plan_for("hello")) == set(engine.MODULES)


def test_asking_for_risk_also_runs_quality(seeded) -> None:
    """Risk sized against planted area instead of expected tonnage is silently worse."""
    assert "quality" in engine.plan_for("What is the risk this season?")
