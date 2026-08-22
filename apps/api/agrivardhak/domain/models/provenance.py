"""Observation, DataSource, DataDiscrepancy, ExternalRecord — the provenance layer.

ADR-0005. Volatile, consequential facts live here as append-only observations carrying
source, time, confidence and verification status. Stable facts stay as plain columns on
their entity. This is the split that keeps provenance real without EAV sprawl.

Nothing in ``intelligence/`` may read a consequential value except through this layer (INV-3).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agrivardhak.db.base import (
    AppendOnlyMixin,
    Base,
    Confidence,
    Json,
    ShortText,
    Timestamp,
    TimestampMixin,
    UuidPk,
)
from agrivardhak.domain import enums


class DataSource(Base, TimestampMixin):
    """A registered origin of data, with its trust weight and cadence."""

    __tablename__ = "data_source"

    id: Mapped[UuidPk]
    key: Mapped[ShortText] = mapped_column(nullable=False, unique=True)
    label: Mapped[ShortText] = mapped_column(nullable=False)
    source_type: Mapped[enums.SourceType] = mapped_column(
        Enum(enums.SourceType, name="source_type"), nullable=False
    )
    base_trust: Mapped[Confidence] = mapped_column(nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    cadence: Mapped[str | None] = mapped_column(String(64))
    #: True when this source is a fixture standing in for an unreachable live source.
    #: Everything derived from it must render with the DEMO DATA marker (FR-406, UI-04).
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AttributePolicy(Base, TimestampMixin):
    """Per-attribute decay, staleness and conflict tolerance (FR-303, FR-304, FR-306).

    Configuration rather than constants, because these half-lives start as judgement calls
    and should be refinable as outcome data accumulates. They are visible in the admin UI
    for exactly that reason.
    """

    __tablename__ = "attribute_policy"

    id: Mapped[UuidPk]
    attribute: Mapped[ShortText] = mapped_column(nullable=False, unique=True)
    unit: Mapped[str | None] = mapped_column(String(32))
    half_life_days: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    stale_after_days: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    #: Percentage spread between competing claims above which a discrepancy is raised.
    tolerance_pct: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=5)
    notes: Mapped[str | None] = mapped_column(Text)


class Observation(Base, AppendOnlyMixin):
    """One value, with everything needed to know how much to trust it (FR-301).

    Append-only: a correction is a new row plus ``superseded_by`` on the old one. There is
    no UPDATE path, and the migration revokes UPDATE/DELETE at the grant level so the rule
    is enforced by Postgres rather than by convention (DR-04).
    """

    __tablename__ = "observation"
    __table_args__ = (
        Index("ix_observation_subject", "subject_type", "subject_id", "attribute", "observed_at"),
        Index("ix_observation_attribute", "attribute"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )

    id: Mapped[UuidPk]

    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    attribute: Mapped[str] = mapped_column(String(120), nullable=False)

    value_numeric: Mapped[float | None] = mapped_column(Numeric(18, 4))
    value_text: Mapped[str | None] = mapped_column(Text)
    value_json: Mapped[Json | None]
    unit: Mapped[str | None] = mapped_column(String(32))

    source_type: Mapped[enums.SourceType] = mapped_column(
        Enum(enums.SourceType, name="source_type"), nullable=False
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_source.id"))
    #: Image id, external record id, or the user id that reported it.
    source_ref: Mapped[str | None] = mapped_column(Text)

    #: When reality was as stated — distinct from when we found out (``created_at``).
    observed_at: Mapped[Timestamp] = mapped_column(nullable=False)
    recorded_at: Mapped[Timestamp] = mapped_column(nullable=False)

    confidence: Mapped[Confidence] = mapped_column(nullable=False)
    verification_status: Mapped[enums.VerificationStatus] = mapped_column(
        Enum(enums.VerificationStatus, name="verification_status"),
        nullable=False,
        default=enums.VerificationStatus.UNVERIFIED,
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    superseded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("observation.id"))


class DataDiscrepancy(Base, TimestampMixin):
    """Recorded conflict between sources for one (subject, attribute) — INV-4, FR-304.

    The system does not output "1.8 acres" when three sources disagree. It records every
    claim, penalizes downstream confidence, surfaces the conflict at the point of use, and
    waits for a human with verification authority.

    ``status`` is the only mutable field; the claims themselves are frozen.
    """

    __tablename__ = "data_discrepancy"
    __table_args__ = (
        Index("ix_discrepancy_subject", "subject_type", "subject_id", "attribute"),
        Index("ix_discrepancy_status", "status"),
    )

    id: Mapped[UuidPk]
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    attribute: Mapped[str] = mapped_column(String(120), nullable=False)

    #: [{observation_id, value, unit, source_type, observed_at, confidence}, ...]
    claims: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    spread_pct: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    tolerance_pct: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)

    #: Highest-trust claim, retained for display — but always shown alongside the conflict,
    #: never as a settled answer.
    effective_value: Mapped[float | None] = mapped_column(Numeric(18, 4))
    effective_confidence: Mapped[Confidence | None]

    status: Mapped[enums.DiscrepancyStatus] = mapped_column(
        Enum(enums.DiscrepancyStatus, name="discrepancy_status"),
        nullable=False,
        default=enums.DiscrepancyStatus.OPEN,
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_observation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("observation.id")
    )
    resolution_rationale: Mapped[str | None] = mapped_column(Text)


class ExternalRecord(Base, AppendOnlyMixin):
    """Raw payload from an external source, retained so evidence can cite it (FR-405).

    The raw payload is kept deliberately: an EvidenceSnapshot that cites a derived number
    without the original response cannot be audited when the source later changes.
    """

    __tablename__ = "external_record"
    __table_args__ = (
        Index("ix_external_record_kind_fetched", "kind", "fetched_at"),
        UniqueConstraint("kind", "dedupe_key", name="kind_dedupe"),
    )

    id: Mapped[UuidPk]
    kind: Mapped[enums.ExternalRecordKind] = mapped_column(
        Enum(enums.ExternalRecordKind, name="external_record_kind"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_source.id"), nullable=False)
    #: Stable identity for idempotent ingestion, e.g. "agmarknet:prayagraj:potato:2026-02-14".
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    fetched_at: Mapped[Timestamp] = mapped_column(nullable=False)
    observed_at: Mapped[Timestamp] = mapped_column(nullable=False)
    payload: Mapped[Json] = mapped_column(nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
