"""Prediction, Recommendation, EvidenceSnapshot, Approval, Intervention, Outcome, Attribution.

This module carries the invariants the whole product rests on:

* INV-1  no code path reaches EXECUTED without a persisted Approval
* INV-2  evidence is frozen at generation and never recomputed
* INV-6  a Prediction is a claim about reality; a Recommendation is a proposed action
* INV-7  attribution is refused when adherence is UNKNOWN
* INV-10 new data supersedes; it never mutates an approved decision
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agrivardhak.db.base import (
    AppendOnlyMixin,
    Base,
    Confidence,
    Json,
    Paise,
    ShortText,
    Timestamp,
    TimestampMixin,
    UuidPk,
)
from agrivardhak.domain import enums


class Prediction(Base, AppendOnlyMixin):
    """A claim about reality, issued by a module (FR-702).

    Deliberately NOT a recommendation. A prediction that was accurate but led to a bad
    action is not a bad prediction, and a recommendation that was right but never followed
    is not a failed prediction. Separating them is what lets us say honestly which part of
    the system was wrong (INV-6).

    ``actual_value`` and ``error`` are written once when the outcome is realized.
    """

    __tablename__ = "prediction"
    __table_args__ = (
        Index("ix_prediction_subject", "subject_type", "subject_id", "metric"),
        Index("ix_prediction_module", "module", "module_version"),
    )

    id: Mapped[UuidPk]
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    module_version: Mapped[str] = mapped_column(String(32), nullable=False)

    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    metric: Mapped[str] = mapped_column(String(120), nullable=False)

    value_numeric: Mapped[float | None] = mapped_column(Numeric(18, 4))
    value_json: Mapped[Json | None]
    unit: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[Confidence] = mapped_column(nullable=False)

    issued_at: Mapped[Timestamp] = mapped_column(nullable=False)
    horizon_end: Mapped[dt.date | None]

    inputs_ref: Mapped[Json | None]

    actual_value: Mapped[float | None] = mapped_column(Numeric(18, 4))
    actual_recorded_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[float | None] = mapped_column(Numeric(18, 4))


class EvidenceSnapshot(Base, AppendOnlyMixin):
    """The immutable, hashed freeze of every input used to generate a recommendation.

    ADR-0004, and the single most important structural decision in the model. Without it,
    "why did the AI recommend Buyer A on 22 August?" can only be answered by recomputing
    against today's market data — which produces a *different* answer and destroys the
    audit trail.

    ``content_hash`` makes tampering detectable without a blockchain, which is exactly the
    "very strong audit trail, not necessarily blockchain" discovery called for.
    """

    __tablename__ = "evidence_snapshot"

    id: Mapped[UuidPk]
    captured_at: Mapped[Timestamp] = mapped_column(nullable=False)

    #: {module_outputs[], observations[], external_records[], org_state,
    #:  prompt_version, model_id, module_versions{}}
    payload: Mapped[Json] = mapped_column(nullable=False)
    #: SHA-256 over canonical JSON of ``payload``.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    #: Bumped when the payload shape changes, so old snapshots stay readable.
    payload_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")


class Recommendation(Base, TimestampMixin):
    """A proposed action (FR-703).

    ``status`` and the approval fields are the only mutable parts. The recommendation
    itself — what was proposed, on what evidence, with what confidence — is written once.
    New material data creates a *new* recommendation and marks this one SUPERSEDED; it
    never edits this row (INV-10).
    """

    __tablename__ = "recommendation"
    __table_args__ = (
        Index("ix_recommendation_org_status", "organization_id", "status"),
        Index("ix_recommendation_target", "target_type", "target_id"),
    )

    id: Mapped[UuidPk]
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization.id"), nullable=False
    )
    packet_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("decision_packet.id"))
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_snapshot.id"), nullable=False
    )

    type: Mapped[enums.RecommendationType] = mapped_column(
        Enum(enums.RecommendationType, name="recommendation_type"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID | None]

    title: Mapped[ShortText] = mapped_column(nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    #: [{kind, id, label, as_of}, ...] — never empty (FR-804).
    evidence: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[Confidence] = mapped_column(nullable=False)
    expected_impact: Mapped[Json | None]
    risks: Mapped[list[Any] | None] = mapped_column(JSONB)
    alternatives: Mapped[list[Any] | None] = mapped_column(JSONB)

    #: The value the AI proposed, e.g. a funding amount in paise. Kept separate from
    #: ``Approval.approved_value`` so "AI said 35,000; CEO approved 32,000" is data,
    #: not a log line (FR-706).
    recommended_value: Mapped[Paise | None]
    value_unit: Mapped[str | None] = mapped_column(String(32))

    status: Mapped[enums.RecommendationStatus] = mapped_column(
        Enum(enums.RecommendationStatus, name="recommendation_status"),
        nullable=False,
        default=enums.RecommendationStatus.SUGGESTED,
    )
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recommendation.id"))

    generator: Mapped[str] = mapped_column(String(64), nullable=False, default="orchestrator")
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    model_id: Mapped[str | None] = mapped_column(String(64))

    approvals: Mapped[list[Approval]] = relationship(back_populates="recommendation")


class DecisionPacket(Base, TimestampMixin):
    """The nine-section answer the orchestrator produced (FR-801).

    Stored whole so the exact rendered decision can be replayed, and so recommendations can
    point back at the question that produced them.
    """

    __tablename__ = "decision_packet"

    id: Mapped[UuidPk]
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization.id"), nullable=False
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_snapshot.id"), nullable=False
    )
    asked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[Json] = mapped_column(nullable=False)
    #: Full DecisionPacket JSON as emitted, including overrides.
    body: Mapped[Json] = mapped_column(nullable=False)
    overall_confidence: Mapped[Confidence] = mapped_column(nullable=False)
    generated_at: Mapped[Timestamp] = mapped_column(nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    model_id: Mapped[str | None] = mapped_column(String(64))


class Approval(Base, AppendOnlyMixin):
    """A human's recorded decision on a recommendation — the gate for INV-1.

    ``approved_value`` may differ from ``Recommendation.recommended_value``. That
    difference is the point: it is how the audit trail shows the human exercised judgement
    rather than rubber-stamping.
    """

    __tablename__ = "approval"
    __table_args__ = (Index("ix_approval_recommendation", "recommendation_id"),)

    id: Mapped[UuidPk]
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recommendation.id"), nullable=False
    )
    approver_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    role_exercised: Mapped[enums.Role] = mapped_column(
        Enum(enums.Role, name="role"), nullable=False
    )
    decision: Mapped[enums.ApprovalDecision] = mapped_column(
        Enum(enums.ApprovalDecision, name="approval_decision"), nullable=False
    )
    approved_value: Mapped[Paise | None]
    rationale: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[Timestamp] = mapped_column(nullable=False)

    recommendation: Mapped[Recommendation] = relationship(back_populates="approvals")


class Intervention(Base, AppendOnlyMixin):
    """An executed action, with adherence (FR-1001, FR-1002).

    ``recommendation_id`` is nullable: a farmer acting on their own initiative is still
    valuable signal, and forcing every intervention to descend from a recommendation would
    bias the learning loop toward our own advice.

    Adherence is what stops the model learning "my advice failed" from advice that was
    never implemented (INV-7).
    """

    __tablename__ = "intervention"
    __table_args__ = (
        Index("ix_intervention_recommendation", "recommendation_id"),
        Index("ix_intervention_cycle", "crop_cycle_id"),
        CheckConstraint(
            "fidelity IS NULL OR (fidelity >= 0 AND fidelity <= 1)", name="fidelity_range"
        ),
    )

    id: Mapped[UuidPk]
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recommendation.id"))
    crop_cycle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("crop_cycle.id"))
    farmer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("farmer.id"))

    action_taken: Mapped[str] = mapped_column(Text, nullable=False)
    executed_at: Mapped[Timestamp] = mapped_column(nullable=False)
    executed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    cost_paise: Mapped[Paise | None]

    followed: Mapped[enums.Adherence] = mapped_column(
        Enum(enums.Adherence, name="adherence"), nullable=False, default=enums.Adherence.UNKNOWN
    )
    fidelity: Mapped[float | None] = mapped_column(Numeric(4, 3))
    delay_days: Mapped[int | None] = mapped_column(Integer)
    deviation_notes: Mapped[str | None] = mapped_column(Text)


class Outcome(Base, AppendOnlyMixin):
    """The observed result against a baseline, with the conditions that prevailed (FR-1003)."""

    __tablename__ = "outcome"
    __table_args__ = (Index("ix_outcome_target", "target_type", "target_id"),)

    id: Mapped[UuidPk]
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    intervention_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("intervention.id"))

    metric: Mapped[str] = mapped_column(String(120), nullable=False)
    baseline_value: Mapped[float | None] = mapped_column(Numeric(18, 4))
    observed_value: Mapped[float | None] = mapped_column(Numeric(18, 4))
    unit: Mapped[str | None] = mapped_column(String(32))

    period_start: Mapped[dt.date | None]
    period_end: Mapped[dt.date | None]
    #: Rainfall, temperature, price movement over the period — the confounders, captured
    #: at the time rather than reconstructed later.
    external_conditions: Mapped[Json | None]


class Attribution(Base, AppendOnlyMixin):
    """How much of an outcome is plausibly explained by the intervention (FR-1004).

    CONFOUNDED is a legitimate and frequently correct result. The service layer refuses to
    create this row when the intervention's adherence is UNKNOWN — the difference between a
    learning system and one that learns the wrong thing.
    """

    __tablename__ = "attribution"

    id: Mapped[UuidPk]
    outcome_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("outcome.id"), nullable=False)
    intervention_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("intervention.id"), nullable=False
    )
    strength: Mapped[enums.AttributionStrength] = mapped_column(
        Enum(enums.AttributionStrength, name="attribution_strength"), nullable=False
    )
    confounders: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    rationale: Mapped[str | None] = mapped_column(Text)
