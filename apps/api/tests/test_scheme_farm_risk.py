"""Scheme, Farm and Risk modules — M9, M10, M8.

Grouped because the tests that matter most across all three are the same tests: does the
module refuse to invent, and does it refuse to say anything about a farmer that could be
used against them (FR-566, FR-605, SAF-04).
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from agrivardhak.intelligence import farm, risk, scheme
from agrivardhak.intelligence.contracts import EvidenceRef, ModuleInput

NOW = dt.datetime(2026, 1, 20, tzinfo=dt.UTC)


def _ref(kind: str = "domain_row") -> EvidenceRef:
    return EvidenceRef(kind=kind, id=uuid.uuid4(), label="row", as_of=NOW)


# --------------------------------------------------------------------------- scheme


def _farmer(**facts) -> scheme.FarmerFacts:
    return scheme.FarmerFacts(
        farmer_id=uuid.uuid4(),
        name="Test Farmer",
        facts=facts,
        evidence=[_ref()],
        consented_purposes=frozenset({"SERVICE_DELIVERY"}),
    )


def test_no_application_is_ever_auto_submitted() -> None:
    """FR-567 / SAF-11. An auto-filed application in a farmer's name is a fraud risk."""
    output = scheme.run(
        ModuleInput(
            organization_id=uuid.uuid4(),
            as_of=NOW,
            data={
                "farmers": [
                    _farmer(is_landholder=True, has_aadhaar=True, is_income_tax_payer=False)
                ]
            },
        )
    )
    assert output.proposed_actions
    for action in output.proposed_actions:
        assert action.expected_impact["auto_submit"] is False
        assert "portal" in action.expected_impact
        assert "never submits" in action.rationale or "files their own" in action.rationale


def test_a_missing_fact_is_insufficient_data_not_ineligible() -> None:
    """The distinction that decides whether thousands of eligible farmers are ever found.

    Treating an unrecorded Aadhaar as "no Aadhaar" marks them ineligible, and nobody ever
    finds out why.
    """
    assessment = scheme.assess(
        next(s for s in scheme.SCHEMES if s.key == "pm_kisan"),
        "farmer",
        uuid.uuid4(),
        "Test",
        {"is_landholder": True},  # no aadhaar fact at all
        [_ref()],
        NOW.date(),
        frozenset({"SERVICE_DELIVERY"}),
    )
    assert assessment.status == "INSUFFICIENT_DATA"
    assert assessment.unknown
    assert assessment.status != "NOT_ELIGIBLE"


def test_a_sensitive_criterion_is_skipped_without_consent(monkeypatch) -> None:
    """FR-566 / INV-9.

    Reading a consent-gated attribute the farmer never opted into is exactly the misuse.
    """
    without_consent = scheme.assess(
        next(s for s in scheme.SCHEMES if s.key == "pm_kisan"),
        "farmer",
        uuid.uuid4(),
        "Test",
        {"is_landholder": True, "has_aadhaar": True, "is_income_tax_payer": False},
        [_ref()],
        NOW.date(),
        consented_purposes=frozenset(),
    )
    assert any("consent" in u for u in without_consent.unknown)
    assert without_consent.status == "INSUFFICIENT_DATA"


def test_the_module_produces_no_per_farmer_ranking() -> None:
    """SAF-04 / FR-605. The structural guarantee, not a policy anyone has to remember.

    A ranking of farmers is the artifact that "don't invest in this farmer" would be built
    from, so the module does not produce one at all.
    """
    output = scheme.run(
        ModuleInput(
            organization_id=uuid.uuid4(),
            as_of=NOW,
            data={"farmers": [_farmer(is_landholder=True) for _ in range(5)]},
        )
    )
    for finding in output.findings:
        text = finding.statement.lower()
        for banned in ("worth investing", "priority farmer", "rank", "score of", "least deserving"):
            assert banned not in text


def test_unverified_rules_cannot_produce_a_confident_assessment() -> None:
    output = scheme.run(
        ModuleInput(
            organization_id=uuid.uuid4(),
            as_of=NOW,
            data={
                "farmers": [
                    _farmer(is_landholder=True, has_aadhaar=True, is_income_tax_payer=False)
                ]
            },
        )
    )
    eligibility = [f for f in output.findings if f.key.startswith("scheme_eligibility.")]
    assert eligibility
    assert all(f.confidence <= scheme.UNVERIFIED_CONFIDENCE_CEILING for f in eligibility)

    # The gap findings are deliberately exempt and sit above the ceiling. "One unrecorded
    # fact blocks 812 assessments" is a count of our own data — it is true whatever the
    # scheme rules turn out to say, so capping it at the rules' confidence would understate
    # something we actually know.
    gaps = [f for f in output.findings if f.key.startswith("scheme_gap.")]
    assert all(f.confidence > scheme.UNVERIFIED_CONFIDENCE_CEILING for f in gaps)


def test_the_biggest_single_blocker_is_named() -> None:
    """One field campaign clearing 800 assessments beats 800 individual follow-ups."""
    farmers = [_farmer(is_landholder=True) for _ in range(10)]
    output = scheme.run(
        ModuleInput(organization_id=uuid.uuid4(), as_of=NOW, data={"farmers": farmers})
    )
    gaps = [f for f in output.findings if f.key.startswith("scheme_gap.")]
    assert gaps, "the module must say what one missing fact is costing"


# --------------------------------------------------------------------------- farm


def _block(tract="DOAB", acres=500.0, irrigated=0.8) -> farm.LandBlock:
    return farm.LandBlock(
        tract=tract,
        area_sqm=Decimal(str(acres * 4046.86)),
        irrigated_share=irrigated,
        farmer_ids=[uuid.uuid4() for _ in range(10)],
        evidence=[_ref()],
    )


def _option(crop, yield_kg=4000.0, low=2000, high=2400, season="RABI") -> farm.CropOption:
    return farm.CropOption(
        crop_name=crop,
        season=season,
        expected_yield_kg_per_ha=yield_kg,
        price_low_paise_per_kg=low,
        price_high_paise_per_kg=high,
        price_evidence=_ref("external_record"),
    )


def test_an_orchard_is_not_ranked_against_an_annual_crop() -> None:
    """A perennial's return on annual operating cost is high because the capital is sunk.

    Ranked together, guava came out at eleven rupees per rupee and would read as "convert
    the wheat land", silently omitting three years of no income.
    """
    returns = [
        farm.crop_return(
            _option("Guava", 30000.0, 2200, 2500, "PERENNIAL"),
            _block(),
            farm.CROP_ECONOMICS["Guava"],
            farm.Constraints(working_capital_paise=None),
        ),
        farm.crop_return(
            _option("Wheat"),
            _block(),
            farm.CROP_ECONOMICS["Wheat"],
            farm.Constraints(working_capital_paise=None),
        ),
    ]
    ranked = farm.rank([r for r in returns if r])
    assert all(not r.is_perennial for r in ranked)
    assert ranked and ranked[0].crop_name == "Wheat"


def test_ranking_uses_the_pessimistic_end_of_the_price_band() -> None:
    """Ranking on the optimistic end favours whichever crop has the widest uncertainty."""
    wide = farm.crop_return(
        _option("Wheat", 4000.0, 1000, 5000),
        _block(),
        farm.CROP_ECONOMICS["Wheat"],
        farm.Constraints(working_capital_paise=None),
    )
    narrow = farm.crop_return(
        _option("Mustard", 1500.0, 5900, 6100),
        _block(),
        farm.CROP_ECONOMICS["Mustard"],
        farm.Constraints(working_capital_paise=None),
    )
    ranked = farm.rank([r for r in (wide, narrow) if r])
    assert ranked[0].crop_name == "Mustard", "the wide band must not win on its upside"


def test_a_small_water_shortfall_discounts_yield_rather_than_excluding_the_crop() -> None:
    """Declaring wheat infeasible on a tract where wheat visibly grows is the model losing."""
    tight = farm.Constraints(working_capital_paise=None, irrigations_available={"YAMUNA_PAR": 4})
    result = farm.crop_return(
        _option("Wheat"), _block("YAMUNA_PAR", irrigated=0.31), farm.CROP_ECONOMICS["Wheat"], tight
    )
    assert result is not None
    assert result.water_feasible, "a one-irrigation gap must not rule the crop out"
    assert any("discounted" in n for n in result.notes)


def test_a_large_water_shortfall_does_exclude() -> None:
    tight = farm.Constraints(working_capital_paise=None, irrigations_available={"YAMUNA_PAR": 4})
    result = farm.crop_return(
        _option("Paddy", season="KHARIF"),
        _block("YAMUNA_PAR", irrigated=0.31),
        farm.CROP_ECONOMICS["Paddy"],
        tight,
    )
    assert result is not None and not result.water_feasible


def test_the_crop_actually_planted_is_ranked_not_just_the_winner() -> None:
    """The more actionable half of the ranking, and it was being thrown away.

    An FPO with 99% of its area in one crop does not need to know which crop scores highest
    in the abstract — it needs to know where *its own* crop sits and by how much. Without
    this the Farm module's findings are all about crops nobody grows, so they can never meet
    the override quorum however strongly they point.
    """
    from agrivardhak.intelligence.contracts import ModuleInput

    output = farm.run(
        ModuleInput(
            organization_id=uuid.uuid4(),
            as_of=NOW,
            data={
                "blocks": [_block()],
                "options": [
                    _option("Mustard", 1500.0, 5900, 6100),
                    _option("Wheat", 4000.0, 2300, 2500),
                    _option("Paddy", 4350.0, 2000, 2200, season="KHARIF"),
                ],
                "planted_crop_by_tract": {"DOAB": "Paddy"},
                "constraints": farm.Constraints(working_capital_paise=None),
            },
        )
    )
    incumbent = [f for f in output.findings if f.key.startswith("underperforming_crop.")]
    assert incumbent, "the planted crop's rank must be reported"
    assert "actually planted here" in incumbent[0].statement


def test_the_incumbent_finding_admits_what_return_per_rupee_does_not_price() -> None:
    """Paddy is not grown only for margin, and a module that implied otherwise would mislead.

    Assured procurement, household food security and a labour calendar are real reasons this
    collective grows what it grows. None of them are in the cost model, and the finding says
    so rather than letting a 0.28-against-1.93 comparison stand as the whole story.
    """
    from agrivardhak.intelligence.contracts import ModuleInput

    output = farm.run(
        ModuleInput(
            organization_id=uuid.uuid4(),
            as_of=NOW,
            data={
                "blocks": [_block()],
                "options": [
                    _option("Mustard", 1500.0, 5900, 6100),
                    _option("Paddy", 4350.0, 2000, 2200, season="KHARIF"),
                ],
                "planted_crop_by_tract": {"DOAB": "Paddy"},
                "constraints": farm.Constraints(working_capital_paise=None),
            },
        )
    )
    incumbent = next(f for f in output.findings if f.key.startswith("underperforming_crop."))
    assumptions = " ".join(incumbent.assumptions).lower()
    assert "procurement" in assumptions
    assert "not the only reason" in assumptions


def test_the_leading_crop_is_not_reported_as_underperforming() -> None:
    """If the incumbent already wins, there is nothing to say and the module says nothing."""
    from agrivardhak.intelligence.contracts import ModuleInput

    output = farm.run(
        ModuleInput(
            organization_id=uuid.uuid4(),
            as_of=NOW,
            data={
                "blocks": [_block()],
                "options": [
                    _option("Mustard", 1500.0, 5900, 6100),
                    _option("Paddy", 4350.0, 2000, 2200, season="KHARIF"),
                ],
                "planted_crop_by_tract": {"DOAB": "Mustard"},
                "constraints": farm.Constraints(working_capital_paise=None),
            },
        )
    )
    assert not [f for f in output.findings if f.key.startswith("underperforming_crop.")]


def test_an_unpriced_option_is_absent_rather_than_guessed() -> None:
    unpriced = farm.CropOption(
        crop_name="Wheat",
        season="RABI",
        expected_yield_kg_per_ha=4000.0,
        price_low_paise_per_kg=None,
        price_high_paise_per_kg=None,
        price_evidence=None,
    )
    assert (
        farm.crop_return(
            unpriced,
            _block(),
            farm.CROP_ECONOMICS["Wheat"],
            farm.Constraints(working_capital_paise=None),
        )
        is None
    )


def test_a_plan_the_collective_cannot_fund_says_so() -> None:
    """A recommendation the FPO cannot pay for burns trust in everything else on the screen."""
    result = farm.crop_return(
        _option("Wheat"),
        _block(),
        farm.CROP_ECONOMICS["Wheat"],
        farm.Constraints(working_capital_paise=100_000),
    )
    affordable, required, note = farm.capital_feasible([result], _block().area_sqm, 100_000)
    assert not affordable
    assert required > 100_000
    assert note and "lakh" in note


def test_unknown_working_capital_is_flagged_not_assumed_unlimited() -> None:
    result = farm.crop_return(
        _option("Wheat"),
        _block(),
        farm.CROP_ECONOMICS["Wheat"],
        farm.Constraints(working_capital_paise=None),
    )
    _affordable, _required, note = farm.capital_feasible([result], _block().area_sqm, None)
    assert note and "not recorded" in note


# --------------------------------------------------------------------------- risk


def _climatology(p_heavy=0.17, years=30) -> risk.Climatology:
    windows = {
        f"{m:02d}{h}": risk.HazardWindow(
            key=f"{m:02d}{h}",
            years_observed=years,
            probability={
                "heavy_rain": p_heavy,
                "very_heavy_rain": 0.03,
                "frost": 0.0,
                "heat_stress": 0.0,
            },
        )
        for m in range(1, 13)
        for h in ("A", "B")
    }
    return risk.Climatology(tract="DOAB", windows=windows, evidence=_ref("external_record"))


def _seasonality(low_month=2, low=1000, high=1950) -> risk.PriceSeasonality:
    months = {
        m: risk.MonthlyPrice(
            month=m,
            median_paise_per_kg=low if m == low_month else high,
            median_arrivals_kg=Decimal("120000") if m == low_month else Decimal("30000"),
            samples=40,
        )
        for m in range(1, 13)
    }
    return risk.PriceSeasonality(
        crop_name="Potato", months=months, evidence=_ref("external_record")
    )


def _exposure(harvest=dt.date(2026, 2, 5)) -> risk.CropExposure:
    return risk.CropExposure(
        crop_name="Potato",
        farmer_ids=[uuid.uuid4() for _ in range(40)],
        crop_cycle_ids=[uuid.uuid4() for _ in range(40)],
        area_sqm=Decimal("2000000"),
        expected_kg=Decimal("500000"),
        harvest_from=harvest,
        harvest_to=harvest + dt.timedelta(days=10),
        tract="DOAB",
        evidence=[_ref()],
    )


def test_a_harvest_in_the_price_trough_is_named_with_what_it_costs() -> None:
    result = risk.price_trough_risk(_exposure(), _seasonality(), 50_000_000)
    assert result is not None
    finding, entry = result
    assert "trough" in finding.statement
    assert finding.affected.value_paise and finding.affected.value_paise > 0
    assert entry.domain == "MARKET"


def test_a_hazard_probability_is_stated_as_a_frequency_not_a_forecast() -> None:
    """climatology != forecast. Saying "it will rain" from a 30-year frequency is a lie."""
    results = risk.weather_hazard_risk(_exposure(), _climatology(0.40), 50_000_000, 1000)
    assert results
    finding, _entry = results[0]
    assert "of the last 30 years" in finding.statement
    assert any("not a forecast" in a for a in finding.assumptions)


def test_thirty_years_of_record_is_trusted_more_than_three() -> None:
    assert risk.climatology_confidence(30) > risk.climatology_confidence(3)
    assert risk.climatology_confidence(30) < 1.0, "reanalysis at a grid point is never certainty"


def test_a_hazard_below_the_reporting_threshold_is_not_raised_as_a_finding() -> None:
    assert risk.weather_hazard_risk(_exposure(), _climatology(0.02), 50_000_000, 1000) == []


def test_impact_is_relative_to_what_the_collective_can_absorb() -> None:
    """Six lakh is survivable for one collective and existential for another."""
    assert risk.impact_band(30_000_000, 100_000_000) == "HIGH"
    assert risk.impact_band(1_000_000, 100_000_000) == "LOW"


def test_unknown_working_capital_refuses_to_rank_rather_than_inventing_a_denominator() -> None:
    assert risk.impact_band(30_000_000, None) == "MEDIUM"


def test_concentration_is_reported_as_a_fact_not_an_instruction() -> None:
    """Whether to accept a concentration is a board decision.

    A module that turned an exposure into an instruction would be overstepping.
    """
    results = risk.concentration_risk([_exposure()], 50_000_000)
    assert results
    _finding, entry = results[0]
    assert "board decision" in (entry.mitigation or "")


def test_risks_we_cannot_size_are_named_rather_than_omitted() -> None:
    """NFR-301. A fabricated 0.7 is indistinguishable from a measured 0.7 once it is on a screen."""
    output = risk.run(
        ModuleInput(
            organization_id=uuid.uuid4(),
            as_of=NOW,
            data={"exposures": [_exposure()], "climatology": {"DOAB": _climatology()}},
        )
    )
    assert any("outbreak likelihood is not modelled" in d for d in output.degraded_inputs)
    assert any("policy" in d for d in output.degraded_inputs)


def test_a_multi_week_harvest_carries_more_exposure_than_a_fortnight() -> None:
    """Which is the whole reason to consider staggering a lift."""
    climate = _climatology(0.30)
    short = climate.over_span(dt.date(2026, 2, 1), dt.date(2026, 2, 10))
    long = climate.over_span(dt.date(2026, 2, 1), dt.date(2026, 3, 20))
    assert long["heavy_rain"] > short["heavy_rain"]
