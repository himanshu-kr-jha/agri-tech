"""Crop Health Intelligence — M11, FR-521…526, INV-8, SAF-02, SAF-03.

The chemical safety floor is the reason this file exists. Being wrong here costs a farmer
money and puts something on food, so these tests are written to fail if anyone ever makes
the module more helpful in the specific way that makes it dangerous.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from agrivardhak.intelligence import crop_health
from agrivardhak.intelligence.contracts import EvidenceRef, ModuleInput

NOW = dt.datetime(2026, 1, 20, tzinfo=dt.UTC)


def _ref() -> EvidenceRef:
    return EvidenceRef(kind="observation", id=uuid.uuid4(), label="field report", as_of=NOW)


def _observation(crop: str, symptoms: tuple[str, ...], **kw) -> crop_health.HealthObservation:
    return crop_health.HealthObservation(
        cycle_id=kw.pop("cycle_id", uuid.uuid4()),
        farmer_id=kw.pop("farmer_id", uuid.uuid4()),
        plot_id=uuid.uuid4(),
        crop_name=crop,
        observed_on=kw.pop("observed_on", NOW.date()),
        symptoms=symptoms,
        severity_pct=kw.pop("severity_pct", 20.0),
        affected_area_sqm=Decimal("4000"),
        evidence=[_ref()],
        **kw,
    )


def _run(observations, weather=None) -> object:
    return crop_health.run(
        ModuleInput(
            organization_id=uuid.uuid4(),
            as_of=NOW,
            data={"observations": observations, "weather_by_tract": weather or {}},
        )
    )


# --------------------------------------------------------------------------- INV-8


def test_no_product_or_dose_is_ever_prescribed() -> None:
    """INV-8 / SAF-03, the safety floor.

    A product name and a millilitre count is legal advice about a registered label. It
    varies by formulation, crop and state, and getting it wrong is a poisoning risk. The
    module gives a *class* and tells the reader to check the label and ask an agronomist.
    """
    output = _run([_observation("Potato", ("leaf_lesion_dark", "white_growth_underside"))])
    chemical_steps = [
        step
        for action in output.proposed_actions
        for step in action.expected_impact.get("ladder", [])
        if step["rung"] == "chemical"
    ]
    assert chemical_steps, "a potato late-blight plan should reach the chemical rung"
    for step in chemical_steps:
        text = f"{step['action']} {step.get('note', '')}".lower()
        for banned in ("ml/", " ml ", "gram per", "g/litre", "g/l ", "%ec", " sc ", "kg/ha of"):
            assert banned not in text, f"a dose slipped into crop-protection output: {step}"
        assert "label" in text and "agronomist" in text


def test_the_chemical_rung_never_appears_without_the_rungs_above_it() -> None:
    """FR-522. The ladder is ordered by reversibility: monitoring can be undone, a spray cannot."""
    output = _run([_observation("Wheat", ("yellow_stripes", "powder_on_leaf"))])
    for action in output.proposed_actions:
        rungs = [s["rung"] for s in action.expected_impact.get("ladder", [])]
        if "chemical" in rungs:
            assert "immediate" in rungs
            assert "cultural" in rungs
            assert rungs.index("chemical") > rungs.index("cultural")


def test_a_chemical_step_is_flagged_as_needing_human_confirmation() -> None:
    output = _run([_observation("Potato", ("leaf_lesion_dark", "white_growth_underside"))])
    steps = [
        s
        for a in output.proposed_actions
        for s in a.expected_impact.get("ladder", [])
        if s["rung"] == "chemical"
    ]
    assert all(s.get("requires_human_confirmation") for s in steps)


def test_low_severity_holds_the_spray_rather_than_recommending_it() -> None:
    """FR-523: escalate to chemical only where severity and spread risk justify it."""
    mild = _observation("Potato", ("concentric_rings", "lower_leaves_first"), severity_pct=2.0)
    output = _run([mild])
    chemical = [
        s
        for a in output.proposed_actions
        for s in a.expected_impact.get("ladder", [])
        if s["rung"] == "chemical"
    ]
    assert any("hold" in s["action"].lower() for s in chemical)


# --------------------------------------------------------------------------- SAF-02


def test_two_close_candidates_produce_no_diagnosis() -> None:
    """FR-524 / SAF-02. An honest "I cannot tell" costs a day; a confident wrong one costs a crop.

    These symptoms fit both blights. The module must decline to name one, say what would
    separate them, and give the action that is safe under either.
    """
    ambiguous = _observation("Potato", ("leaf_lesion_dark", "leaf_margin_necrosis"))
    plan = crop_health.build_plan(
        crop_health.candidates_for(ambiguous, None),
        crop_health.DEFAULT_DIAGNOSTIC_MARGIN,
        ambiguous.severity_pct,
    )
    assert plan.asserted_condition is None
    assert plan.needs_to_distinguish, "it must say what observation would settle it"
    assert plan.safe_under_all


def test_an_undetermined_case_gives_no_chemical_option_at_all() -> None:
    """The two candidates need different treatment; picking one on a coin flip is the harm."""
    ambiguous = _observation("Potato", ("leaf_lesion_dark", "leaf_margin_necrosis"))
    plan = crop_health.build_plan(
        crop_health.candidates_for(ambiguous, None),
        crop_health.DEFAULT_DIAGNOSTIC_MARGIN,
        ambiguous.severity_pct,
    )
    chemical = [s for s in plan.steps if s["rung"] == "chemical"]
    assert chemical and "no chemical option" in chemical[0]["action"].lower()


def test_an_undetermined_case_is_re_inspected_sooner_not_later() -> None:
    ambiguous = _observation("Potato", ("leaf_lesion_dark", "leaf_margin_necrosis"))
    clear = _observation("Potato", ("concentric_rings", "lower_leaves_first"))
    open_plan = crop_health.build_plan(
        crop_health.candidates_for(ambiguous, None), crop_health.DEFAULT_DIAGNOSTIC_MARGIN, 20.0
    )
    settled = crop_health.build_plan(
        crop_health.candidates_for(clear, None), crop_health.DEFAULT_DIAGNOSTIC_MARGIN, 20.0
    )
    assert open_plan.monitoring_days <= settled.monitoring_days


# --------------------------------------------------------------------------- honesty


def test_an_unsourced_diagnosis_cannot_reach_the_confidence_floor() -> None:
    """The knowledge base is unverified, so it must be structurally unable to drive a decision.

    Capped below the orchestrator's floor, which means a diagnosis from here cannot become a
    recommendation until someone adds the citation (seed/sources.md P1-P7).
    """
    output = _run([_observation("Potato", ("leaf_lesion_dark", "white_growth_underside"))])
    assert all(
        f.confidence <= crop_health.UNSOURCED_CONFIDENCE_CEILING
        for f in output.findings
        if f.key.startswith("condition.")
    )
    assert crop_health.UNSOURCED_CONFIDENCE_CEILING < 0.45


def test_every_finding_is_labelled_synthetic() -> None:
    """SAF-07 / C-2. An unverified association must never present itself as established."""
    output = _run([_observation("Paddy", ("leaf_margin_necrosis", "wavy_lesion_edge"))])
    diagnostic = [f for f in output.findings if not f.key.startswith("outbreak.")]
    assert diagnostic
    for finding in diagnostic:
        assert crop_health.SYNTHETIC_MARKER in finding.statement


def test_an_image_derived_symptom_list_lowers_confidence() -> None:
    """FR-526: image classification is an assistive signal, never the sole basis."""
    seen = _observation("Wheat", ("yellow_stripes", "powder_on_leaf"))
    from_photo = _observation("Wheat", ("yellow_stripes", "powder_on_leaf"), from_image=True)
    assert crop_health.confidence_for(
        crop_health.candidates_for(from_photo, None), from_photo
    ) < crop_health.confidence_for(crop_health.candidates_for(seen, None), seen)


def test_weather_adjusts_likelihood_but_never_rules_a_condition_out() -> None:
    """One humidity reading must not erase a candidate a field officer is looking at."""
    dry = crop_health.WeatherContext(
        humidity_pct=30.0, temp_max_c=32.0, temp_min_c=18.0, rainfall_mm=0.0
    )
    blight = next(c for c in crop_health.CONDITIONS if c.key == "potato_late_blight")
    assert crop_health._weather_support(blight, dry) >= 0.6


def test_a_non_contagious_condition_is_not_reported_as_a_spread_risk() -> None:
    deficiency = next(c for c in crop_health.CONDITIONS if c.key == "nutrient_nitrogen_deficiency")
    risk, note = crop_health.spread_risk(deficiency, None, 30.0)
    assert risk == "NONE"
    assert "not contagious" in note


# --------------------------------------------------------------------------- FR-525


def test_clustered_reports_raise_an_outbreak_signal() -> None:
    """FR-525. Clustered on symptom, not diagnosis — an outbreak is visible before anyone agrees."""
    reports = [
        _observation("Potato", ("leaf_lesion_dark", "rapid_spread"), village="Kaurihar")
        for _ in range(4)
    ]
    reports = [
        crop_health.HealthObservation(**{**r.__dict__, "village": "Kaurihar"}) for r in reports
    ]
    clusters = crop_health.cluster(reports)
    assert clusters
    assert clusters[0]["reports"] >= 3
    assert clusters[0]["place"] == "Kaurihar"


def test_scattered_reports_do_not_raise_an_outbreak() -> None:
    """A signal that fires on ordinary background noise is a signal nobody will read."""
    scattered = [
        _observation("Potato", ("leaf_lesion_dark",), village=f"Village {i}") for i in range(6)
    ]
    scattered = [
        crop_health.HealthObservation(**{**r.__dict__, "village": f"Village {i}"})
        for i, r in enumerate(scattered)
    ]
    assert crop_health.cluster(scattered) == []


def test_no_observations_returns_a_stated_gap_not_an_all_clear() -> None:
    """NFR-301: "nothing reported" and "nothing wrong" are different answers."""
    output = _run([])
    assert output.findings == []
    assert any("no crop-health observations" in d for d in output.degraded_inputs)
