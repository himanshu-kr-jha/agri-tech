"""Crop Health Intelligence — M11, FR-521…526, INV-8.

This is the module where being wrong has a cost measured in a farmer's money and in what
gets sprayed onto food and into groundwater. Three design choices follow from that, and
they are the whole module:

**1. It produces an action plan, not a label (FR-522).**
"Late blight" is not advice. The output is always a ladder — what to do today, what to
change in how the field is managed, a biological option, and only then a chemical *class*
with the instruction to read the label and ask a local agronomist. The ladder is ordered by
reversibility: a monitoring interval costs nothing and can be undone; a spray cannot.

**2. It refuses to guess (FR-524, SAF-02).**
When the top two candidates sit within ``diagnostic_margin``, no diagnosis is asserted. The
module says what it cannot tell apart, asks for the specific observation that would separate
them, and gives the action that is safe under *both* candidates. A confident wrong diagnosis
sends a farmer to buy the wrong chemical; an honest "I need a closer photo of the leaf
underside" costs a day.

**3. It never emits an unattributed product and dose (INV-8, SAF-03).**
Chemical guidance is a class — "a protectant contact fungicide", not a brand and a
millilitre count. Exact dosage is legal advice about a registered label, it varies by
formulation and state, and getting it wrong is a poisoning risk. That line is not a
limitation of this implementation to be lifted later; it is the safety floor.

Status of the knowledge base
----------------------------
``CONDITIONS`` below is **SYNTHETIC — DEMO ONLY**. The symptom-to-condition associations are
ordinary textbook plant pathology, but nothing here has yet been checked against a cited
authority (``seed/sources.md`` P1-P7 remain open). So every finding this module emits
carries the synthetic marker and its confidence is capped at
:data:`UNSOURCED_CONFIDENCE_CEILING`, which keeps it below the orchestrator's confidence
floor and therefore incapable of driving a recommendation on its own. When P1-P7 are filled
in, the ceiling lifts for the entries that gained a citation, one at a time.
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

MODULE = "crop_health_intelligence"
VERSION = "1.0.0"

#: No un-cited condition may be stated more confidently than this. Chosen to sit *below* the
#: orchestrator's default confidence floor (0.45) so an unsourced diagnosis cannot become a
#: recommendation without a human adding the citation first.
UNSOURCED_CONFIDENCE_CEILING = 0.42

#: FR-524 default. Two candidates closer than this are not distinguishable to us.
DEFAULT_DIAGNOSTIC_MARGIN = 0.15


#: The escalation ladder, in order. The order is the safety property: a recommendation may
#: never present a chemical step without the steps above it (FR-522).
LADDER = ("immediate", "cultural", "biological", "chemical", "monitoring")


@dataclass(frozen=True)
class Condition:
    """One thing that can be wrong with a crop.

    ``source`` is the whole point of the dataclass. ``None`` means nobody has checked this
    against an authority, and the module treats it accordingly rather than trusting it
    because it is written down.
    """

    key: str
    name: str
    crops: tuple[str, ...]
    #: symptom code -> how strongly it points here, 0..1
    symptoms: dict[str, float]
    #: Conditions favouring it. Weather is a multiplier on likelihood, not a symptom.
    favours_humidity_pct: tuple[float, float] | None = None
    favours_temp_c: tuple[float, float] | None = None
    spread: str = "MODERATE"
    #: The separating observation — what a field officer should look at to rule it in or out.
    distinguishing_check: str = ""
    immediate: str = ""
    cultural: tuple[str, ...] = ()
    biological: tuple[str, ...] = ()
    #: A CLASS, never a product. See INV-8.
    chemical_class: str | None = None
    monitoring_days: int = 7
    #: Citation key in seed/sources.md. None => unsourced => capped confidence + marker.
    source: str | None = None


#: Conditions for the demo crops. SYNTHETIC — DEMO ONLY pending seed/sources.md P1-P7.
CONDITIONS: tuple[Condition, ...] = (
    Condition(
        key="potato_late_blight",
        name="Late blight",
        crops=("Potato",),
        symptoms={
            "leaf_lesion_dark": 0.8,
            "leaf_margin_necrosis": 0.7,
            "white_growth_underside": 0.9,
            "rapid_spread": 0.7,
            "tuber_rot": 0.6,
        },
        favours_humidity_pct=(80.0, 100.0),
        favours_temp_c=(10.0, 22.0),
        spread="FAST",
        distinguishing_check=(
            "Look at the underside of a lesion margin early in the morning: late blight "
            "shows a fine white growth there, early blight does not."
        ),
        immediate=(
            "Walk the affected block today and mark it. Do not irrigate overhead while "
            "lesions are wet, and do not move equipment from the marked block to a clean one."
        ),
        cultural=(
            "Improve airflow: avoid dense canopy and evening irrigation.",
            "Remove and destroy affected haulm away from the field — not on the bund.",
            "Earth up well so tubers are not exposed to spores washing down.",
        ),
        biological=("Preventive biocontrol drench where the block is not yet symptomatic.",),
        chemical_class=(
            "A protectant contact fungicide on unaffected blocks, escalating to a systemic "
            "only if lesions are already established"
        ),
        monitoring_days=3,
        source=None,
    ),
    Condition(
        key="potato_early_blight",
        name="Early blight",
        crops=("Potato",),
        symptoms={
            "leaf_lesion_dark": 0.6,
            "concentric_rings": 0.9,
            "lower_leaves_first": 0.8,
            "leaf_margin_necrosis": 0.4,
        },
        favours_humidity_pct=(60.0, 90.0),
        favours_temp_c=(20.0, 30.0),
        spread="MODERATE",
        distinguishing_check=(
            "Early blight lesions carry concentric rings like a target and start on the "
            "oldest, lowest leaves. Late blight starts anywhere and spreads much faster."
        ),
        immediate="Mark the affected rows and check whether the lowest leaves went first.",
        cultural=(
            "Maintain nitrogen — early blight hits stressed, under-fed crops hardest.",
            "Rotate away from solanaceous crops on that plot next season.",
        ),
        biological=("Biocontrol foliar application at first sign, before lesions coalesce.",),
        chemical_class="A protectant contact fungicide",
        monitoring_days=7,
        source=None,
    ),
    Condition(
        key="wheat_yellow_rust",
        name="Yellow rust",
        crops=("Wheat",),
        symptoms={
            "yellow_stripes": 0.9,
            "powder_on_leaf": 0.8,
            "leaf_yellowing": 0.5,
            "rapid_spread": 0.6,
        },
        favours_humidity_pct=(70.0, 100.0),
        favours_temp_c=(8.0, 18.0),
        spread="FAST",
        distinguishing_check=(
            "Rub a leaf: yellow rust leaves yellow-orange powder on the finger, in stripes "
            "along the veins. Nutrient yellowing does not come off."
        ),
        immediate="Mark the patch and check neighbouring fields — rust arrives on the wind.",
        cultural=(
            "Note the variety: susceptibility differs sharply, and next season's seed choice "
            "is the cheapest control there is.",
            "Avoid excess nitrogen, which thickens the canopy and holds moisture.",
        ),
        biological=(),
        chemical_class="A triazole-group foliar fungicide at the label's stated growth stage",
        monitoring_days=5,
        source=None,
    ),
    Condition(
        key="nutrient_nitrogen_deficiency",
        name="Nitrogen deficiency",
        crops=("Potato", "Wheat", "Paddy", "Mustard"),
        symptoms={"leaf_yellowing": 0.8, "lower_leaves_first": 0.7, "stunted_growth": 0.6},
        spread="NONE",
        distinguishing_check=(
            "Deficiency yellowing is even across the leaf and starts on the oldest leaves; "
            "it has no lesion, no powder and no smell, and it does not spread to neighbours."
        ),
        immediate="Check the last fertiliser application date and the soil test if there is one.",
        cultural=(
            "Split the remaining nitrogen dose rather than applying it all at once.",
            "Where a legume was grown last season, expect to need less.",
        ),
        biological=("Biofertiliser where the soil test supports it.",),
        chemical_class=None,
        monitoring_days=10,
        source=None,
    ),
    Condition(
        key="paddy_bacterial_leaf_blight",
        name="Bacterial leaf blight",
        crops=("Paddy",),
        symptoms={
            "leaf_margin_necrosis": 0.8,
            "wavy_lesion_edge": 0.9,
            "leaf_yellowing": 0.4,
            "rapid_spread": 0.5,
        },
        favours_humidity_pct=(75.0, 100.0),
        favours_temp_c=(25.0, 34.0),
        spread="FAST",
        distinguishing_check=(
            "Lesions run from the leaf tip down the margin with a wavy edge, and a cut stem "
            "end in clear water gives a milky ooze. Fungal lesions do not ooze."
        ),
        immediate="Drain the field if standing water is deep; avoid moving through it when wet.",
        cultural=(
            "Avoid excess nitrogen.",
            "Do not clip seedling tips at transplanting — it is a direct entry wound.",
        ),
        biological=(),
        chemical_class=(
            "Bactericides are of limited use here and fungicides do nothing at all — this is "
            "a management problem, and a local agronomist should confirm before anything is "
            "bought"
        ),
        monitoring_days=5,
        source=None,
    ),
    Condition(
        key="water_stress",
        name="Water stress",
        crops=("Potato", "Wheat", "Paddy", "Mustard", "Guava"),
        symptoms={"wilting": 0.9, "leaf_curl": 0.6, "stunted_growth": 0.5},
        spread="NONE",
        distinguishing_check=(
            "Water-stressed plants recover overnight or after irrigation; a wilt caused by "
            "disease does not, and its stem is usually discoloured inside."
        ),
        immediate="Irrigate if water is available, then look again the next morning.",
        cultural=("Mulch to hold soil moisture.", "Irrigate early morning, not midday."),
        biological=(),
        chemical_class=None,
        monitoring_days=3,
        source=None,
    ),
)


# --------------------------------------------------------------------------- inputs


@dataclass(frozen=True)
class HealthObservation:
    """What a field officer or farmer actually reported about one cycle.

    ``symptoms`` are checklist codes, not free text. Free text would have to enter a model
    as instructions-adjacent content, and a symptom list is the one place we can keep
    untrusted input out of the reasoning path entirely (NFR-405).
    """

    cycle_id: uuid.UUID
    farmer_id: uuid.UUID
    plot_id: uuid.UUID
    crop_name: str
    observed_on: dt.date
    symptoms: tuple[str, ...]
    severity_pct: float | None
    affected_area_sqm: Decimal | None
    #: True when the symptom list came from an image classifier (FR-526): assistive only.
    from_image: bool = False
    health: ProvenancedValue | None = None
    evidence: list[EvidenceRef] = field(default_factory=list)
    tract: str | None = None
    village: str | None = None


@dataclass(frozen=True)
class WeatherContext:
    """Conditions over the days around the observation. Drives spread risk, not diagnosis."""

    humidity_pct: float | None
    temp_max_c: float | None
    temp_min_c: float | None
    rainfall_mm: float | None
    evidence: EvidenceRef | None = None


@dataclass(frozen=True)
class Candidate:
    condition: Condition
    likelihood: float
    matched: tuple[str, ...]
    weather_support: float


@dataclass(frozen=True)
class ActionPlan:
    """FR-522: the ladder. Chemical never appears without the rungs above it."""

    steps: list[dict[str, Any]]
    monitoring_days: int
    asserted_condition: str | None
    #: Populated when FR-524 fires: what to look at to separate the candidates.
    needs_to_distinguish: list[str] = field(default_factory=list)
    safe_under_all: bool = False


# --------------------------------------------------------------------------- computation


def candidates_for(
    observation: HealthObservation, weather: WeatherContext | None
) -> list[Candidate]:
    """Score conditions against the reported symptoms, then modulate by weather.

    Symptoms decide *which* conditions are in play; weather only adjusts how plausible each
    is. Doing it the other way round would let a humid week invent a disease nobody saw.
    """
    scored: list[Candidate] = []
    for condition in CONDITIONS:
        if observation.crop_name not in condition.crops:
            continue
        matched = tuple(s for s in observation.symptoms if s in condition.symptoms)
        if not matched:
            continue
        weight = sum(condition.symptoms[s] for s in matched)
        possible = sum(condition.symptoms.values())
        base = weight / possible if possible else 0.0
        # Unmatched reported symptoms count against a candidate: a condition that explains
        # three of five findings is a worse fit than one that explains three of three.
        coverage = len(matched) / max(1, len(observation.symptoms))
        support = _weather_support(condition, weather)
        scored.append(
            Candidate(
                condition=condition,
                likelihood=round(base * (0.6 + 0.4 * coverage) * support, 4),
                matched=matched,
                weather_support=support,
            )
        )
    total = sum(c.likelihood for c in scored)
    if total <= 0:
        return []
    normalised = [
        Candidate(
            condition=c.condition,
            likelihood=round(c.likelihood / total, 4),
            matched=c.matched,
            weather_support=c.weather_support,
        )
        for c in scored
    ]
    return sorted(normalised, key=lambda c: -c.likelihood)


def _weather_support(condition: Condition, weather: WeatherContext | None) -> float:
    """1.0 when weather is neutral or unknown. Never below 0.6 — weather rules nothing out.

    A disease outside its favoured range is less likely, not impossible, and a hard zero
    here would let one humidity reading erase a candidate a field officer is looking at.
    """
    if weather is None:
        return 1.0
    support = 1.0
    if condition.favours_humidity_pct and weather.humidity_pct is not None:
        low, high = condition.favours_humidity_pct
        support *= 1.15 if low <= weather.humidity_pct <= high else 0.8
    if condition.favours_temp_c and weather.temp_max_c is not None:
        low, high = condition.favours_temp_c
        mean = (
            (weather.temp_max_c + weather.temp_min_c) / 2
            if weather.temp_min_c is not None
            else weather.temp_max_c
        )
        support *= 1.15 if low <= mean <= high else 0.8
    return max(0.6, min(1.3, support))


def spread_risk(
    condition: Condition, weather: WeatherContext | None, severity_pct: float | None
) -> tuple[str, str]:
    """FR-521: severity is what is there now; spread risk is what happens next."""
    if condition.spread == "NONE":
        return "NONE", "This is not contagious — neighbouring plots are not at risk from it."
    favourable = _weather_support(condition, weather) > 1.0
    heavy = (severity_pct or 0) >= 25
    if condition.spread == "FAST" and favourable:
        return (
            "HIGH",
            "Conditions favour it and it moves fast — neighbouring plots should be walked "
            "within the monitoring interval, not at the next routine visit.",
        )
    if condition.spread == "FAST" or (favourable and heavy):
        return "MODERATE", "It can move; check adjacent plots on the next visit."
    return "LOW", "Spread is unlikely under current conditions."


def build_plan(
    candidates: list[Candidate], margin: float, severity_pct: float | None
) -> ActionPlan:
    """The ladder, and the refusal to guess.

    When the top two are within ``margin`` the plan is built from what the candidates
    *agree* on. In practice that means the cultural and monitoring steps survive and the
    chemical step does not — which is the correct outcome, because the two candidates
    usually need different chemistry and picking one on a coin-flip is how the wrong thing
    gets sprayed.
    """
    if not candidates:
        return ActionPlan(
            steps=[
                {
                    "rung": "immediate",
                    "action": "No condition matched the reported symptoms.",
                    "note": "Record a fuller symptom list or a clearer photo before acting.",
                }
            ],
            monitoring_days=7,
            asserted_condition=None,
            needs_to_distinguish=["A fuller symptom checklist from the field."],
        )

    top = candidates[0]
    runner_up = candidates[1] if len(candidates) > 1 else None
    ambiguous = runner_up is not None and (top.likelihood - runner_up.likelihood) < margin

    if ambiguous and runner_up is not None:
        shared_cultural = [
            step for step in top.condition.cultural if step in runner_up.condition.cultural
        ]
        steps: list[dict[str, Any]] = [
            {
                "rung": "immediate",
                "action": top.condition.immediate,
                "note": (
                    f"Safe whether this is {top.condition.name.lower()} or "
                    f"{runner_up.condition.name.lower()}."
                ),
            }
        ]
        steps.extend(
            {"rung": "cultural", "action": step, "note": "Safe under both candidates."}
            for step in (
                shared_cultural or ["Do not change the nutrient plan until this is settled."]
            )
        )
        steps.append(
            {
                "rung": "chemical",
                "action": "No chemical option is given.",
                "note": (
                    f"{top.condition.name} and {runner_up.condition.name} are within the "
                    f"diagnostic margin and need different treatment. Spraying for the "
                    f"wrong one costs money and can make the right one worse."
                ),
            }
        )
        soonest = min(top.condition.monitoring_days, runner_up.condition.monitoring_days)
        steps.append(
            {
                "rung": "monitoring",
                "action": f"Re-inspect within {soonest} days.",
                "note": "Sooner than either alone would need, because the diagnosis is open.",
            }
        )
        return ActionPlan(
            steps=steps,
            monitoring_days=soonest,
            asserted_condition=None,
            needs_to_distinguish=[
                c.condition.distinguishing_check
                for c in (top, runner_up)
                if c.condition.distinguishing_check
            ],
            safe_under_all=True,
        )

    condition = top.condition
    steps = [{"rung": "immediate", "action": condition.immediate, "note": ""}]
    steps.extend({"rung": "cultural", "action": step, "note": ""} for step in condition.cultural)
    steps.extend(
        {"rung": "biological", "action": step, "note": "Preferred where severity is still low."}
        for step in condition.biological
    )
    if condition.chemical_class:
        justified = (severity_pct or 0) >= 10 or condition.spread == "FAST"
        steps.append(
            {
                "rung": "chemical",
                "action": (
                    condition.chemical_class
                    if justified
                    else "Hold. Severity does not yet justify a spray."
                ),
                "note": (
                    "Class only. Read the product label for dose, waiting period and crop "
                    "registration, and confirm with a local agronomist before buying. This "
                    "system does not prescribe a product or a dose."
                ),
                "requires_human_confirmation": True,
            }
        )
    steps.append(
        {
            "rung": "monitoring",
            "action": f"Re-inspect in {condition.monitoring_days} days.",
            "note": "Sooner if the affected area grows.",
        }
    )
    return ActionPlan(
        steps=steps,
        monitoring_days=condition.monitoring_days,
        asserted_condition=condition.name,
    )


def cluster(observations: list[HealthObservation], within_days: int = 10) -> list[dict[str, Any]]:
    """FR-525: the same symptoms turning up near each other, near the same time.

    Clustering by village and symptom rather than by diagnosis on purpose — an outbreak is
    visible in the raw reports before anybody has agreed what it is, and waiting for a
    confident diagnosis is how you notice a week late.
    """
    buckets: dict[tuple[str, str, str], list[HealthObservation]] = {}
    for observation in observations:
        for symptom in observation.symptoms:
            place = observation.village or observation.tract or "unknown"
            key = (place, observation.crop_name, symptom)
            buckets.setdefault(key, []).append(observation)

    clusters: list[dict[str, Any]] = []
    for (place, crop, symptom), group in buckets.items():
        if len(group) < 3:
            continue
        dates = sorted(o.observed_on for o in group)
        if (dates[-1] - dates[0]).days > within_days:
            continue
        clusters.append(
            {
                "place": place,
                "crop": crop,
                "symptom": symptom,
                "reports": len(group),
                "first_seen": dates[0],
                "last_seen": dates[-1],
                "farmer_ids": sorted({o.farmer_id for o in group}, key=str),
                "cycle_ids": sorted({o.cycle_id for o in group}, key=str),
                "area_sqm": sum((o.affected_area_sqm or Decimal(0) for o in group), Decimal(0)),
            }
        )
    return sorted(clusters, key=lambda c: -c["reports"])


def confidence_for(candidates: list[Candidate], observation: HealthObservation) -> float:
    """Never above the unsourced ceiling, and lower still when the evidence is thin."""
    if not candidates:
        return 0.0
    top = candidates[0]
    base = top.likelihood
    # The ceiling is applied FIRST, then the observation-level penalties. Order matters:
    # clamping last made every unsourced diagnosis land on exactly the ceiling, which
    # silently erased the image penalty FR-526 requires — a photo-derived match and a
    # field-officer match came out identical.
    if top.condition.source is None:
        base = min(base, UNSOURCED_CONFIDENCE_CEILING)
    if len(observation.symptoms) < 2:
        base *= 0.7  # one symptom is a hint, not a diagnosis
    if observation.from_image:
        base *= 0.75  # FR-526: assistive signal, never the sole basis
    return round(max(0.0, min(1.0, base)), 3)


# --------------------------------------------------------------------------- module entry


def run(inputs: ModuleInput) -> ModuleOutput:
    data = inputs.data
    observations: list[HealthObservation] = data.get("observations") or []
    weather: dict[str, WeatherContext] = data.get("weather_by_tract") or {}
    margin: float = data.get("diagnostic_margin", DEFAULT_DIAGNOSTIC_MARGIN)

    findings: list[Finding] = []
    actions: list[ProposedAction] = []
    degraded: list[str] = [
        "Condition knowledge base is not yet cited to an authority: every diagnosis "
        f"here is capped at {UNSOURCED_CONFIDENCE_CEILING} confidence."
    ]

    if not observations:
        return ModuleOutput(
            module=MODULE,
            version=VERSION,
            degraded_inputs=[*degraded, "no crop-health observations reported"],
        )
    if not weather:
        degraded.append("no weather context — spread risk is assessed without conditions")

    unresolved = 0
    for observation in observations:
        context = weather.get(observation.tract or "")
        candidates = candidates_for(observation, context)
        if not candidates:
            continue
        plan = build_plan(candidates, margin, observation.severity_pct)
        confidence = confidence_for(candidates, observation)
        top = candidates[0]
        risk, risk_note = spread_risk(top.condition, context, observation.severity_pct)

        evidence = list(observation.evidence)
        if context and context.evidence:
            evidence.append(context.evidence)
        if not evidence:
            continue  # FR-804: a claim with no evidence does not get made

        affected = AffectedSet(
            farmer_ids=[observation.farmer_id],
            plot_ids=[observation.plot_id],
            crop_cycle_ids=[observation.cycle_id],
            area_sqm=observation.affected_area_sqm,
        )

        if plan.asserted_condition is None and len(candidates) > 1:
            unresolved += 1
            statement = (
                f"{observation.crop_name}: symptoms are consistent with both "
                f"{candidates[0].condition.name.lower()} ({candidates[0].likelihood:.0%}) and "
                f"{candidates[1].condition.name.lower()} ({candidates[1].likelihood:.0%}) — "
                f"too close to call. No diagnosis is asserted."
            )
            key = f"undetermined.{observation.crop_name.lower()}.{observation.cycle_id}"
        else:
            statement = (
                f"{observation.crop_name}: symptoms most consistent with "
                f"{top.condition.name.lower()} ({top.likelihood:.0%}); spread risk {risk}. "
                f"{risk_note}"
            )
            key = f"condition.{top.condition.key}.{observation.cycle_id}"

        findings.append(
            Finding(
                key=key,
                statement=statement,
                magnitude=(
                    Decimal(str(observation.severity_pct))
                    if observation.severity_pct is not None
                    else None
                ),
                unit="% severity" if observation.severity_pct is not None else None,
                confidence=confidence,
                evidence=evidence,
                assumptions=[
                    "Condition associations are unverified against a cited authority.",
                    "Weather adjusts likelihood; it never rules a condition in or out.",
                    *(
                        ["Symptoms came from an image classifier — assistive only (FR-526)."]
                        if observation.from_image
                        else []
                    ),
                ],
                affected=affected,
            )
        )
        actions.append(_plan_action(observation, plan, top, confidence, evidence, affected))

    for group in cluster(observations):
        first = next(o for o in observations if o.cycle_id in group["cycle_ids"])
        if not first.evidence:
            continue
        findings.append(
            Finding(
                key=f"outbreak.{group['crop'].lower()}.{group['symptom']}.{group['place']}",
                statement=(
                    f"{group['reports']} reports of '{group['symptom'].replace('_', ' ')}' in "
                    f"{group['crop']} around {group['place']} between "
                    f"{group['first_seen']:%d %b} and {group['last_seen']:%d %b} — a cluster, "
                    f"not scattered cases."
                ),
                magnitude=Decimal(group["reports"]),
                unit="reports",
                confidence=0.55,  # the clustering is arithmetic; what it means is not
                evidence=first.evidence[:3],
                assumptions=[
                    "Clustered on reported symptom, not on diagnosis — an outbreak is "
                    "visible in the reports before anyone agrees what it is.",
                    "Reporting is uneven: more reports may mean more field visits.",
                ],
                affected=AffectedSet(
                    farmer_ids=group["farmer_ids"],
                    crop_cycle_ids=group["cycle_ids"],
                    area_sqm=group["area_sqm"] or None,
                ),
            )
        )

    if unresolved:
        degraded.append(
            f"{unresolved} observations could not be resolved to a single condition and "
            "were given the action safe under all candidates (FR-524)"
        )

    return ModuleOutput(
        module=MODULE,
        version=VERSION,
        findings=findings,
        proposed_actions=actions,
        degraded_inputs=degraded,
    )


def _plan_action(
    observation: HealthObservation,
    plan: ActionPlan,
    top: Candidate,
    confidence: float,
    evidence: list[EvidenceRef],
    affected: AffectedSet,
) -> ProposedAction:
    title = (
        f"{observation.crop_name}: action plan for {plan.asserted_condition.lower()}"
        if plan.asserted_condition
        else f"{observation.crop_name}: hold and confirm before treating"
    )
    rationale = (
        "Ordered by reversibility — the cheap, undoable steps come first, and the chemical "
        "step is a class with a label caution, never a product and a dose."
        if plan.asserted_condition
        else (
            "The top two candidates are within the diagnostic margin, so no diagnosis is "
            "asserted. These steps are safe whichever it turns out to be, and the check "
            "that separates them is listed."
        )
    )
    return ProposedAction(
        key=f"crop_protection.{observation.cycle_id}",
        title=title,
        rationale=rationale,
        recommendation_type="CROP_PROTECTION",
        target_type="crop_cycle",
        target_id=observation.cycle_id,
        value_paise=None,
        value_unit=None,
        expected_impact={
            "metric": "affected area",
            "direction": "contain",
            "ladder": plan.steps,
            "monitoring_days": plan.monitoring_days,
            "needs_to_distinguish": plan.needs_to_distinguish,
            "safety": (
                "No product or dose is prescribed. Follow the label and consult a local "
                "agronomist (INV-8)."
            ),
        },
        risks=[
            "The knowledge base is unverified; treat this as a prompt to look, not an answer.",
            *(
                ["Acting on the wrong candidate can worsen the other one."]
                if plan.asserted_condition is None
                else []
            ),
        ],
        alternatives=["Call a local agronomist to the plot before doing anything."],
        confidence=confidence,
        evidence=evidence,
    )
