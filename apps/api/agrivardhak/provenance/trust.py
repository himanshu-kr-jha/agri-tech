"""Trust weights, confidence decay and conflict penalty (ADR-0005, FR-303, FR-304).

This is the arithmetic behind INV-3. It is deliberately a **pure module**: no database, no
clock. ``as_of`` is always passed in, so a replay against a stored EvidenceSnapshot produces
the same confidence it produced on the day.

The three factors that turn a raw claim into a usable confidence:

    effective = base_trust * verification_multiplier * 0.5 ** (age_days / half_life_days)

and then, if the value sits under an open discrepancy, a further penalty. That penalty is
applied **once, here**, so it propagates into every intelligence module automatically —
no module has to remember to apply it, which is exactly the kind of rule that gets forgotten.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from agrivardhak.domain.enums import SourceType, VerificationStatus

# --------------------------------------------------------------------------- defaults

#: Base trust by source type (DATA-MODEL.md §4.3). Overridable per DataSource row — these
#: are the fallbacks when a source has not been individually calibrated.
BASE_TRUST: dict[SourceType, float] = {
    SourceType.FIELD_OFFICER: 0.95,
    SourceType.ORG_RECORD: 0.90,
    SourceType.EXTERNAL_SOURCE: 0.85,
    SourceType.FARMER_SELF_REPORT: 0.70,
    SourceType.AI_INFERENCE: 0.75,
    SourceType.FIXTURE: 0.50,
}

#: An AI-inferred value may report its own confidence, but never above this. A model that is
#: certain is still a model, and a field officer who looked at the plot outranks it.
AI_INFERENCE_CEILING = 0.85

VERIFICATION_MULTIPLIER: dict[VerificationStatus, float] = {
    VerificationStatus.VERIFIED: 1.00,
    VerificationStatus.UNVERIFIED: 0.85,
    VerificationStatus.DISPUTED: 0.50,
    VerificationStatus.SUPERSEDED: 0.0,
}

#: Ceiling on the conflict penalty. Even wildly divergent sources leave *some* signal —
#: zeroing confidence would discard the fact that we know roughly the magnitude.
MAX_CONFLICT_PENALTY = 0.40


@dataclass(frozen=True)
class AttributeDecayPolicy:
    """Per-attribute freshness. Mirrors the ``attribute_policy`` table."""

    attribute: str
    half_life_days: float
    stale_after_days: float
    tolerance_pct: float = 5.0


#: Seed defaults (DATA-MODEL.md §4.3). Judgement calls, deliberately configuration rather
#: than constants so they can be refined as outcome data accumulates.
DEFAULT_POLICIES: dict[str, AttributeDecayPolicy] = {
    # 14, not 7: a week-old field-officer reading is still worth a great deal. The
    # earlier 7-day half-life conflated how fast a crop changes with how fast our
    # information about it decays, and drove every aggregate forecast to ~0 confidence.
    "crop_health_pct": AttributeDecayPolicy("crop_health_pct", 14, 30, 10),
    "crop_stage": AttributeDecayPolicy("crop_stage", 10, 30, 0),
    "soil_moisture": AttributeDecayPolicy("soil_moisture", 3, 10, 15),
    "expected_yield_kg": AttributeDecayPolicy("expected_yield_kg", 14, 45, 15),
    "market_price_paise_per_kg": AttributeDecayPolicy("market_price_paise_per_kg", 2, 7, 8),
    "area_sqm": AttributeDecayPolicy("area_sqm", 365, 730, 5),
    "soil_ph": AttributeDecayPolicy("soil_ph", 180, 540, 10),
    "water_availability": AttributeDecayPolicy("water_availability", 60, 180, 20),
    "livestock_count": AttributeDecayPolicy("livestock_count", 90, 365, 10),
    # A symptom report is a statement about one morning in one field. It stops being a
    # description of the crop very quickly — but it stays evidence that something was seen,
    # which is why it goes stale at 21 days rather than being deleted.
    "symptoms": AttributeDecayPolicy("symptoms", 7, 21, 0),
    # Published text, unlike an observation, does not go out of date by being old: a
    # government order issued in March still says exactly what it said in March. What
    # decays is whether it is still the *operative* one. Both half-lives below are
    # therefore much longer than an observation's, and the T-08 warning applies — do not
    # conflate how fast the world changes with how fast our information about it does.
    #
    # Reference guidance ("what is a soil health card") is the slowest-moving thing here.
    # At 180 days a two-year-old FAQ scored 0.02 and vanished from every result, which is
    # not a judgement anyone would defend out loud.
    "scheme_text": AttributeDecayPolicy("scheme_text", 730, 1460, 0),
    # A dated policy act. Halving over a year reflects the real rate at which orders are
    # superseded, amended or absorbed into standing practice.
    "policy_event": AttributeDecayPolicy("policy_event", 365, 730, 0),
}

#: Used when an attribute has no policy row. Conservative: decays fast, so an unmodelled
#: attribute cannot quietly carry high confidence for months.
FALLBACK_POLICY = AttributeDecayPolicy("__default__", half_life_days=30, stale_after_days=90)


def policy_for(attribute: str) -> AttributeDecayPolicy:
    return DEFAULT_POLICIES.get(attribute, FALLBACK_POLICY)


# --------------------------------------------------------------------------- computation


def base_trust_for(source_type: SourceType, reported: float | None = None) -> float:
    """Trust before verification and age are considered.

    ``reported`` is the source's own stated confidence — meaningful only for AI inference,
    where it is honoured but capped (see :data:`AI_INFERENCE_CEILING`).
    """
    base = BASE_TRUST[source_type]
    if source_type is SourceType.AI_INFERENCE and reported is not None:
        return min(reported, AI_INFERENCE_CEILING)
    return base


def age_days(observed_at: dt.datetime, as_of: dt.datetime) -> float:
    """Age in days, floored at zero.

    A future ``observed_at`` is clock skew or a data-entry error, not evidence from the
    future — treat it as fresh rather than letting it decay backwards into >1.0 confidence.
    """
    return max(0.0, (as_of - observed_at).total_seconds() / 86400.0)


def decay_factor(
    observed_at: dt.datetime, as_of: dt.datetime, policy: AttributeDecayPolicy
) -> float:
    if policy.half_life_days <= 0:
        return 1.0
    return float(0.5 ** (age_days(observed_at, as_of) / policy.half_life_days))


def is_stale(observed_at: dt.datetime, as_of: dt.datetime, policy: AttributeDecayPolicy) -> bool:
    return age_days(observed_at, as_of) > policy.stale_after_days


def effective_confidence(
    *,
    source_type: SourceType,
    verification_status: VerificationStatus,
    observed_at: dt.datetime,
    as_of: dt.datetime,
    attribute: str,
    reported_confidence: float | None = None,
    conflict_spread_pct: float | None = None,
) -> float:
    """The single number every intelligence module sees.

    Combines source trust, verification, age decay and any open conflict. Clamped to [0, 1].
    """
    policy = policy_for(attribute)
    value = base_trust_for(source_type, reported_confidence)
    value *= VERIFICATION_MULTIPLIER[verification_status]
    value *= decay_factor(observed_at, as_of, policy)
    value *= 1.0 - conflict_penalty(conflict_spread_pct)
    return max(0.0, min(1.0, value))


def conflict_penalty(spread_pct: float | None) -> float:
    """Confidence reduction for an open discrepancy (FR-304).

    Proportional to how far apart the sources are, capped so a conflict degrades a value
    without erasing it.
    """
    if not spread_pct or spread_pct <= 0:
        return 0.0
    return min(MAX_CONFLICT_PENALTY, spread_pct / 100.0)


# --------------------------------------------------------------------------- conflict detection


def spread_pct(values: list[Decimal | float]) -> float:
    """Relative spread across competing claims, as a percentage of the mean.

    Uses the mean rather than the max as the denominator so that the measure is symmetric —
    2.0 vs 1.6 acres reads the same whichever claim happens to be listed first.
    """
    nums = [float(v) for v in values if v is not None]
    if len(nums) < 2:
        return 0.0
    mean = sum(nums) / len(nums)
    if mean == 0:
        return 0.0 if max(nums) == min(nums) else 100.0
    return abs(max(nums) - min(nums)) / abs(mean) * 100.0


def exceeds_tolerance(values: list[Decimal | float], attribute: str) -> bool:
    """Whether a set of competing claims should raise a DataDiscrepancy."""
    return spread_pct(values) > policy_for(attribute).tolerance_pct
