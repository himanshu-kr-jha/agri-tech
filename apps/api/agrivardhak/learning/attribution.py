"""Outcome, adherence and attribution — M18, FR-1001…1004, INV-7, SAF-12.

The part of the system that decides whether it is learning or fooling itself.

Three ideas, and the second is the one most systems get wrong.

**An outcome is measured against a baseline, not against a hope.** "Yield was 4.2 t" says
nothing. "Yield was 4.2 t against a 3.6 t baseline for comparable plots" is a claim.

**Adherence is recorded, and unfollowed advice is not scored (INV-7).** If a recommendation
was never implemented, its outcome says nothing about the recommendation. A model that
learns "my advice failed" from advice nobody took will systematically un-learn its correct
advice, because the recommendations people ignore are not a random sample — they are the
inconvenient ones, which are often the right ones.

**``CONFOUNDED`` is a valid and expected answer (SAF-12).** A season where the advice was
followed, the price rose, and it rained perfectly is not evidence the advice worked. A
system that claims credit for every good outcome is a system whose credit means nothing.
Attribution here is deliberately conservative: it downgrades on any confounder it can see,
and it can only see some of them, which is itself recorded.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from agrivardhak.domain import enums
from agrivardhak.domain.models.decisions import (
    Attribution,
    Intervention,
    Outcome,
    Prediction,
)

#: Fidelity below which "followed" is really "partially followed". Below it we do not treat
#: the outcome as evidence about the recommendation at all.
FIDELITY_FLOOR = 0.6

#: Delay beyond which timing, not advice, is the plausible cause. A crop-protection action
#: taken three weeks late is a different action.
DELAY_CONFOUND_DAYS = 14

#: Relative change below which an outcome is noise rather than a result.
MATERIAL_CHANGE = 0.05


@dataclass(frozen=True)
class AttributionResult:
    strength: str
    rationale: str
    confounders: list[str]
    relative_change: float | None
    #: False when the recommendation was not followed well enough for the outcome to inform it.
    scored: bool


def record_outcome(
    session: Session,
    *,
    target_type: str,
    target_id: uuid.UUID,
    metric: str,
    observed_value: float,
    baseline_value: float | None,
    unit: str | None = None,
    intervention_id: uuid.UUID | None = None,
    period_start: dt.date | None = None,
    period_end: dt.date | None = None,
    external_conditions: dict[str, object] | None = None,
) -> Outcome:
    """Persist what actually happened. Append-only — an outcome is never revised in place."""
    outcome = Outcome(
        target_type=target_type,
        target_id=target_id,
        intervention_id=intervention_id,
        metric=metric,
        baseline_value=baseline_value,
        observed_value=observed_value,
        unit=unit,
        period_start=period_start,
        period_end=period_end,
        external_conditions=external_conditions,
    )
    session.add(outcome)
    session.flush()
    return outcome


def record_adherence(
    session: Session,
    *,
    intervention: Intervention,
    followed: enums.Adherence,
    fidelity: float | None = None,
    delay_days: int | None = None,
    deviation_notes: str | None = None,
) -> Intervention:
    """INV-7. What the human actually did, and how faithfully.

    Recorded even — especially — when the answer is "not at all". An intervention row saying
    ``NO`` is what stops the outcome from ever being read as a verdict on the advice.

    **Must be called before the intervention is flushed.** ``intervention`` is append-only
    under DR-04 with no mutable columns at all, so setting these fields on a row that already
    exists is not merely discouraged — the database trigger refuses the UPDATE. This function
    had no callers until the seed used it, and the first thing it did was raise
    ``RestrictViolation``: the fields were being written as an UPDATE after the INSERT.

    Recording adherence *later* than the intervention is a legitimate thing to want — a field
    officer reports back a fortnight after the action. That is a new intervention row
    superseding this one, which is what append-only means everywhere else in this schema, and
    it is a deliberate design choice rather than an oversight: "what we believed on the day"
    and "what we learned afterwards" are two facts, and overwriting the first loses one.
    """
    if intervention not in session.new:
        raise ValueError(
            "record_adherence must be called before the intervention is flushed. "
            "intervention is append-only (DR-04): to correct adherence on a row that already "
            "exists, insert a new intervention rather than updating this one."
        )
    intervention.followed = followed
    intervention.fidelity = fidelity
    intervention.delay_days = delay_days
    intervention.deviation_notes = deviation_notes
    session.flush()
    return intervention


def attribute(
    *,
    intervention: Intervention,
    outcome: Outcome,
    external_conditions: dict[str, object] | None = None,
) -> AttributionResult:
    """Decide how much of this outcome the intervention can honestly claim.

    The logic is a ladder of disqualifications rather than a score, because every step of it
    should be arguable by a human reading the result. A single number would hide which of
    these actually fired.
    """
    confounders: list[str] = []

    if intervention.followed in (enums.Adherence.NO, enums.Adherence.UNKNOWN):
        return AttributionResult(
            strength=enums.AttributionStrength.CONFOUNDED.value,
            rationale=(
                "The recommendation was not implemented, so this outcome says nothing about "
                "it. Scoring it either way would teach the system from advice nobody took."
            ),
            confounders=["not implemented"],
            relative_change=None,
            scored=False,
        )

    fidelity = float(intervention.fidelity) if intervention.fidelity is not None else None
    if fidelity is not None and fidelity < FIDELITY_FLOOR:
        return AttributionResult(
            strength=enums.AttributionStrength.CONFOUNDED.value,
            rationale=(
                f"Implemented at {fidelity:.0%} fidelity, below the {FIDELITY_FLOOR:.0%} floor. "
                "What was done and what was advised are different enough that the outcome "
                "cannot distinguish them."
            ),
            confounders=[f"low fidelity ({fidelity:.0%})"],
            relative_change=None,
            scored=False,
        )

    if intervention.delay_days and intervention.delay_days > DELAY_CONFOUND_DAYS:
        confounders.append(f"acted {intervention.delay_days} days late")

    baseline = float(outcome.baseline_value) if outcome.baseline_value is not None else None
    observed = float(outcome.observed_value) if outcome.observed_value is not None else None
    if baseline is None or observed is None or baseline == 0:
        return AttributionResult(
            strength=enums.AttributionStrength.UNCERTAIN.value,
            rationale=(
                "No baseline to compare against. The outcome is recorded, but a number with "
                "nothing to measure it from is not a result."
            ),
            confounders=[*confounders, "no baseline"],
            relative_change=None,
            scored=True,
        )

    change = (observed - baseline) / abs(baseline)

    conditions = external_conditions or outcome.external_conditions or {}
    for key, label in (
        ("price_moved_favourably", "market price moved in the same direction independently"),
        ("weather_favourable", "the season was unusually favourable"),
        ("other_interventions", "other interventions ran on the same plots"),
        ("scheme_payout", "a scheme payment landed in the same period"),
    ):
        if conditions.get(key):
            confounders.append(label)

    if abs(change) < MATERIAL_CHANGE:
        return AttributionResult(
            strength=enums.AttributionStrength.UNCERTAIN.value,
            rationale=(
                f"The outcome moved {change:+.1%} against baseline, inside the range we would "
                f"expect from ordinary variation. Neither success nor failure."
            ),
            confounders=confounders,
            relative_change=change,
            scored=True,
        )

    if confounders:
        return AttributionResult(
            strength=enums.AttributionStrength.CONFOUNDED.value,
            rationale=(
                f"The outcome moved {change:+.1%}, but {len(confounders)} other explanation"
                f"{'s' if len(confounders) > 1 else ''} would produce the same result: "
                f"{'; '.join(confounders)}. Claiming credit here would make the credit "
                f"meaningless everywhere else."
            ),
            confounders=confounders,
            relative_change=change,
            scored=True,
        )

    strength = (
        enums.AttributionStrength.HIGH
        if abs(change) >= 0.15 and (fidelity is None or fidelity >= 0.85)
        else enums.AttributionStrength.MODERATE
    )
    return AttributionResult(
        strength=strength.value,
        rationale=(
            f"The outcome moved {change:+.1%} against baseline, the recommendation was "
            f"implemented"
            + (f" at {fidelity:.0%} fidelity" if fidelity is not None else "")
            + ", and no confounder we track is present. Note that we track only the "
            "confounders listed in this module — absence of evidence is not evidence of "
            "absence."
        ),
        confounders=[],
        relative_change=change,
        scored=True,
    )


def persist_attribution(
    session: Session,
    *,
    outcome: Outcome,
    intervention: Intervention,
    result: AttributionResult,
) -> Attribution | None:
    """Store the judgement. Returns ``None`` when the outcome was not scoreable at all."""
    if not result.scored:
        return None
    row = Attribution(
        outcome_id=outcome.id,
        intervention_id=intervention.id,
        strength=enums.AttributionStrength(result.strength),
        confounders=result.confounders or None,
        rationale=result.rationale,
    )
    session.add(row)
    session.flush()
    return row


def score_prediction(
    session: Session, *, prediction: Prediction, actual: float, at: dt.datetime
) -> Prediction:
    """INV-6. Was the *claim about reality* right — separately from whether the advice was.

    Kept apart from attribution on purpose. A forecast can be accurate while the advice built
    on it was wrong, and vice versa; collapsing the two makes both unanswerable.
    """
    prediction.actual_value = actual
    prediction.actual_recorded_at = at
    if prediction.value_numeric:
        prediction.error = (actual - float(prediction.value_numeric)) / abs(
            float(prediction.value_numeric)
        )
    session.flush()
    return prediction


def summarise(session: Session, *, organization_id: uuid.UUID) -> dict[str, object]:
    """What the loop has actually recorded. Honest about how thin it is (FR-1201…1203).

    Deliberately reports the count of *unscoreable* outcomes alongside the scored ones. A
    panel showing only "3 successes" from three cherry-picked attributions is worse than no
    panel at all.
    """
    interventions = list(session.execute(select(Intervention)).scalars())
    attributions = list(session.execute(select(Attribution)).scalars())
    predictions = list(
        session.execute(select(Prediction).where(Prediction.actual_value.is_not(None))).scalars()
    )

    by_adherence: dict[str, int] = {}
    for record in interventions:
        key = record.followed.value
        by_adherence[key] = by_adherence.get(key, 0) + 1

    by_strength: dict[str, int] = {}
    for attribution in attributions:
        key = attribution.strength.value
        by_strength[key] = by_strength.get(key, 0) + 1

    errors = [abs(float(p.error)) for p in predictions if p.error is not None]
    return {
        "interventions": len(interventions),
        "adherence": by_adherence,
        "attributions": len(attributions),
        "attribution_strength": by_strength,
        # Every executed action that produced no attribution row — which is what the panel
        # labels "could not attribute". This used to count only NO/UNKNOWN adherence and so
        # missed the action that *was* followed, but too loosely to mean anything: the
        # fidelity-floor case never appeared in the one figure meant to own it.
        "unattributable": len(interventions) - len(attributions),
        "predictions_scored": len(predictions),
        "mean_absolute_error": round(sum(errors) / len(errors), 4) if errors else None,
        "note": (
            "Counts include outcomes we could not attribute. A panel that showed only the "
            "successes would be measuring our own selection, not our impact."
        ),
    }
