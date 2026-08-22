"""Provenance layer tests — INV-3 and INV-4.

The headline case is the one from the discovery session and the demo script: farmer says
2.0 acres, the government record says 1.6, the field officer says 1.8. The system must show
all three and pick none.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest

from agrivardhak.domain.enums import DiscrepancyStatus, SourceType, VerificationStatus
from agrivardhak.provenance import trust

UTC = dt.UTC
NOW = dt.datetime(2026, 8, 22, 6, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- trust weights


def test_field_officer_outranks_self_report_at_equal_age() -> None:
    common = dict(
        verification_status=VerificationStatus.UNVERIFIED,
        observed_at=NOW - dt.timedelta(days=1),
        as_of=NOW,
        attribute="crop_health_pct",
    )
    officer = trust.effective_confidence(source_type=SourceType.FIELD_OFFICER, **common)
    farmer = trust.effective_confidence(source_type=SourceType.FARMER_SELF_REPORT, **common)
    assert officer > farmer


def test_ai_inference_confidence_is_capped() -> None:
    """A model that is certain is still a model (INV-3)."""
    value = trust.base_trust_for(SourceType.AI_INFERENCE, reported=0.99)
    assert value == trust.AI_INFERENCE_CEILING


def test_ai_inference_honours_low_self_reported_confidence() -> None:
    assert trust.base_trust_for(SourceType.AI_INFERENCE, reported=0.40) == 0.40


def test_verification_raises_confidence() -> None:
    common = dict(
        source_type=SourceType.FIELD_OFFICER,
        observed_at=NOW - dt.timedelta(days=2),
        as_of=NOW,
        attribute="crop_health_pct",
    )
    verified = trust.effective_confidence(verification_status=VerificationStatus.VERIFIED, **common)
    unverified = trust.effective_confidence(
        verification_status=VerificationStatus.UNVERIFIED, **common
    )
    disputed = trust.effective_confidence(verification_status=VerificationStatus.DISPUTED, **common)
    assert verified > unverified > disputed


# --------------------------------------------------------------------------- decay


def test_confidence_halves_over_one_half_life() -> None:
    """Crop health is on a 14-day half-life.

    Raised from 7 after it drove aggregate forecasts to near-zero confidence: 7 days
    conflated how fast a *crop* changes with how fast our *information about it* decays. A
    week-old field-officer reading is still worth a great deal.
    """
    policy = trust.policy_for("crop_health_pct")
    assert policy.half_life_days == 14
    assert trust.decay_factor(NOW, NOW, policy) == pytest.approx(1.0)
    assert trust.decay_factor(NOW - dt.timedelta(days=14), NOW, policy) == pytest.approx(0.5)
    assert trust.decay_factor(NOW - dt.timedelta(days=28), NOW, policy) == pytest.approx(0.25)


def test_slow_attributes_barely_decay_over_a_season() -> None:
    """Plot area does not change because time passed; crop health does."""
    area = trust.decay_factor(NOW - dt.timedelta(days=90), NOW, trust.policy_for("area_sqm"))
    health = trust.decay_factor(
        NOW - dt.timedelta(days=90), NOW, trust.policy_for("crop_health_pct")
    )
    assert area > 0.8, "a plot does not change size because a season passed"
    assert health < 0.05, "a three-month-old health reading tells you almost nothing"
    assert area > health * 15


def test_future_observation_does_not_exceed_full_confidence() -> None:
    """Clock skew must not manufacture confidence above 1.0."""
    policy = trust.policy_for("crop_health_pct")
    assert trust.decay_factor(NOW + dt.timedelta(days=30), NOW, policy) == pytest.approx(1.0)


def test_staleness_uses_its_own_threshold() -> None:
    """Staleness is a separate threshold from decay — a value can be weak but not yet stale."""
    policy = trust.policy_for("crop_health_pct")
    assert policy.stale_after_days == 30
    assert not trust.is_stale(NOW - dt.timedelta(days=29), NOW, policy)
    assert trust.is_stale(NOW - dt.timedelta(days=31), NOW, policy)


def test_unmodelled_attribute_decays_conservatively() -> None:
    """An attribute nobody wrote a policy for must not coast on high confidence."""
    policy = trust.policy_for("some_attribute_nobody_configured")
    assert policy is trust.FALLBACK_POLICY
    assert trust.decay_factor(NOW - dt.timedelta(days=180), NOW, policy) < 0.02


# --------------------------------------------------------------------------- conflict maths


def test_spread_is_symmetric() -> None:
    """2.0 vs 1.6 reads the same whichever claim is listed first."""
    assert trust.spread_pct([2.0, 1.6]) == pytest.approx(trust.spread_pct([1.6, 2.0]))


def test_the_demo_plot_area_conflict_exceeds_tolerance() -> None:
    """Farmer 2.0 ac / record 1.6 / officer 1.8 — the demo's beat 5."""
    claims = [8093.7, 6474.9, 7284.3]  # acres converted to sqm
    assert trust.exceeds_tolerance(claims, "area_sqm")
    assert trust.spread_pct(claims) == pytest.approx(22.2, abs=0.5)


def test_agreeing_sources_do_not_conflict() -> None:
    assert not trust.exceeds_tolerance([7284.3, 7290.0], "area_sqm")


def test_single_claim_has_no_spread() -> None:
    assert trust.spread_pct([7284.3]) == 0.0
    assert not trust.exceeds_tolerance([7284.3], "area_sqm")


def test_conflict_penalty_is_capped() -> None:
    """A conflict degrades a value without erasing what we know of its magnitude."""
    assert trust.conflict_penalty(500) == trust.MAX_CONFLICT_PENALTY
    assert trust.conflict_penalty(None) == 0.0
    assert trust.conflict_penalty(10) == pytest.approx(0.10)


def test_conflict_lowers_effective_confidence() -> None:
    common = dict(
        source_type=SourceType.FIELD_OFFICER,
        verification_status=VerificationStatus.UNVERIFIED,
        observed_at=NOW - dt.timedelta(days=1),
        as_of=NOW,
        attribute="area_sqm",
    )
    clean = trust.effective_confidence(**common)
    conflicted = trust.effective_confidence(conflict_spread_pct=22.2, **common)
    assert conflicted < clean


# --------------------------------------------------------------------------- resolver (DB)


@pytest.mark.usefixtures("db")
class TestResolver:
    def test_records_and_resolves_a_single_observation(self, session) -> None:
        from agrivardhak.provenance import resolver

        plot_id = uuid.uuid4()
        resolver.record_observation(
            session,
            subject_type="plot",
            subject_id=plot_id,
            attribute="area_sqm",
            value_numeric=Decimal("7284.3"),
            unit="sqm",
            source_type=SourceType.FIELD_OFFICER,
            observed_at=NOW - dt.timedelta(days=5),
            recorded_at=NOW - dt.timedelta(days=5),
        )
        value = resolver.resolve(
            session, subject_type="plot", subject_id=plot_id, attribute="area_sqm", as_of=NOW
        )
        assert value is not None
        assert value.value == Decimal("7284.3")
        assert value.has_open_discrepancy is False
        assert value.confidence > 0.7
        assert value.evidence.kind == "observation"

    def test_unknown_attribute_resolves_to_none_not_zero(self, session) -> None:
        """FR-103: absent is unknown. A caller must never read it as zero."""
        from agrivardhak.provenance import resolver

        assert (
            resolver.resolve(
                session,
                subject_type="plot",
                subject_id=uuid.uuid4(),
                attribute="area_sqm",
                as_of=NOW,
            )
            is None
        )

    def test_three_way_conflict_raises_a_discrepancy_and_picks_no_winner(self, session) -> None:
        """INV-4, and the demo's provenance moment.

        The system must expose all three claims. It may show a best-supported value for
        display, but it carries the conflict flag and a reduced confidence with it — it does
        not present 1.8 acres as settled.
        """
        from agrivardhak.provenance import resolver

        plot_id = uuid.uuid4()
        claims = [
            (Decimal("8093.7"), SourceType.FARMER_SELF_REPORT, 3),  # 2.0 ac
            (Decimal("6474.9"), SourceType.EXTERNAL_SOURCE, 2),  # 1.6 ac
            (Decimal("7284.3"), SourceType.FIELD_OFFICER, 1),  # 1.8 ac
        ]
        discrepancy = None
        for value, source, days_ago in claims:
            _, discrepancy = resolver.record_observation(
                session,
                subject_type="plot",
                subject_id=plot_id,
                attribute="area_sqm",
                value_numeric=value,
                unit="sqm",
                source_type=source,
                observed_at=NOW - dt.timedelta(days=days_ago),
                recorded_at=NOW - dt.timedelta(days=days_ago),
            )

        assert discrepancy is not None
        assert discrepancy.status is DiscrepancyStatus.OPEN
        assert len(discrepancy.claims) == 3, "every claimed value must be recorded"
        assert float(discrepancy.spread_pct) > float(discrepancy.tolerance_pct)

        recorded = {float(c["value"]) for c in discrepancy.claims}
        assert recorded == {8093.7, 6474.9, 7284.3}

        resolved = resolver.resolve(
            session, subject_type="plot", subject_id=plot_id, attribute="area_sqm", as_of=NOW
        )
        assert resolved is not None
        assert resolved.has_open_discrepancy is True, "the conflict must reach the caller"

        clean_confidence = trust.effective_confidence(
            source_type=SourceType.FIELD_OFFICER,
            verification_status=VerificationStatus.UNVERIFIED,
            observed_at=NOW - dt.timedelta(days=1),
            as_of=NOW,
            attribute="area_sqm",
        )
        assert resolved.confidence < clean_confidence, "conflict must reduce confidence"

    def test_repeated_reports_from_one_source_are_not_a_conflict(self, session) -> None:
        from agrivardhak.provenance import resolver

        plot_id = uuid.uuid4()
        discrepancy = None
        for value, days_ago in ((Decimal("8093.7"), 3), (Decimal("6474.9"), 1)):
            _, discrepancy = resolver.record_observation(
                session,
                subject_type="plot",
                subject_id=plot_id,
                attribute="area_sqm",
                value_numeric=value,
                unit="sqm",
                source_type=SourceType.FARMER_SELF_REPORT,
                observed_at=NOW - dt.timedelta(days=days_ago),
                recorded_at=NOW - dt.timedelta(days=days_ago),
            )
        assert discrepancy is None, "one source changing its mind is a correction, not a conflict"

    def test_stale_claims_are_not_compared(self, session) -> None:
        """Two crop-health readings months apart are a time series, not a disagreement."""
        from agrivardhak.provenance import resolver

        cycle_id = uuid.uuid4()
        discrepancy = None
        for value, source, days_ago in (
            (Decimal("40"), SourceType.FARMER_SELF_REPORT, 120),
            (Decimal("85"), SourceType.FIELD_OFFICER, 1),
        ):
            _, discrepancy = resolver.record_observation(
                session,
                subject_type="crop_cycle",
                subject_id=cycle_id,
                attribute="crop_health_pct",
                value_numeric=value,
                unit="pct",
                source_type=source,
                observed_at=NOW - dt.timedelta(days=days_ago),
                recorded_at=NOW - dt.timedelta(days=days_ago),
            )
        assert discrepancy is None

    def test_human_resolution_closes_the_conflict_and_keeps_the_trail(
        self, session, staff_user
    ) -> None:
        """FR-305: losing claims are marked DISPUTED, never deleted."""
        from agrivardhak.domain.models.provenance import Observation
        from agrivardhak.provenance import resolver

        plot_id = uuid.uuid4()
        observations = []
        discrepancy = None
        for value, source in (
            (Decimal("8093.7"), SourceType.FARMER_SELF_REPORT),
            (Decimal("7284.3"), SourceType.FIELD_OFFICER),
        ):
            obs, discrepancy = resolver.record_observation(
                session,
                subject_type="plot",
                subject_id=plot_id,
                attribute="area_sqm",
                value_numeric=value,
                unit="sqm",
                source_type=source,
                observed_at=NOW - dt.timedelta(days=1),
                recorded_at=NOW - dt.timedelta(days=1),
            )
            observations.append(obs)

        assert discrepancy is not None
        winner = observations[1]
        user_id = staff_user.id

        resolver.resolve_discrepancy(
            session,
            discrepancy=discrepancy,
            resolver_user_id=user_id,
            winning_observation_id=winner.id,
            rationale="Field officer re-measured with the record of rights present.",
            resolved_at=NOW,
        )

        assert discrepancy.status is DiscrepancyStatus.RESOLVED
        assert discrepancy.resolution_observation_id == winner.id

        loser = session.get(Observation, observations[0].id)
        assert loser is not None, "the losing claim must survive"
        assert loser.verification_status is VerificationStatus.DISPUTED
        assert session.get(Observation, winner.id).verification_status is (
            VerificationStatus.VERIFIED
        )

    def test_resolution_rejects_an_observation_outside_the_conflict(
        self, session, staff_user
    ) -> None:
        from agrivardhak.provenance import resolver

        plot_id = uuid.uuid4()
        discrepancy = None
        for value, source in (
            (Decimal("8093.7"), SourceType.FARMER_SELF_REPORT),
            (Decimal("7284.3"), SourceType.FIELD_OFFICER),
        ):
            _, discrepancy = resolver.record_observation(
                session,
                subject_type="plot",
                subject_id=plot_id,
                attribute="area_sqm",
                value_numeric=value,
                unit="sqm",
                source_type=source,
                observed_at=NOW - dt.timedelta(days=1),
                recorded_at=NOW - dt.timedelta(days=1),
            )
        assert discrepancy is not None
        with pytest.raises(ValueError, match="not one of the recorded claims"):
            resolver.resolve_discrepancy(
                session,
                discrepancy=discrepancy,
                resolver_user_id=staff_user.id,
                winning_observation_id=uuid.uuid4(),
                rationale="nope",
                resolved_at=NOW,
            )
