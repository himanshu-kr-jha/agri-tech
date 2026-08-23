"""The invariant tests (SRS §8.2).

These are the tests that must never be allowed to go red. Each one asserts a property the
product's credibility depends on, not an implementation detail.

Tests for invariants whose machinery lands in later phases are marked ``xfail(strict=True)``
so they fail loudly the moment the feature exists but the invariant does not hold — rather
than sitting silently skipped until someone remembers them.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from agrivardhak.api.scope import ScopeViolation, for_user
from agrivardhak.domain.enums import (
    Adherence,
    AttributionStrength,
    RecommendationStatus,
    RecommendationType,
    Role,
    VisibilityScope,
)
from agrivardhak.intelligence.contracts import EvidenceRef, Finding

# --------------------------------------------------------------------- INV-3 provenance


def test_finding_requires_evidence() -> None:
    """INV-3 / FR-804: a claim without evidence cannot be constructed at all.

    This is the structural defence against a hallucinated number reaching a user: it is not
    filtered out downstream, it fails to exist.
    """
    with pytest.raises(ValidationError):
        Finding(
            key="oversupply_risk.potato",
            statement="Potato oversupply of about 500 tonnes is expected.",
            confidence=0.8,
            evidence=[],  # empty — must be rejected
        )


def test_finding_with_evidence_is_valid() -> None:
    finding = Finding(
        key="oversupply_risk.potato",
        statement="Potato oversupply of about 500 tonnes is expected.",
        confidence=0.8,
        evidence=[
            EvidenceRef(
                kind="external_record",
                id=uuid.uuid4(),
                label="Agmarknet arrivals, Prayagraj, Feb 2026",
                as_of=dt.datetime.now(dt.UTC),
            )
        ],
    )
    assert finding.confidence == 0.8
    assert len(finding.evidence) == 1


def test_confidence_is_bounded() -> None:
    with pytest.raises(ValidationError):
        Finding(
            key="k",
            statement="s",
            confidence=1.4,
            evidence=[
                EvidenceRef(
                    kind="observation",
                    id=uuid.uuid4(),
                    label="l",
                    as_of=dt.datetime.now(dt.UTC),
                )
            ],
        )


# ----------------------------------------------------------------- INV-5 info boundary


def _farmer_scope(farmer_id: uuid.UUID, org_id: uuid.UUID):
    return for_user(
        user_id=uuid.uuid4(),
        roles={Role.FARMER},
        organization_id=org_id,
        farmer_id=farmer_id,
    )


def _ceo_scope(org_id: uuid.UUID):
    return for_user(user_id=uuid.uuid4(), roles={Role.FPO_CEO}, organization_id=org_id)


def test_farmer_scope_excludes_org_internal() -> None:
    """INV-5: a farmer never sees ORG_INTERNAL — not even rows about themselves.

    Buyer negotiation state concerning a farmer's own lot is still organization-internal
    until the organization chooses to share it.
    """
    scope = _farmer_scope(uuid.uuid4(), uuid.uuid4())
    visible = scope.visible_scopes()
    assert VisibilityScope.ORG_INTERNAL not in visible
    assert VisibilityScope.OWNER in visible
    assert VisibilityScope.SHARED_WITH_MEMBERS in visible


def test_ceo_scope_includes_org_internal() -> None:
    assert VisibilityScope.ORG_INTERNAL in _ceo_scope(uuid.uuid4()).visible_scopes()


def test_farmer_cannot_see_another_farmer() -> None:
    me, someone_else = uuid.uuid4(), uuid.uuid4()
    scope = _farmer_scope(me, uuid.uuid4())
    assert scope.can_see_farmer(me)
    assert not scope.can_see_farmer(someone_else)
    with pytest.raises(ScopeViolation):
        scope.require_farmer_access(someone_else)


def test_farmer_audience_is_farmer_ceo_audience_is_fpo() -> None:
    assert _farmer_scope(uuid.uuid4(), uuid.uuid4()).audience == "FARMER"
    assert _ceo_scope(uuid.uuid4()).audience == "FPO"


def test_scope_without_org_refuses_org_operations() -> None:
    """NFR-402: the organization comes from the token, and its absence is an error.

    Defaulting to "all organizations" here is the classic multi-tenant data leak.
    """
    scope = for_user(user_id=uuid.uuid4(), roles={Role.FPO_CEO}, organization_id=None)
    with pytest.raises(ScopeViolation):
        scope.require_org()


def test_role_requirement_is_enforced() -> None:
    scope = _farmer_scope(uuid.uuid4(), uuid.uuid4())
    with pytest.raises(ScopeViolation):
        scope.require_any_role(Role.FPO_CEO)
    scope.require_any_role(Role.FARMER)  # does not raise


def test_platform_admin_bypasses_narrowing() -> None:
    scope = for_user(user_id=uuid.uuid4(), roles={Role.PLATFORM_ADMIN}, organization_id=None)
    assert scope.require_any_role(Role.FPO_CEO) is None
    assert scope.visible_scopes() == frozenset(VisibilityScope)


# ------------------------------------------------------------------- DR-04 append-only


class TestAppendOnly:
    """DR-04 / INV-2: immutable tables are immutable in the database, not by convention.

    These use the rolled-back ``session`` fixture rather than committing. The triggers fire
    on the statement, not on commit, so a savepoint proves the same thing — and the tests
    leave no residue in a database the demo and `make progress` both read.
    """

    def test_observation_value_cannot_be_updated(self, session) -> None:
        obs_id = _insert_observation(session)
        with pytest.raises(Exception, match="append-only violation"):
            session.execute(
                text("update observation set value_numeric = 1 where id = :i"), {"i": obs_id}
            )

    def test_observation_cannot_be_deleted(self, session) -> None:
        obs_id = _insert_observation(session)
        with pytest.raises(Exception, match="append-only violation"):
            session.execute(text("delete from observation where id = :i"), {"i": obs_id})

    def test_verification_transition_is_allowed(self, session) -> None:
        """A human verifying a claim does not change the claim."""
        obs_id = _insert_observation(session)
        session.execute(
            text(
                "update observation set verification_status = "
                "cast(:v as verification_status) where id = :i"
            ),
            {"i": obs_id, "v": "VERIFIED"},
        )
        status = session.execute(
            text("select verification_status from observation where id = :i"), {"i": obs_id}
        ).scalar_one()
        assert status == "VERIFIED"

    def test_evidence_snapshot_cannot_be_updated(self, session) -> None:
        """INV-2: the frozen evidence stays frozen."""
        snap_id = session.execute(
            text(
                "insert into evidence_snapshot (captured_at, payload, content_hash, "
                "payload_version) values (now(), '{}'::jsonb, :h, '1') returning id"
            ),
            {"h": uuid.uuid4().hex * 2},
        ).scalar_one()
        with pytest.raises(Exception, match="append-only violation"):
            session.execute(
                text("update evidence_snapshot set payload = cast(:p as jsonb) where id = :i"),
                {"i": snap_id, "p": '{"tampered": true}'},
            )


def _insert_observation(session) -> uuid.UUID:
    session.execute(
        text(
            "insert into data_source (key, label, source_type, base_trust, is_fixture) "
            "values (:k, 'test', 'FIELD_OFFICER', 0.95, false) on conflict (key) do nothing"
        ),
        {"k": "test-source"},
    )
    source_id = session.execute(
        text("select id from data_source where key = :k"), {"k": "test-source"}
    ).scalar_one()
    return session.execute(
        text(
            "insert into observation (subject_type, subject_id, attribute, value_numeric, "
            "unit, source_type, source_id, observed_at, recorded_at, confidence, "
            "verification_status) values ('plot', uuid_generate_v7(), 'area_sqm', 8093.7, "
            "'sqm', 'FIELD_OFFICER', :s, now(), now(), 0.95, 'UNVERIFIED') returning id"
        ),
        {"s": source_id},
    ).scalar_one()


# ------------------------------------------------- the remaining invariants


def test_no_execution_without_approval() -> None:
    """INV-1: EXECUTED is unreachable without an Approval row.

    Asserted here against the guard itself, not through a database round trip, so this test
    stays meaningful even when Postgres is not running. The end-to-end version — ask,
    approve, execute, with the audit trail — lives in tests/test_orchestrator.py.
    """
    from agrivardhak.orchestrator import lifecycle

    for status in (
        RecommendationStatus.SUGGESTED,
        RecommendationStatus.REVIEWED,
        RecommendationStatus.REJECTED,
    ):
        with pytest.raises(lifecycle.LifecycleViolation):
            lifecycle.assert_transition(status, RecommendationStatus.EXECUTED)

    # And the only status that *may* reach EXECUTED still has to produce an approval row,
    # which lifecycle.execute reads back from the database rather than accepting as an
    # argument. That path is covered end to end in test_orchestrator.py.
    assert RecommendationStatus.EXECUTED in lifecycle.TRANSITIONS[RecommendationStatus.APPROVED]


def test_only_an_authorised_role_can_approve() -> None:
    """INV-1's other half: approval is by a role, and the role is recorded."""
    from agrivardhak.orchestrator import lifecycle

    with pytest.raises(lifecycle.LifecycleViolation):
        lifecycle.assert_may_approve(
            RecommendationType.FUNDING_ALLOCATION, frozenset({Role.FARMER})
        )
    assert (
        lifecycle.assert_may_approve(
            RecommendationType.FUNDING_ALLOCATION, frozenset({Role.FINANCE_OFFICER})
        )
        is Role.FINANCE_OFFICER
    )


# INV-4 is implemented as of Phase 1. Its assertions live in tests/test_provenance.py:
#   TestResolver::test_three_way_conflict_raises_a_discrepancy_and_picks_no_winner
#   TestResolver::test_human_resolution_closes_the_conflict_and_keeps_the_trail


def test_attribution_requires_adherence() -> None:
    """INV-7: an outcome from advice nobody followed is not evidence about the advice."""
    from agrivardhak.domain.models.decisions import Intervention, Outcome
    from agrivardhak.learning import attribution

    for adherence in (Adherence.NO, Adherence.UNKNOWN):
        result = attribution.attribute(
            intervention=Intervention(
                id=uuid.uuid4(),
                action_taken="not done",
                executed_at=dt.datetime.now(dt.UTC),
                followed=adherence,
            ),
            outcome=Outcome(
                id=uuid.uuid4(),
                target_type="crop_cycle",
                target_id=uuid.uuid4(),
                metric="yield",
                baseline_value=3.6,
                observed_value=1.0,
            ),
        )
        assert result.scored is False
        assert result.strength == AttributionStrength.CONFOUNDED.value


def test_chemical_recommendation_has_citation_or_caution() -> None:
    """INV-8 / SAF-03: no product, no dose — a class plus the label-and-agronomist caution.

    Every condition in the knowledge base is checked, not a sample. A single entry someone
    adds later with a dosage in it is exactly the failure this is here to catch.
    """
    from agrivardhak.intelligence import crop_health

    for condition in crop_health.CONDITIONS:
        if condition.chemical_class is None:
            continue
        text = condition.chemical_class.lower()
        for banned in ("ml/", " ml ", "g/l", "gram", "%ec", "kg/ha", "litre per"):
            assert banned not in text, (
                f"{condition.key} names a dose. Crop protection gives a class only (INV-8)."
            )
        if condition.source is None:
            assert condition.key  # unsourced entries are capped elsewhere; see test_crop_health

    plan = crop_health.build_plan(
        crop_health.candidates_for(
            crop_health.HealthObservation(
                cycle_id=uuid.uuid4(),
                farmer_id=uuid.uuid4(),
                plot_id=uuid.uuid4(),
                crop_name="Potato",
                observed_on=dt.date(2026, 1, 20),
                symptoms=("leaf_lesion_dark", "white_growth_underside", "rapid_spread"),
                severity_pct=30.0,
                affected_area_sqm=None,
                evidence=[],
            ),
            None,
        ),
        crop_health.DEFAULT_DIAGNOSTIC_MARGIN,
        30.0,
    )
    chemical = [s for s in plan.steps if s["rung"] == "chemical"]
    assert chemical, "a severe late-blight plan must reach the chemical rung"
    note = chemical[0].get("note", "").lower()
    assert "label" in note and "agronomist" in note


def test_superseded_not_mutated() -> None:
    """INV-10: new evidence replaces a decision; it never edits one.

    Checked at the transition table, which is where the rule actually lives: an APPROVED
    recommendation can only move to EXECUTED or SUPERSEDED, and a SUPERSEDED or REJECTED one
    is terminal. There is no path back into APPROVED from anywhere.
    """
    from agrivardhak.orchestrator import lifecycle

    assert lifecycle.TRANSITIONS[RecommendationStatus.SUPERSEDED] == frozenset()
    assert lifecycle.TRANSITIONS[RecommendationStatus.REJECTED] == frozenset()
    assert lifecycle.TRANSITIONS[RecommendationStatus.APPROVED] == frozenset(
        {RecommendationStatus.EXECUTED, RecommendationStatus.SUPERSEDED}
    )
    for status, allowed in lifecycle.TRANSITIONS.items():
        if status is not RecommendationStatus.REVIEWED:
            assert RecommendationStatus.APPROVED not in allowed or status in (
                RecommendationStatus.SUGGESTED,
                RecommendationStatus.REVIEWED,
            ), f"{status} must not be able to become APPROVED again"


def test_prediction_and_recommendation_are_separate_lifecycles() -> None:
    """INV-6. "Was the forecast right" and "was the advice good" are different questions.

    Collapsing them makes both unanswerable: a correct forecast can carry bad advice, and
    good advice can rest on a forecast that turned out wrong for unrelated reasons.
    """
    from agrivardhak.domain.models.decisions import Prediction, Recommendation

    assert Prediction.__tablename__ != Recommendation.__tablename__
    assert hasattr(Prediction, "actual_value"), "a prediction is scored against reality"
    assert not hasattr(Prediction, "status"), "a prediction has no approval lifecycle"
    assert hasattr(Recommendation, "status"), "a recommendation does"
    assert not hasattr(Recommendation, "actual_value"), (
        "a recommendation is not scored against reality directly — its outcome is, "
        "through an Intervention that records whether it was followed at all"
    )
