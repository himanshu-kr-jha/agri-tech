"""Quality Intelligence tests — FR-531…534.

The property that matters most here is not accuracy — the coefficients are placeholders — but
**honesty about uncertainty**. A yield built on a stale self-report must not arrive at the CEO
looking as solid as one built on a field-officer reading from Tuesday.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest

from agrivardhak.intelligence import quality
from agrivardhak.intelligence.contracts import EvidenceRef, ModuleInput, ProvenancedValue

NOW = dt.datetime(2026, 8, 23, 6, 0, tzinfo=dt.UTC)
ORG = uuid.uuid4()


def _health(
    pct: float,
    *,
    confidence: float = 0.9,
    stale: bool = False,
    disputed: bool = False,
    source: str = "FIELD_OFFICER",
) -> ProvenancedValue:
    return ProvenancedValue(
        attribute="crop_health_pct",
        value=Decimal(str(pct)),
        unit="pct",
        confidence=confidence,
        source_type=source,
        observed_at=NOW - dt.timedelta(days=2),
        is_stale=stale,
        has_open_discrepancy=disputed,
        evidence=EvidenceRef(
            kind="observation", id=uuid.uuid4(), label=f"health {pct}%", as_of=NOW
        ),
    )


def _cycle(**kw) -> quality.CycleInput:
    defaults = dict(
        cycle_id=uuid.uuid4(),
        crop_name="Potato",
        variety_name="Kufri Bahar",
        farmer_id=uuid.uuid4(),
        plot_id=uuid.uuid4(),
        area_sqm=Decimal("10000"),  # 1 ha
        sowing_date=dt.date(2026, 11, 5),
        duration_days=110,
        base_yield_kg_per_ha=25_000.0,
        health=_health(88),
    )
    defaults.update(kw)
    return quality.CycleInput(**defaults)


# --------------------------------------------------------------------------- yield


def test_one_hectare_at_full_health_yields_about_the_base() -> None:
    cycle = _cycle(health=_health(100), water_assured=True, nutrient_plan_followed=True)
    yield_kg, factors = quality.expected_yield_kg(cycle, quality.YieldModel())
    assert float(yield_kg) == pytest.approx(25_000, rel=0.01)
    assert factors["health"] == pytest.approx(1.0)


def test_poor_health_costs_more_than_proportionally() -> None:
    """A crop at 50% health does not give half a harvest.

    The damage that shows as poor health is the damage that costs grain, so the response is
    superlinear. A linear model would systematically over-promise on struggling cycles —
    exactly the ones an FPO most needs the truth about.
    """
    model = quality.YieldModel()
    half = quality.health_factor(50, model)
    assert half < 0.5
    assert quality.health_factor(100, model) == pytest.approx(1.0)
    assert quality.health_factor(0, model) == 0.0


def test_rainfed_yields_less_than_irrigated() -> None:
    model = quality.YieldModel()
    assert quality.water_factor(False, model) < quality.water_factor(True, model)


def test_missing_inputs_are_neutral_not_optimistic() -> None:
    """Absent data must not read as a good season.

    Returning 1.0 keeps the arithmetic sane; the *cost* of not knowing is charged to
    confidence instead, where a reader can see it.
    """
    model = quality.YieldModel()
    assert quality.water_factor(None, model) == 1.0
    assert quality.nutrient_factor(None, model) == 1.0
    assert quality.stress_factor(None, model) == 1.0

    cycle = _cycle(water_assured=None, weather_stress_sd=None)
    confidence, gaps = quality.prediction_confidence(cycle)
    assert gaps, "the gaps must be recorded even though the factors are neutral"
    assert confidence < 0.85


def test_missing_yield_coefficient_produces_zero_not_a_guess() -> None:
    """A fabricated default would become tonnage the FPO plans against."""
    yield_kg, factors = quality.expected_yield_kg(
        _cycle(base_yield_kg_per_ha=None), quality.YieldModel()
    )
    assert yield_kg == 0
    assert "unavailable" in factors


def test_tract_factor_lowers_yield_on_vindhyan_soils() -> None:
    """Yamuna-par is shallower and largely rain-fed (seed/reference.py TRACTS)."""
    good, _ = quality.expected_yield_kg(_cycle(tract_factor=1.0), quality.YieldModel())
    poor, _ = quality.expected_yield_kg(_cycle(tract_factor=0.72), quality.YieldModel())
    assert poor < good


# --------------------------------------------------------------------------- confidence


def test_confidence_never_exceeds_the_observation_it_rests_on() -> None:
    """INV-3 paying for itself. A prediction cannot be surer than its input."""
    weak = _cycle(health=_health(88, confidence=0.42), water_assured=True, weather_stress_sd=0.4)
    confidence, _ = quality.prediction_confidence(weak)
    assert confidence <= 0.42


def test_stale_and_disputed_health_both_reduce_confidence() -> None:
    base, _ = quality.prediction_confidence(
        _cycle(water_assured=True, weather_stress_sd=0.2, health=_health(88))
    )
    stale, _ = quality.prediction_confidence(
        _cycle(water_assured=True, weather_stress_sd=0.2, health=_health(88, stale=True))
    )
    disputed, _ = quality.prediction_confidence(
        _cycle(water_assured=True, weather_stress_sd=0.2, health=_health(88, disputed=True))
    )
    assert stale < base
    assert disputed < base


def test_no_health_observation_collapses_confidence() -> None:
    confidence, gaps = quality.prediction_confidence(_cycle(health=None))
    assert confidence < 0.6
    assert any("crop-health" in g for g in gaps)


def test_lower_confidence_widens_the_yield_band() -> None:
    """An uncertain prediction reporting a narrow range is worse than useless."""
    sure = quality.predict_cycle(
        _cycle(health=_health(88, confidence=0.92), water_assured=True, weather_stress_sd=0.1),
        quality.YieldModel(),
    )
    unsure = quality.predict_cycle(
        _cycle(health=_health(88, confidence=0.45)), quality.YieldModel()
    )
    sure_band = float(sure.yield_high_kg - sure.yield_low_kg)
    unsure_band = float(unsure.yield_high_kg - unsure.yield_low_kg)
    assert unsure_band > sure_band


# --------------------------------------------------------------------------- grade


def test_grade_is_a_distribution_not_a_verdict() -> None:
    """FR-531. Selling a whole lot at the headline grade eats the difference at weighing."""
    prediction = quality.predict_cycle(_cycle(health=_health(90)), quality.YieldModel())
    assert set(prediction.grade_distribution) == {"A", "B", "C"}
    assert sum(prediction.grade_distribution.values()) == pytest.approx(1.0, abs=0.01)
    assert prediction.grade_distribution["A"] < 1.0, "no lot is 100% one grade"


def test_healthier_crops_skew_toward_grade_a() -> None:
    model = quality.YieldModel()
    healthy, _ = quality.grade_distribution(_cycle(health=_health(92)), model, 0.9)
    poor, _ = quality.grade_distribution(_cycle(health=_health(55)), model, 0.9)
    assert healthy["A"] > poor["A"]
    assert poor["C"] > healthy["C"]


def test_uncertainty_flattens_the_grade_distribution() -> None:
    """When we are unsure about health we are unsure about grade. Say so."""
    model = quality.YieldModel()
    confident, _ = quality.grade_distribution(_cycle(health=_health(92)), model, 0.95)
    unsure, _ = quality.grade_distribution(_cycle(health=_health(92)), model, 0.40)
    assert unsure["A"] < confident["A"], "low confidence must not produce a confident grade"


def test_no_health_data_gives_a_wide_uninformative_split() -> None:
    dist, headline = quality.grade_distribution(_cycle(health=None), quality.YieldModel(), 0.5)
    assert dist["A"] < 0.5
    assert headline == "B"


# --------------------------------------------------------------------------- window


def test_harvest_is_a_window_not_a_date() -> None:
    """The FPO books a cold store against a range; a single date implies false precision."""
    start, end = quality.harvest_window(_cycle(sowing_date=dt.date(2026, 11, 5), duration_days=110))
    assert start is not None and end is not None
    assert start < end
    assert (end - start).days >= 10


def test_unsown_cycle_has_no_window() -> None:
    assert quality.harvest_window(_cycle(sowing_date=None)) == (None, None)


# --------------------------------------------------------------------------- risk


def test_cycle_below_its_contracted_grade_is_flagged() -> None:
    """FR-533: flagged while the harvest is still ahead, so the loss is preventable."""
    prediction = quality.predict_cycle(
        _cycle(health=_health(58), target_grade="A"), quality.YieldModel()
    )
    assert prediction.at_risk
    assert prediction.risk_reason and "below the required grade" in prediction.risk_reason


def test_cycle_with_no_target_grade_is_not_flagged() -> None:
    """Flagging a cycle nobody contracted for is noise, and noise trains people to ignore."""
    assert not quality.predict_cycle(
        _cycle(health=_health(55), target_grade=None), quality.YieldModel()
    ).at_risk


def test_healthy_cycle_meeting_its_target_is_not_flagged() -> None:
    assert not quality.predict_cycle(
        _cycle(health=_health(95), target_grade="B"), quality.YieldModel()
    ).at_risk


# --------------------------------------------------------------------------- aggregation


def test_aggregate_answers_the_originating_question() -> None:
    """*"How much will we have, and when?"* — the pain the whole product started from."""
    cycles = [
        _cycle(crop_name="Potato", area_sqm=Decimal("10000")),
        _cycle(crop_name="Potato", area_sqm=Decimal("20000")),
        _cycle(crop_name="Wheat", base_yield_kg_per_ha=4000.0, area_sqm=Decimal("10000")),
    ]
    predictions = [quality.predict_cycle(c, quality.YieldModel()) for c in cycles]
    rolled = quality.aggregate(predictions)

    assert set(rolled) == {"Potato", "Wheat"}
    assert rolled["Potato"]["cycles"] == 2
    assert rolled["Potato"]["expected_kg"] > rolled["Wheat"]["expected_kg"]
    assert rolled["Potato"]["harvest_from"] is not None


def test_aggregate_confidence_is_a_weighted_mean_not_the_minimum() -> None:
    """Weakest-link is the wrong rule for a rollup.

    A forecast assembled from many independently observed cycles is not made worthless by one
    plot nobody visited. An earlier draft used min() and reported 0.00 confidence on a
    1,900-tonne forecast built from 1,282 cycles — wrong, and useless, because it told the
    CEO nothing about where the uncertainty actually sat.

    The weak evidence is reported separately instead, which is the number a CEO can act on.
    """
    predictions = [
        quality.predict_cycle(_cycle(health=_health(88, confidence=0.9)), quality.YieldModel()),
        quality.predict_cycle(_cycle(health=_health(88, confidence=0.9)), quality.YieldModel()),
        quality.predict_cycle(_cycle(health=_health(88, confidence=0.30)), quality.YieldModel()),
    ]
    rolled = quality.aggregate(predictions)["Potato"]

    assert rolled["confidence"] > 0.30, "one weak cycle must not zero the aggregate"
    assert rolled["confidence"] < 0.9, "nor may it be ignored"
    assert rolled["weakest_confidence"] <= 0.30, "the worst case is still reported"
    assert rolled["poorly_evidenced_cycles"] == 1


def test_aggregate_confidence_is_weighted_by_tonnage() -> None:
    """A big cycle's evidence matters more, because it contributes more of the number."""
    big_and_sure = _cycle(area_sqm=Decimal("100000"), health=_health(88, confidence=0.9))
    small_and_unsure = _cycle(area_sqm=Decimal("1000"), health=_health(88, confidence=0.2))
    big = quality.predict_cycle(big_and_sure, quality.YieldModel())
    small = quality.predict_cycle(small_and_unsure, quality.YieldModel())
    rolled = quality.aggregate([big, small])["Potato"]

    # The 10 ha plot carries ~100x the tonnage of the 0.1 ha one, so the aggregate should sit
    # close to its confidence rather than midway between the two.
    assert abs(rolled["confidence"] - big.confidence) < 0.05
    assert rolled["confidence"] - small.confidence > 0.5
    assert rolled["weakest_confidence"] == pytest.approx(small.confidence)


def test_poorly_evidenced_cycles_are_surfaced_as_their_own_finding() -> None:
    """The actionable version: a field visit here buys more confidence than anything else."""
    out = quality.run(
        ModuleInput(
            organization_id=ORG,
            as_of=NOW,
            data={"cycles": [_cycle(health=_health(88, confidence=0.2)), _cycle()]},
        )
    )
    gap = [f for f in out.findings if f.key == "evidence_gap.crop_health"]
    assert gap, "cycles too weakly evidenced to forecast must be named"
    assert gap[0].evidence, "a claim about missing evidence still needs evidence of its own"
    assert all(ref.kind == "domain_row" for ref in gap[0].evidence), (
        "it must cite the cycles, not the observations that are missing"
    )


def test_a_crop_with_no_observations_still_appears_in_the_forecast() -> None:
    """An FPO reading a forecast that omits its paddy would conclude it has no paddy."""
    out = quality.run(
        ModuleInput(
            organization_id=ORG,
            as_of=NOW,
            data={"cycles": [_cycle(crop_name="Paddy", base_yield_kg_per_ha=4200.0, health=None)]},
        )
    )
    production = [f for f in out.findings if f.key == "expected_production.paddy"]
    assert production, "the crop must not vanish for lack of a health reading"
    assert production[0].confidence < 0.6, "but it must say how little it knows"


# --------------------------------------------------------------------------- learning


def test_prediction_error_reports_both_absolute_and_relative() -> None:
    """FR-534. A 500 kg miss is a bad model on a smallholding and noise on 5,000 t."""
    error = quality.prediction_error(Decimal("25000"), Decimal("20000"))
    assert error["error_kg"] == 5000
    assert error["error_pct"] == pytest.approx(25.0)
    assert error["abs_error_pct"] == pytest.approx(25.0)

    under = quality.prediction_error(Decimal("18000"), Decimal("20000"))
    assert under["error_pct"] < 0, "under-prediction must be signed, not absolute"
    assert under["abs_error_pct"] > 0


def test_prediction_error_survives_a_zero_actual() -> None:
    """A total crop failure must not divide by zero on the way into the learning loop."""
    error = quality.prediction_error(Decimal("25000"), Decimal("0"))
    assert error["error_pct"] == 0.0


# --------------------------------------------------------------------------- module contract


def test_run_produces_production_and_quality_findings() -> None:
    out = quality.run(
        ModuleInput(
            organization_id=ORG,
            as_of=NOW,
            data={"cycles": [_cycle(), _cycle(crop_name="Wheat", base_yield_kg_per_ha=4000.0)]},
        )
    )
    assert out.module == quality.MODULE
    keys = {f.key for f in out.findings}
    assert any(k.startswith("expected_production.") for k in keys)
    assert any(k.startswith("expected_quality.") for k in keys)
    for finding in out.findings:
        assert finding.evidence, f"unevidenced finding: {finding.key}"


def test_run_proposes_intervention_only_when_cycles_are_at_risk() -> None:
    safe = quality.run(ModuleInput(organization_id=ORG, as_of=NOW, data={"cycles": [_cycle()]}))
    assert not safe.proposed_actions

    risky = quality.run(
        ModuleInput(
            organization_id=ORG,
            as_of=NOW,
            data={"cycles": [_cycle(health=_health(52), target_grade="A")]},
        )
    )
    assert risky.proposed_actions
    action = risky.proposed_actions[0]
    assert action.recommendation_type == "RISK_MITIGATION"
    assert "verify" in action.rationale.lower(), "must prompt inspection, not assert a result"


def test_run_reports_what_it_was_missing() -> None:
    """NFR-301: degradation is stated, not silent."""
    out = quality.run(
        ModuleInput(
            organization_id=ORG,
            as_of=NOW,
            data={"cycles": [_cycle(health=None, weather_stress_sd=None)]},
        )
    )
    assert any("crop-health" in d for d in out.degraded_inputs)
    assert any("weather" in d for d in out.degraded_inputs)


def test_run_with_no_cycles_degrades_rather_than_failing() -> None:
    out = quality.run(ModuleInput(organization_id=ORG, as_of=NOW, data={}))
    assert out.findings == []
    assert out.degraded_inputs


def test_module_is_pure_and_replayable() -> None:
    """ARCHITECTURE §9: the property the whole replay guarantee rests on."""
    cycle = _cycle(cycle_id=uuid.UUID(int=7), farmer_id=uuid.UUID(int=8), plot_id=uuid.UUID(int=9))
    data = {"cycles": [cycle]}
    first = quality.run(ModuleInput(organization_id=ORG, as_of=NOW, data=data))
    second = quality.run(ModuleInput(organization_id=ORG, as_of=NOW, data=data))
    assert first.model_dump_json() == second.model_dump_json()
