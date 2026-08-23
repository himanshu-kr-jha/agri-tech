"""Outcome, adherence and attribution — M18, INV-7, SAF-12, and the funding safety line.

These tests are about the difference between a system that learns and one that flatters
itself. Every one of them asserts a refusal.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from agrivardhak.domain import enums
from agrivardhak.domain.models.decisions import Intervention, Outcome
from agrivardhak.intelligence import funding
from agrivardhak.intelligence.contracts import EvidenceRef, ModuleInput
from agrivardhak.learning import attribution

NOW = dt.datetime(2026, 6, 1, tzinfo=dt.UTC)


def _intervention(followed=enums.Adherence.YES, fidelity=0.95, delay=0) -> Intervention:
    return Intervention(
        id=uuid.uuid4(),
        recommendation_id=uuid.uuid4(),
        action_taken="did the thing",
        executed_at=NOW,
        followed=followed,
        fidelity=fidelity,
        delay_days=delay,
    )


def _outcome(observed=4.2, baseline=3.6, conditions=None) -> Outcome:
    return Outcome(
        id=uuid.uuid4(),
        target_type="crop_cycle",
        target_id=uuid.uuid4(),
        metric="yield_t_per_ha",
        baseline_value=baseline,
        observed_value=observed,
        unit="t/ha",
        external_conditions=conditions,
    )


# --------------------------------------------------------------------------- INV-7


def test_advice_that_was_never_followed_is_not_scored_as_failed() -> None:
    """INV-7, the whole reason adherence is recorded.

    Recommendations people ignore are not a random sample — they are the inconvenient ones,
    which are often the right ones. A model that learns from them un-learns its best advice.
    """
    result = attribution.attribute(
        intervention=_intervention(followed=enums.Adherence.NO, fidelity=None),
        outcome=_outcome(observed=2.0, baseline=3.6),
    )
    assert result.scored is False
    assert result.strength == "CONFOUNDED"
    assert "not implemented" in result.confounders


def test_unknown_adherence_is_treated_as_unscoreable_not_as_followed() -> None:
    """The optimistic reading of a missing record is the one that corrupts the training data."""
    result = attribution.attribute(
        intervention=_intervention(followed=enums.Adherence.UNKNOWN, fidelity=None),
        outcome=_outcome(),
    )
    assert result.scored is False


def test_a_half_implemented_recommendation_does_not_score_either() -> None:
    """What was done and what was advised are different enough that the outcome cannot tell."""
    result = attribution.attribute(
        intervention=_intervention(fidelity=0.3), outcome=_outcome(observed=2.0)
    )
    assert result.scored is False
    assert "fidelity" in result.rationale


def test_an_unscoreable_outcome_writes_no_attribution_row(session) -> None:
    result = attribution.attribute(
        intervention=_intervention(followed=enums.Adherence.NO, fidelity=None),
        outcome=_outcome(),
    )
    assert (
        attribution.persist_attribution(
            session, outcome=_outcome(), intervention=_intervention(), result=result
        )
        is None
    )


# --------------------------------------------------------------------------- SAF-12


def test_a_favourable_season_confounds_the_claim_rather_than_confirming_it() -> None:
    """SAF-12. A system that claims credit for every good outcome has credit worth nothing."""
    result = attribution.attribute(
        intervention=_intervention(),
        outcome=_outcome(conditions={"weather_favourable": True}),
    )
    assert result.strength == "CONFOUNDED"
    assert any("favourable" in c for c in result.confounders)


def test_a_price_move_in_the_same_direction_confounds_an_income_result() -> None:
    result = attribution.attribute(
        intervention=_intervention(),
        outcome=_outcome(conditions={"price_moved_favourably": True}),
    )
    assert result.strength == "CONFOUNDED"


def test_a_clean_result_can_be_claimed_but_never_as_certainty() -> None:
    result = attribution.attribute(intervention=_intervention(), outcome=_outcome())
    assert result.strength in ("HIGH", "MODERATE")
    assert "absence of evidence is not evidence of absence" in result.rationale


def test_a_change_inside_ordinary_variation_is_neither_success_nor_failure() -> None:
    result = attribution.attribute(
        intervention=_intervention(), outcome=_outcome(observed=3.62, baseline=3.6)
    )
    assert result.strength == "UNCERTAIN"


def test_no_baseline_means_no_result() -> None:
    """ "Yield was 4.2 t" is not a finding. It needs something to be measured against."""
    result = attribution.attribute(intervention=_intervention(), outcome=_outcome(baseline=None))
    assert result.strength == "UNCERTAIN"
    assert "no baseline" in result.confounders


def test_acting_far_too_late_confounds_the_result() -> None:
    result = attribution.attribute(
        intervention=_intervention(delay=30), outcome=_outcome(observed=2.0)
    )
    assert result.strength == "CONFOUNDED"
    assert any("late" in c for c in result.confounders)


def test_the_impact_summary_reports_what_it_could_not_attribute(session) -> None:
    """A panel showing only successes measures our own selection, not our impact."""
    summary = attribution.summarise(session, organization_id=uuid.uuid4())
    assert "unattributable" in summary
    assert "selection" in str(summary["note"])


# --------------------------------------------------------------------------- FR-605


def _need() -> funding.CapitalNeed:
    return funding.CapitalNeed(
        crop_name="Wheat",
        tract="DOAB",
        area_sqm=Decimal("4000000"),
        cost_paise_per_ha=5_000_000,
        needed_by=dt.date(2026, 11, 10),
        farmer_ids=[uuid.uuid4() for _ in range(200)],
        evidence=[EvidenceRef(kind="domain_row", id=uuid.uuid4(), label="plan", as_of=NOW)],
    )


def test_no_farmer_is_ever_ranked_for_withholding_support() -> None:
    """FR-605 / SAF-04. The most plausible way this software could do real harm.

    An FPO short of capital has a financing problem. Turning it into a selection problem is
    how a collective stops being one, so the module answers in timing and sourcing and never
    produces a per-farmer list.
    """
    output = funding.run(
        ModuleInput(
            organization_id=uuid.uuid4(),
            as_of=NOW,
            data={"needs": [_need()], "working_capital_paise": 1_000_000},
        )
    )
    text = " ".join(
        [f.statement for f in output.findings]
        + [a.rationale for a in output.proposed_actions]
        + [alt for a in output.proposed_actions for alt in a.alternatives]
    ).lower()
    for banned in (
        "withhold",
        "exclude these farmers",
        "prioritise farmers",
        "creditworthy",
        "which members to fund",
        "drop the smallest",
    ):
        assert banned not in text, f"funding output edged toward selecting members: {banned}"


def test_a_shortfall_is_answered_with_timing_and_sourcing(monkeypatch) -> None:
    output = funding.run(
        ModuleInput(
            organization_id=uuid.uuid4(),
            as_of=NOW,
            data={"needs": [_need()], "working_capital_paise": 1_000_000},
        )
    )
    assert any(f.key == "capital_shortfall" for f in output.findings)
    action = next(a for a in output.proposed_actions if a.key == "close_capital_gap")
    assert "stagger" in action.rationale.lower()
    assert "FR-605" in str(action.expected_impact["never"])


def test_reducing_area_is_offered_as_a_board_decision_across_the_membership() -> None:
    """It is a legitimate lever. What it may never become is a list of who to cut."""
    output = funding.run(
        ModuleInput(
            organization_id=uuid.uuid4(),
            as_of=NOW,
            data={"needs": [_need()], "working_capital_paise": 1_000_000},
        )
    )
    action = next(a for a in output.proposed_actions if a.key == "close_capital_gap")
    assert "across the membership" in action.rationale


def test_unknown_working_capital_produces_no_shortfall_claim() -> None:
    """Unknown is not zero. Claiming a shortfall we cannot compute would be inventing one."""
    output = funding.run(
        ModuleInput(
            organization_id=uuid.uuid4(),
            as_of=NOW,
            data={"needs": [_need()], "working_capital_paise": None},
        )
    )
    assert not any(f.key == "capital_shortfall" for f in output.findings)
    assert any("not recorded" in d for d in output.degraded_inputs)


def test_the_requirement_carries_a_buffer_and_says_it_is_a_judgement() -> None:
    output = funding.run(
        ModuleInput(
            organization_id=uuid.uuid4(),
            as_of=NOW,
            data={"needs": [_need()], "working_capital_paise": 100_000_000_000},
        )
    )
    requirement = next(f for f in output.findings if f.key == "capital_requirement")
    assert any("judgement" in a for a in requirement.assumptions)
