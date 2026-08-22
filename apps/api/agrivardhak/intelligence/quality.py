"""Quality Intelligence — crop health → expected quality → expected quantity → buyer matching.

The chain discovery asked for (D-16, FR-531…534). It is the module that lets an FPO know in
*September* what it will have to sell in *March* — which is the originating pain: *"FPO
doesn't know three months beforehand that 400 tonnes will be available, so it cannot secure
buyers, storage or logistics."*

Pure function (ARCHITECTURE §3). Everything arrives in ``ModuleInput``; ``as_of`` is passed
rather than read, so a replay reproduces the number exactly.

Three rules shape it:

* **A prediction is not a recommendation** (INV-6). This module emits claims about reality —
  expected tonnage, expected grade mix, expected window. Where it proposes an action it is
  because a *specific* cycle can still be saved, and the action is clearly separated.
* **Confidence is inherited, not invented.** A yield built on a three-month-old self-report
  cannot be more certain than that report. The weakest provenanced input caps the output.
* **Grade is a distribution, not a verdict.** Telling an FPO "Grade A" when 30% will come in
  B is worse than telling them the split, because they will have sold the whole lot as A.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from agrivardhak.intelligence.contracts import (
    AffectedSet,
    EvidenceRef,
    Finding,
    ModuleInput,
    ModuleOutput,
    ProposedAction,
    ProvenancedValue,
)

MODULE = "quality_intelligence"
VERSION = "1.0.0"

GRADES = ("A", "B", "C")

#: A cycle below this is counted as poorly evidenced and reported separately, rather than
#: being allowed to drag an otherwise well-observed aggregate down with it.
POORLY_EVIDENCED_BELOW = 0.45


# --------------------------------------------------------------------------- tunables


@dataclass(frozen=True)
class YieldModel:
    """How the factors combine. Configuration, and shown with every output.

    Deliberately multiplicative and shallow. A deeper agronomic model would be more accurate
    and far less defensible — every coefficient here can be pointed at, argued with, and
    replaced by a sourced value from `seed/sources.md` A1-A13 without touching the shape.
    """

    #: Crop health at 100% yields the variety's base. Below that, yield falls faster than
    #: health does — a crop at 50% health does not give 50% of the harvest.
    health_exponent: float = 1.4
    #: Multiplier when irrigation is assured vs rain-fed.
    irrigated_factor: float = 1.0
    rainfed_factor: float = 0.72
    #: Applied when the nutrient plan was not followed.
    nutrient_shortfall_factor: float = 0.85
    #: Applied per standard deviation of weather stress. Absent weather data means 1.0 and a
    #: recorded degradation, never an assumed-good season.
    stress_factor_per_sd: float = 0.08
    #: Grade A needs sustained health; these are the thresholds on the health trajectory.
    grade_a_health: float = 82.0
    grade_b_health: float = 65.0
    #: How much of a lot lands off its headline grade even in a good year.
    baseline_grade_spread: float = 0.18

    def as_dict(self) -> dict[str, float]:
        return {
            "health_exponent": self.health_exponent,
            "irrigated_factor": self.irrigated_factor,
            "rainfed_factor": self.rainfed_factor,
            "nutrient_shortfall_factor": self.nutrient_shortfall_factor,
            "stress_factor_per_sd": self.stress_factor_per_sd,
            "grade_a_health": self.grade_a_health,
            "grade_b_health": self.grade_b_health,
        }


# --------------------------------------------------------------------------- inputs


@dataclass(frozen=True)
class CycleInput:
    """One crop cycle, with its consequential values already provenance-resolved.

    ``health`` and ``water`` are :class:`ProvenancedValue` rather than floats precisely so
    that a bare number cannot enter the model without declaring where it came from (INV-3).
    """

    cycle_id: uuid.UUID
    crop_name: str
    variety_name: str
    farmer_id: uuid.UUID
    plot_id: uuid.UUID
    area_sqm: Decimal
    sowing_date: dt.date | None
    duration_days: int | None
    base_yield_kg_per_ha: float | None
    #: Tract multiplier — Vindhyan soils are shallower (seed/reference.py TRACTS).
    tract_factor: float = 1.0
    tract: str | None = None
    health: ProvenancedValue | None = None
    water_assured: bool | None = None
    nutrient_plan_followed: bool | None = None
    #: Standard deviations of weather stress over the cycle. None = no weather data.
    weather_stress_sd: float | None = None
    #: Grade the buyer contract or GI mark requires, if any.
    target_grade: str | None = None
    evidence: list[EvidenceRef] = field(default_factory=list)


# --------------------------------------------------------------------------- outputs


@dataclass(frozen=True)
class CyclePrediction:
    cycle_id: uuid.UUID
    crop_name: str
    expected_yield_kg: Decimal
    #: Band, not a point. ±1 sigma from the confidence in the inputs.
    yield_low_kg: Decimal
    yield_high_kg: Decimal
    grade_distribution: dict[str, float]
    headline_grade: str
    harvest_from: dt.date | None
    harvest_to: dt.date | None
    confidence: float
    factors: dict[str, Any]
    at_risk: bool
    risk_reason: str | None
    evidence: list[EvidenceRef]


# --------------------------------------------------------------------------- computation


def health_factor(health_pct: float | None, model: YieldModel) -> float:
    """Yield response to crop health.

    Superlinear: a crop at 50% health gives well under half a harvest, because the damage
    that shows as poor health is the damage that costs grain. Absent health data returns a
    neutral 1.0 — and the caller records the gap rather than assuming a healthy crop.
    """
    if health_pct is None:
        return 1.0
    ratio = max(0.0, min(1.0, health_pct / 100.0))
    return float(ratio**model.health_exponent)


def water_factor(assured: bool | None, model: YieldModel) -> float:
    if assured is None:
        return 1.0
    return model.irrigated_factor if assured else model.rainfed_factor


def nutrient_factor(followed: bool | None, model: YieldModel) -> float:
    if followed is None:
        return 1.0
    return 1.0 if followed else model.nutrient_shortfall_factor


def stress_factor(stress_sd: float | None, model: YieldModel) -> float:
    if stress_sd is None:
        return 1.0
    return max(0.4, 1.0 - abs(stress_sd) * model.stress_factor_per_sd)


def expected_yield_kg(cycle: CycleInput, model: YieldModel) -> tuple[Decimal, dict[str, Any]]:
    """Base yield scaled by everything we know, with the factors returned.

    Returns zero and an explicit reason when the variety has no yield coefficient — a
    fabricated default would silently become tonnage the FPO plans against.
    """
    if not cycle.base_yield_kg_per_ha or cycle.base_yield_kg_per_ha <= 0:
        return Decimal("0"), {"unavailable": "no base yield coefficient for this variety"}

    area_ha = float(cycle.area_sqm) / 10_000.0
    health_pct = float(cycle.health.value) if cycle.health and cycle.health.value else None

    factors = {
        "base_yield_kg_per_ha": cycle.base_yield_kg_per_ha,
        "area_ha": round(area_ha, 4),
        "health": round(health_factor(health_pct, model), 4),
        "water": round(water_factor(cycle.water_assured, model), 4),
        "nutrient": round(nutrient_factor(cycle.nutrient_plan_followed, model), 4),
        "stress": round(stress_factor(cycle.weather_stress_sd, model), 4),
        "tract": round(cycle.tract_factor, 4),
    }
    total = (
        cycle.base_yield_kg_per_ha
        * area_ha
        * factors["health"]
        * factors["water"]
        * factors["nutrient"]
        * factors["stress"]
        * factors["tract"]
    )
    return Decimal(str(round(total, 3))), factors


def grade_distribution(
    cycle: CycleInput, model: YieldModel, confidence: float
) -> tuple[dict[str, float], str]:
    """Expected split across grades, and the grade that dominates it.

    A distribution rather than a verdict (FR-531). An FPO told "Grade A" that then finds 30%
    graded B has already sold the whole lot as A, and eats the difference at weighbridge.

    Lower confidence widens the spread: when we are unsure about health, we are unsure about
    grade, and the honest output is a flatter distribution rather than a confident one.
    """
    health = float(cycle.health.value) if cycle.health and cycle.health.value else None
    if health is None:
        # No health signal: report a wide, uninformative split rather than guessing A.
        return {"A": 0.34, "B": 0.40, "C": 0.26}, "B"

    if health >= model.grade_a_health:
        centre = "A"
    elif health >= model.grade_b_health:
        centre = "B"
    else:
        centre = "C"

    spread = model.baseline_grade_spread + (1.0 - confidence) * 0.35
    spread = min(0.6, spread)
    index = GRADES.index(centre)

    weights = {}
    for i, grade in enumerate(GRADES):
        distance = abs(i - index)
        weights[grade] = max(0.0, 1.0 - distance * (1.0 - spread) - distance * 0.15)
    total = sum(weights.values()) or 1.0
    dist = {g: round(w / total, 3) for g, w in weights.items()}
    return dist, max(dist, key=lambda g: dist[g])


def harvest_window(cycle: CycleInput) -> tuple[dt.date | None, dt.date | None]:
    """Sowing plus variety duration, widened by uncertainty about the season.

    A window rather than a date: the FPO needs to book a cold store and a buyer against a
    range, and a single date implies a precision no one has.
    """
    if cycle.sowing_date is None or not cycle.duration_days:
        return None, None
    centre = cycle.sowing_date + dt.timedelta(days=cycle.duration_days)
    slack = max(5, round(cycle.duration_days * 0.06))
    return centre - dt.timedelta(days=slack), centre + dt.timedelta(days=slack)


def prediction_confidence(cycle: CycleInput) -> tuple[float, list[str]]:
    """Confidence in the prediction, inherited from the weakest input.

    This is the point at which the provenance layer pays for itself. A yield built on a
    stale self-report is not as good as one built on a field-officer reading from Tuesday,
    and the number that reaches the CEO has to say so.
    """
    gaps: list[str] = []
    confidence = 0.85

    if cycle.health is None:
        confidence -= 0.30
        gaps.append("no crop-health observation")
    else:
        # Never exceed the confidence of the observation the prediction rests on.
        confidence = min(confidence, cycle.health.confidence)
        if cycle.health.is_stale:
            confidence -= 0.10
            gaps.append("crop-health reading is stale")
        if cycle.health.has_open_discrepancy:
            confidence -= 0.10
            gaps.append("crop-health value is disputed")

    if cycle.weather_stress_sd is None:
        confidence -= 0.08
        gaps.append("no weather data for the cycle")
    if cycle.water_assured is None:
        confidence -= 0.05
        gaps.append("irrigation status unknown")
    if not cycle.base_yield_kg_per_ha:
        confidence = 0.0
        gaps.append("no base yield coefficient")

    return max(0.0, min(0.95, confidence)), gaps


def predict_cycle(cycle: CycleInput, model: YieldModel) -> CyclePrediction:
    confidence, gaps = prediction_confidence(cycle)
    yield_kg, factors = expected_yield_kg(cycle, model)
    dist, headline = grade_distribution(cycle, model, confidence)
    start, end = harvest_window(cycle)

    # The band widens as confidence falls — an uncertain prediction that reports a narrow
    # range is worse than useless, because it will be planned against.
    band = float(yield_kg) * (0.10 + (1.0 - confidence) * 0.45)

    at_risk, reason = _assess_risk(cycle, dist, model)

    factors["gaps"] = gaps
    factors["model"] = model.as_dict()

    return CyclePrediction(
        cycle_id=cycle.cycle_id,
        crop_name=cycle.crop_name,
        expected_yield_kg=yield_kg,
        yield_low_kg=Decimal(str(round(max(0.0, float(yield_kg) - band), 3))),
        yield_high_kg=Decimal(str(round(float(yield_kg) + band, 3))),
        grade_distribution=dist,
        headline_grade=headline,
        harvest_from=start,
        harvest_to=end,
        confidence=confidence,
        factors=factors,
        at_risk=at_risk,
        risk_reason=reason,
        evidence=cycle.evidence or ([cycle.health.evidence] if cycle.health else []),
    )


def _assess_risk(
    cycle: CycleInput, dist: dict[str, float], model: YieldModel
) -> tuple[bool, str | None]:
    """FR-533: cycles at risk of falling a grade, while there is still time to act.

    Only flagged when there is a *target* to fall short of and the harvest has not happened.
    Flagging a cycle nobody contracted for produces noise, and noise trains people to ignore
    the alert that matters.
    """
    if cycle.target_grade is None:
        return False, None
    target_index = GRADES.index(cycle.target_grade) if cycle.target_grade in GRADES else 0
    shortfall = sum(p for i, g in enumerate(GRADES) if i > target_index for p in [dist[g]])
    if shortfall < 0.30:
        return False, None

    health = float(cycle.health.value) if cycle.health and cycle.health.value else None
    if health is not None and health < model.grade_a_health:
        return True, (
            f"{shortfall:.0%} of this cycle is tracking below the required grade "
            f"{cycle.target_grade}; crop health is {health:.0f}%."
        )
    return True, (
        f"{shortfall:.0%} of this cycle is tracking below the required grade {cycle.target_grade}."
    )


# --------------------------------------------------------------------------- aggregation


def aggregate(predictions: list[CyclePrediction]) -> dict[str, dict[str, Any]]:
    """FR-532: roll cycles up to the organization view the CEO actually asks for.

    **Aggregate confidence is a tonnage-weighted mean, not the minimum.** Weakest-link is the
    right rule for a single claim — a chain built on one stale reading is only as good as that
    reading. It is the wrong rule for a rollup: a 1,900-tonne forecast assembled from 1,282
    independently observed cycles is not made worthless by one plot nobody visited last month.
    Using min() here reported 0.00 confidence on the whole forecast, which is both wrong and
    useless — it tells the CEO nothing about where the uncertainty actually sits.

    So the weak evidence is reported *separately* instead: ``poorly_evidenced_cycles`` and
    ``weakest_confidence`` are carried alongside, letting the UI say "1,932 t at 62%, though
    340 cycles have stale health readings" — which is the sentence a CEO can act on.
    """
    by_crop: dict[str, dict[str, Any]] = {}
    for prediction in predictions:
        bucket = by_crop.setdefault(
            prediction.crop_name,
            {
                "cycles": 0,
                "expected_kg": Decimal("0"),
                "low_kg": Decimal("0"),
                "high_kg": Decimal("0"),
                "grade_kg": dict.fromkeys(GRADES, Decimal("0")),
                "harvest_from": None,
                "harvest_to": None,
                "at_risk_cycles": 0,
                "confidence": 0.0,
                "weakest_confidence": 1.0,
                "poorly_evidenced_cycles": 0,
                "_confidence_weight": Decimal("0"),
                "_confidence_sum": Decimal("0"),
            },
        )
        bucket["cycles"] += 1
        bucket["expected_kg"] += prediction.expected_yield_kg
        bucket["low_kg"] += prediction.yield_low_kg
        bucket["high_kg"] += prediction.yield_high_kg
        for grade, share in prediction.grade_distribution.items():
            bucket["grade_kg"][grade] += prediction.expected_yield_kg * Decimal(str(share))
        if prediction.at_risk:
            bucket["at_risk_cycles"] += 1
        bucket["weakest_confidence"] = min(bucket["weakest_confidence"], prediction.confidence)
        if prediction.confidence < POORLY_EVIDENCED_BELOW:
            bucket["poorly_evidenced_cycles"] += 1
        # Weight by tonnage: a big cycle's evidence matters more to the total than a small
        # one's, because it is contributing more of the number being reported.
        weight = prediction.expected_yield_kg
        bucket["_confidence_weight"] += weight
        bucket["_confidence_sum"] += weight * Decimal(str(prediction.confidence))
        if prediction.harvest_from:
            current = bucket["harvest_from"]
            bucket["harvest_from"] = (
                prediction.harvest_from
                if current is None
                else min(current, prediction.harvest_from)
            )
        if prediction.harvest_to:
            current = bucket["harvest_to"]
            bucket["harvest_to"] = (
                prediction.harvest_to if current is None else max(current, prediction.harvest_to)
            )

    for bucket in by_crop.values():
        weight = bucket.pop("_confidence_weight")
        total = bucket.pop("_confidence_sum")
        bucket["confidence"] = round(float(total / weight), 4) if weight > 0 else 0.0
    return by_crop


# --------------------------------------------------------------------------- learning


def prediction_error(predicted_kg: Decimal, actual_kg: Decimal) -> dict[str, float]:
    """FR-534: predicted vs actual, the signal that makes this a learning system.

    Reported as both absolute and relative error, because the two say different things: a
    500 kg miss on a smallholding is a bad model, on a 5,000-tonne lot it is noise.
    """
    predicted, actual = float(predicted_kg), float(actual_kg)
    absolute = predicted - actual
    return {
        "predicted_kg": predicted,
        "actual_kg": actual,
        "error_kg": round(absolute, 3),
        "error_pct": round(absolute / actual * 100, 2) if actual else 0.0,
        "abs_error_pct": round(abs(absolute) / actual * 100, 2) if actual else 0.0,
    }


# --------------------------------------------------------------------------- module entry


def run(inputs: ModuleInput) -> ModuleOutput:
    """Predict yield, grade and harvest window per cycle, then aggregate."""
    data = inputs.data
    model: YieldModel = data.get("model") or YieldModel()
    cycles: list[CycleInput] = data.get("cycles") or []

    findings: list[Finding] = []
    actions: list[ProposedAction] = []
    degraded: list[str] = []

    if not cycles:
        return ModuleOutput(
            module=MODULE, version=VERSION, degraded_inputs=["no active crop cycles"]
        )

    predictions = [predict_cycle(cycle, model) for cycle in cycles]
    usable = [p for p in predictions if p.expected_yield_kg > 0]

    missing_health = sum(1 for c in cycles if c.health is None)
    if missing_health:
        degraded.append(f"{missing_health} of {len(cycles)} cycles have no crop-health observation")
    if all(c.weather_stress_sd is None for c in cycles):
        degraded.append("no weather data — stress factor not applied")
    if len(usable) < len(predictions):
        degraded.append(f"{len(predictions) - len(usable)} cycles lack a yield coefficient")

    cycle_by_id = {c.cycle_id: c for c in cycles}

    for crop_name, bucket in aggregate(usable).items():
        evidence = _sample_evidence(usable, crop_name, inputs.as_of)

        window = ""
        if bucket["harvest_from"] and bucket["harvest_to"]:
            window = f" between {bucket['harvest_from']:%d %b} and {bucket['harvest_to']:%d %b}"
        grade_kg = bucket["grade_kg"]
        grade_text = ", ".join(
            f"Grade {g} {float(grade_kg[g]) / 1000:,.0f} t" for g in GRADES if grade_kg[g] > 0
        )

        findings.append(
            Finding(
                key=f"expected_production.{crop_name.lower()}",
                statement=(
                    f"{crop_name}: expected {float(bucket['expected_kg']) / 1000:,.0f} t "
                    f"(range {float(bucket['low_kg']) / 1000:,.0f} to "
                    f"{float(bucket['high_kg']) / 1000:,.0f} t) from {bucket['cycles']} cycles"
                    f"{window}."
                ),
                magnitude=bucket["expected_kg"],
                unit="kg",
                confidence=bucket["confidence"],
                evidence=evidence,
                assumptions=[
                    "Yield coefficients are unsourced placeholders (seed/sources.md A1-A5).",
                    "Confidence is a tonnage-weighted mean across cycles; "
                    f"{bucket['poorly_evidenced_cycles']} of {bucket['cycles']} cycles are "
                    "poorly evidenced and are reported separately rather than averaged away.",
                ],
                affected=AffectedSet(
                    crop_cycle_ids=[p.cycle_id for p in usable if p.crop_name == crop_name],
                    quantity_kg=bucket["expected_kg"],
                ),
            )
        )

        if grade_text:
            findings.append(
                Finding(
                    key=f"expected_quality.{crop_name.lower()}",
                    statement=f"{crop_name} expected grade mix: {grade_text}.",
                    confidence=bucket["confidence"],
                    evidence=evidence,
                    assumptions=[
                        "A distribution, not a verdict — selling the whole lot at the "
                        "headline grade would leave the difference at the weighbridge."
                    ],
                    affected=AffectedSet(quantity_kg=bucket["expected_kg"]),
                )
            )

    weak = [p for p in usable if p.confidence < POORLY_EVIDENCED_BELOW]
    if weak:
        findings.append(
            Finding(
                key="evidence_gap.crop_health",
                statement=(
                    f"{len(weak)} of {len(usable)} cycles rest on crop-health readings too old "
                    f"or too weakly sourced to support a confident forecast. A field visit to "
                    f"these would raise the production estimate's confidence more than any "
                    f"other action."
                ),
                magnitude=Decimal(len(weak)),
                unit="cycles",
                confidence=0.90,
                # Cites the cycles, not the observations — the observations are what is
                # missing.
                evidence=[_cycle_ref(p, inputs.as_of) for p in weak[:5]],
                affected=AffectedSet(crop_cycle_ids=[p.cycle_id for p in weak][:200]),
            )
        )

    at_risk = [p for p in usable if p.at_risk]
    if at_risk:
        affected_farmers = [
            cycle_by_id[p.cycle_id].farmer_id for p in at_risk if p.cycle_id in cycle_by_id
        ]
        exposure = sum((p.expected_yield_kg for p in at_risk), Decimal("0"))
        findings.append(
            Finding(
                key="quality_at_risk",
                statement=(
                    f"{len(at_risk)} crop cycles carrying {float(exposure) / 1000:,.0f} t are "
                    f"tracking below their required grade, with the harvest still ahead."
                ),
                magnitude=Decimal(len(at_risk)),
                unit="cycles",
                confidence=min(p.confidence for p in at_risk),
                evidence=_flatten_evidence(at_risk, inputs.as_of),
                affected=AffectedSet(
                    farmer_ids=affected_farmers,
                    crop_cycle_ids=[p.cycle_id for p in at_risk],
                    quantity_kg=exposure,
                ),
            )
        )
        actions.append(
            ProposedAction(
                key="quality.intervene",
                title=(f"Field-verify {len(at_risk)} cycles at risk of a grade drop"),
                rationale=(
                    "These cycles are tracking below the grade their buyer or GI mark "
                    "requires, and the harvest has not happened yet — so the loss is still "
                    "preventable. Verify in the field before acting: the prediction rests on "
                    "crop-health readings whose confidence is "
                    f"{min(p.confidence for p in at_risk):.0%}.\n"
                    + "\n".join(f"- {p.risk_reason}" for p in at_risk[:5])
                ),
                recommendation_type="RISK_MITIGATION",
                target_type="organization",
                target_id=inputs.organization_id,
                expected_impact={
                    "cycles_at_risk": len(at_risk),
                    "tonnes_exposed": round(float(exposure) / 1000, 1),
                    "by_crop": _risk_by_crop(at_risk),
                },
                risks=[
                    "Grade prediction is derived from crop health, not from a laboratory "
                    "assessment. Treat it as a prompt to inspect, not as a result."
                ],
                confidence=min(p.confidence for p in at_risk),
                evidence=_flatten_evidence(at_risk, inputs.as_of),
            )
        )

    return ModuleOutput(
        module=MODULE,
        version=VERSION,
        findings=findings,
        proposed_actions=actions,
        degraded_inputs=degraded,
    )


def _cycle_ref(prediction: CyclePrediction, as_of: dt.datetime) -> EvidenceRef:
    """The crop cycle itself as evidence.

    Needed for claims *about missing evidence*: a finding that says "these cycles have no
    recent health reading" cannot cite the readings, because that is the point. It cites the
    cycles, which are real rows a reader can open.
    """
    return EvidenceRef(
        kind="domain_row",
        id=prediction.cycle_id,
        label=f"{prediction.crop_name} cycle (confidence {prediction.confidence:.0%})",
        as_of=as_of,
    )


def _sample_evidence(
    predictions: list[CyclePrediction], crop_name: str, as_of: dt.datetime
) -> list[EvidenceRef]:
    """A few representative refs — enough to audit, not so many the packet drowns.

    Falls back to citing the cycles when none of them carry an observation. A crop must not
    vanish from the production forecast merely because nobody visited it: an FPO reading a
    forecast that omits its paddy would conclude it has no paddy.
    """
    refs: list[EvidenceRef] = []
    matching = [p for p in predictions if p.crop_name == crop_name]
    for prediction in matching:
        refs.extend(prediction.evidence)
        if len(refs) >= 3:
            break
    if not refs:
        refs = [_cycle_ref(p, as_of) for p in matching[:3]]
    return refs[:3]


def _flatten_evidence(predictions: list[CyclePrediction], as_of: dt.datetime) -> list[EvidenceRef]:
    refs: list[EvidenceRef] = []
    for prediction in predictions:
        refs.extend(prediction.evidence)
        if len(refs) >= 5:
            break
    if not refs:
        refs = [_cycle_ref(p, as_of) for p in predictions[:5]]
    return refs[:5]


def _risk_by_crop(predictions: list[CyclePrediction]) -> dict[str, int]:
    out: dict[str, int] = {}
    for prediction in predictions:
        out[prediction.crop_name] = out.get(prediction.crop_name, 0) + 1
    return out
