"""Observation resolution — the only legitimate way to read a consequential value (INV-3).

Writes go through :func:`record_observation`, which detects conflicts as they arrive. Reads
go through :func:`resolve`, which returns a :class:`ProvenancedValue` carrying an already
provenance-adjusted confidence — so an intelligence module physically cannot receive a bare
float whose origin it does not know.

The rule that gives this module its shape (FR-304): **when sources disagree, we do not pick
a winner.** We surface every claim, penalise confidence, and wait for a human with
verification authority. Silently choosing 1.8 acres because a field officer outranks a
farmer would be the easy implementation and the wrong one — it hides the disagreement from
the person best placed to resolve it.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from agrivardhak.domain.enums import (
    DiscrepancyStatus,
    SourceType,
    VerificationStatus,
)
from agrivardhak.domain.models.provenance import (
    DataDiscrepancy,
    DataSource,
    Observation,
)
from agrivardhak.intelligence.contracts import EvidenceRef, ProvenancedValue
from agrivardhak.provenance import trust


@dataclass(frozen=True)
class Claim:
    """One competing assertion about a (subject, attribute), used for conflict reporting."""

    observation_id: uuid.UUID
    #: SQLAlchemy hands back the Numeric column as float; both are accepted so the
    #: caller never has to convert just to report a conflict.
    value: Decimal | float | None
    unit: str | None
    source_type: SourceType
    observed_at: dt.datetime
    confidence: float

    def as_json(self) -> dict[str, Any]:
        return {
            "observation_id": str(self.observation_id),
            "value": float(self.value) if self.value is not None else None,
            "unit": self.unit,
            "source_type": self.source_type.value,
            "observed_at": self.observed_at.isoformat(),
            "confidence": round(self.confidence, 3),
        }


# --------------------------------------------------------------------------- reads


def _live_observations(
    session: Session, subject_type: str, subject_id: uuid.UUID, attribute: str
) -> list[Observation]:
    """Non-superseded observations, newest observation time first."""
    stmt = (
        select(Observation)
        .where(
            Observation.subject_type == subject_type,
            Observation.subject_id == subject_id,
            Observation.attribute == attribute,
            Observation.superseded_by.is_(None),
            Observation.verification_status != VerificationStatus.SUPERSEDED,
        )
        .order_by(Observation.observed_at.desc())
    )
    return list(session.execute(stmt).scalars())


def _open_discrepancy(
    session: Session, subject_type: str, subject_id: uuid.UUID, attribute: str
) -> DataDiscrepancy | None:
    stmt = select(DataDiscrepancy).where(
        DataDiscrepancy.subject_type == subject_type,
        DataDiscrepancy.subject_id == subject_id,
        DataDiscrepancy.attribute == attribute,
        DataDiscrepancy.status == DiscrepancyStatus.OPEN,
    )
    return session.execute(stmt).scalars().first()


def resolve(
    session: Session,
    *,
    subject_type: str,
    subject_id: uuid.UUID,
    attribute: str,
    as_of: dt.datetime,
) -> ProvenancedValue | None:
    """Current value for one (subject, attribute), with confidence already adjusted.

    Selection rule (FR-302): highest **effective** confidence wins — which folds together
    source trust, verification and freshness rather than ranking on any one of them. A
    field officer's six-month-old note legitimately loses to a farmer's report from today
    for a fast-decaying attribute like crop health, and that is the intended behaviour.

    Returns ``None`` when nothing has ever been observed. Callers must treat that as
    *unknown*, never as zero (FR-103).
    """
    observations = _live_observations(session, subject_type, subject_id, attribute)
    if not observations:
        return None

    discrepancy = _open_discrepancy(session, subject_type, subject_id, attribute)
    conflict_spread = float(discrepancy.spread_pct) if discrepancy else None

    scored: list[tuple[float, Observation]] = []
    for obs in observations:
        confidence = trust.effective_confidence(
            source_type=obs.source_type,
            verification_status=obs.verification_status,
            observed_at=obs.observed_at,
            as_of=as_of,
            attribute=attribute,
            reported_confidence=float(obs.confidence),
            conflict_spread_pct=conflict_spread,
        )
        scored.append((confidence, obs))

    confidence, winner = max(scored, key=lambda pair: pair[0])
    policy = trust.policy_for(attribute)

    return ProvenancedValue(
        attribute=attribute,
        value=Decimal(str(winner.value_numeric)) if winner.value_numeric is not None else None,
        value_text=winner.value_text,
        unit=winner.unit,
        confidence=confidence,
        source_type=winner.source_type.value,
        observed_at=winner.observed_at,
        is_stale=trust.is_stale(winner.observed_at, as_of, policy),
        has_open_discrepancy=discrepancy is not None,
        evidence=EvidenceRef(
            kind="observation",
            id=winner.id,
            label=f"{attribute} = {winner.value_numeric or winner.value_text}"
            f" ({winner.source_type.value.replace('_', ' ').lower()})",
            as_of=winner.observed_at,
        ),
    )


def resolve_many(
    session: Session,
    *,
    subject_type: str,
    subject_id: uuid.UUID,
    attributes: list[str],
    as_of: dt.datetime,
) -> dict[str, ProvenancedValue]:
    """Resolve several attributes for one subject. Missing attributes are simply absent."""
    out: dict[str, ProvenancedValue] = {}
    for attribute in attributes:
        value = resolve(
            session,
            subject_type=subject_type,
            subject_id=subject_id,
            attribute=attribute,
            as_of=as_of,
        )
        if value is not None:
            out[attribute] = value
    return out


# --------------------------------------------------------------------------- writes


def record_observation(
    session: Session,
    *,
    subject_type: str,
    subject_id: uuid.UUID,
    attribute: str,
    source_type: SourceType,
    observed_at: dt.datetime,
    recorded_at: dt.datetime,
    value_numeric: Decimal | float | None = None,
    value_text: str | None = None,
    unit: str | None = None,
    source: DataSource | None = None,
    source_ref: str | None = None,
    reported_confidence: float | None = None,
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED,
) -> tuple[Observation, DataDiscrepancy | None]:
    """Append an observation and check whether it puts sources into conflict.

    Returns the new observation and any discrepancy raised or updated by it.

    Note this **never** supersedes an existing observation automatically. A newer reading
    does not invalidate an older one — the older one may still be the more trustworthy
    claim, and deciding otherwise is the resolver's job at read time, or a human's job at
    verification time.
    """
    stored_confidence = trust.base_trust_for(source_type, reported_confidence)

    observation = Observation(
        subject_type=subject_type,
        subject_id=subject_id,
        attribute=attribute,
        value_numeric=Decimal(str(value_numeric)) if value_numeric is not None else None,
        value_text=value_text,
        unit=unit,
        source_type=source_type,
        source_id=source.id if source else None,
        source_ref=source_ref,
        observed_at=observed_at,
        recorded_at=recorded_at,
        confidence=stored_confidence,
        verification_status=verification_status,
    )
    session.add(observation)
    session.flush()

    discrepancy = detect_conflict(
        session,
        subject_type=subject_type,
        subject_id=subject_id,
        attribute=attribute,
        as_of=recorded_at,
    )
    return observation, discrepancy


def detect_conflict(
    session: Session,
    *,
    subject_type: str,
    subject_id: uuid.UUID,
    attribute: str,
    as_of: dt.datetime,
) -> DataDiscrepancy | None:
    """Raise or refresh a DataDiscrepancy when live claims diverge beyond tolerance.

    Only *fresh* claims are compared. Two readings of crop health three months apart are a
    time series, not a disagreement — comparing them would raise a conflict on every
    seasonal change and train everyone to ignore the badge.
    """
    policy = trust.policy_for(attribute)
    observations = _live_observations(session, subject_type, subject_id, attribute)

    fresh = [
        obs
        for obs in observations
        if obs.value_numeric is not None and not trust.is_stale(obs.observed_at, as_of, policy)
    ]
    # One claim per source type — a source repeating itself is not a conflict.
    latest_per_source: dict[SourceType, Observation] = {}
    for obs in fresh:
        held = latest_per_source.get(obs.source_type)
        if held is None or obs.observed_at > held.observed_at:
            latest_per_source[obs.source_type] = obs

    existing = _open_discrepancy(session, subject_type, subject_id, attribute)
    contenders = list(latest_per_source.values())

    if len(contenders) < 2:
        return existing

    values = [obs.value_numeric for obs in contenders]
    spread = trust.spread_pct(values)  # type: ignore[arg-type]

    if spread <= policy.tolerance_pct:
        return existing

    claims = [
        Claim(
            observation_id=obs.id,
            value=obs.value_numeric,
            unit=obs.unit,
            source_type=obs.source_type,
            observed_at=obs.observed_at,
            confidence=trust.effective_confidence(
                source_type=obs.source_type,
                verification_status=obs.verification_status,
                observed_at=obs.observed_at,
                as_of=as_of,
                attribute=attribute,
                reported_confidence=float(obs.confidence),
            ),
        )
        for obs in contenders
    ]
    best = max(claims, key=lambda c: c.confidence)
    penalised = best.confidence * (1.0 - trust.conflict_penalty(spread))

    if existing is not None:
        # Refresh in place rather than stacking duplicates on the same subject/attribute.
        existing.claims = [c.as_json() for c in claims]
        existing.spread_pct = spread
        existing.tolerance_pct = policy.tolerance_pct
        existing.effective_value = float(best.value) if best.value is not None else None
        existing.effective_confidence = penalised
        session.flush()
        return existing

    discrepancy = DataDiscrepancy(
        subject_type=subject_type,
        subject_id=subject_id,
        attribute=attribute,
        claims=[c.as_json() for c in claims],
        spread_pct=spread,
        tolerance_pct=policy.tolerance_pct,
        effective_value=float(best.value) if best.value is not None else None,
        effective_confidence=penalised,
        status=DiscrepancyStatus.OPEN,
    )
    session.add(discrepancy)
    session.flush()
    return discrepancy


def resolve_discrepancy(
    session: Session,
    *,
    discrepancy: DataDiscrepancy,
    resolver_user_id: uuid.UUID,
    winning_observation_id: uuid.UUID,
    rationale: str,
    resolved_at: dt.datetime,
) -> DataDiscrepancy:
    """Close a discrepancy by human decision (FR-305).

    The chosen observation is marked VERIFIED; the others are marked DISPUTED rather than
    deleted, so the record of what each source claimed survives. That trail is the point:
    it is what lets a farmer contest a decision that turned on a disputed plot area.
    """
    if discrepancy.status is not DiscrepancyStatus.OPEN:
        raise ValueError("discrepancy is not open")

    claim_ids = {uuid.UUID(c["observation_id"]) for c in discrepancy.claims}
    if winning_observation_id not in claim_ids:
        raise ValueError("winning observation is not one of the recorded claims")

    for observation_id in claim_ids:
        obs = session.get(Observation, observation_id)
        if obs is None:
            continue
        obs.verification_status = (
            VerificationStatus.VERIFIED
            if observation_id == winning_observation_id
            else VerificationStatus.DISPUTED
        )
        if observation_id == winning_observation_id:
            obs.verified_by = resolver_user_id
            obs.verified_at = resolved_at

    discrepancy.status = DiscrepancyStatus.RESOLVED
    discrepancy.resolved_by = resolver_user_id
    discrepancy.resolved_at = resolved_at
    discrepancy.resolution_observation_id = winning_observation_id
    discrepancy.resolution_rationale = rationale
    session.flush()
    return discrepancy
