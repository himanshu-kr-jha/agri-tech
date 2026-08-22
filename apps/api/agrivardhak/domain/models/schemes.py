"""Government schemes, eligibility and applications.

FR-561..FR-567. Two rules shape this module:

* ``INSUFFICIENT_DATA`` is never silently downgraded to ``NOT_ELIGIBLE``. Telling a farmer
  they do not qualify when we simply lack a field is a real harm, not a UI nicety.
* No application is ever auto-submitted (FR-567).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

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


class Scheme(Base, TimestampMixin):
    """A government programme.

    ``eligibility_rules`` is the machine-evaluable form; ``eligibility_text`` is the
    original wording it was transcribed from. Both are required — a rule we cannot trace
    back to published text is a rule we should not be applying to someone's benefits.
    """

    __tablename__ = "scheme"

    id: Mapped[UuidPk]
    code: Mapped[ShortText] = mapped_column(nullable=False, unique=True)
    name: Mapped[ShortText] = mapped_column(nullable=False)
    name_hi: Mapped[str | None] = mapped_column(String(255))
    authority: Mapped[str | None] = mapped_column(String(160))
    #: CENTRAL | STATE
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="CENTRAL")

    description: Mapped[str | None] = mapped_column(Text)
    eligibility_text: Mapped[str | None] = mapped_column(Text)
    #: {"all": [{"attr": ..., "op": ..., "value": ...}, {"any": [...]}]}
    eligibility_rules: Mapped[Json | None]
    required_documents: Mapped[list[str] | None] = mapped_column(ARRAY(Text))

    benefit_paise: Mapped[Paise | None]
    benefit_description: Mapped[str | None] = mapped_column(Text)

    application_deadline: Mapped[dt.date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(Text)
    #: When the eligibility text was retrieved. State schemes lapse; a stale retrieval date
    #: is the signal to re-check before acting on it (seed/sources.md §7).
    retrieved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class EligibilityAssessment(Base, AppendOnlyMixin):
    """Per-farmer, per-scheme result with rule-by-rule detail (FR-561).

    Append-only so the aggregate the CEO saw last week remains reconstructable, and so a
    farmer can see when and why their status changed.
    """

    __tablename__ = "eligibility_assessment"
    __table_args__ = (
        Index("ix_eligibility_farmer_scheme", "farmer_id", "scheme_id", "assessed_at"),
        Index("ix_eligibility_scheme_status", "scheme_id", "status"),
    )

    id: Mapped[UuidPk]
    farmer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farmer.id"), nullable=False)
    scheme_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scheme.id"), nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization.id"), nullable=False
    )

    status: Mapped[enums.EligibilityStatus] = mapped_column(
        Enum(enums.EligibilityStatus, name="eligibility_status"), nullable=False
    )
    #: [{rule, passed, actual, reason}, ...] — every rule, passed or failed.
    rule_results: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    #: Attributes we needed and did not have. Drives INSUFFICIENT_DATA rather than a
    #: false negative.
    missing_attributes: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    missing_documents: Mapped[list[str] | None] = mapped_column(ARRAY(Text))

    confidence: Mapped[Confidence] = mapped_column(nullable=False)
    estimated_benefit_paise: Mapped[Paise | None]
    assessed_at: Mapped[Timestamp] = mapped_column(nullable=False)
    module_version: Mapped[str] = mapped_column(String(32), nullable=False)


class SchemeApplication(Base, TimestampMixin):
    """DISCOVERED → ELIGIBLE → DOCUMENTS_PENDING → APPLIED → UNDER_REVIEW → APPROVED/REJECTED."""

    __tablename__ = "scheme_application"
    __table_args__ = (
        UniqueConstraint("farmer_id", "scheme_id", "cycle_year", name="farmer_scheme_year"),
        Index("ix_scheme_application_status", "organization_id", "status"),
    )

    id: Mapped[UuidPk]
    farmer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farmer.id"), nullable=False)
    scheme_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scheme.id"), nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization.id"), nullable=False
    )
    cycle_year: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[enums.ApplicationStatus] = mapped_column(
        Enum(enums.ApplicationStatus, name="application_status"),
        nullable=False,
        default=enums.ApplicationStatus.DISCOVERED,
    )
    documents_on_record: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    applied_on: Mapped[dt.date | None] = mapped_column(Date)
    decided_on: Mapped[dt.date | None] = mapped_column(Date)
    benefit_received_paise: Mapped[Paise | None]
    reference_no: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)


class FundingRequirement(Base, AppendOnlyMixin):
    """FR-601..FR-606. Deliberately shallow (D-21) — and it shows its arithmetic.

    ``data_sufficiency`` exists because the honest answer is often "we do not have this
    farmer's financial history". Saying so is better than implying a credit assessment we
    have not made (FR-606).
    """

    __tablename__ = "funding_requirement"
    __table_args__ = (Index("ix_funding_requirement_cycle", "crop_cycle_id"),)

    id: Mapped[UuidPk]
    crop_cycle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crop_cycle.id"), nullable=False)
    farmer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farmer.id"), nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization.id"), nullable=False
    )

    input_plan_cost_paise: Mapped[Paise] = mapped_column(nullable=False)
    expected_scheme_benefit_paise: Mapped[Paise] = mapped_column(nullable=False, default=0)
    farmer_contribution_paise: Mapped[Paise] = mapped_column(nullable=False, default=0)
    recommended_support_paise: Mapped[Paise] = mapped_column(nullable=False)

    expected_revenue_paise: Mapped[Paise | None]
    expected_farmer_roi: Mapped[float | None]

    #: Every term of the calculation, so the UI can render the arithmetic (FR-601).
    computation: Mapped[Json] = mapped_column(nullable=False)
    #: COMPLETE | PARTIAL | SPARSE
    data_sufficiency: Mapped[str] = mapped_column(String(16), nullable=False, default="PARTIAL")
    confidence: Mapped[Confidence] = mapped_column(nullable=False)
    computed_at: Mapped[Timestamp] = mapped_column(nullable=False)
    module_version: Mapped[str] = mapped_column(String(32), nullable=False)


class FundingAllocation(Base, TimestampMixin):
    """The organization's decision. Records the decision, not the money movement (D-21)."""

    __tablename__ = "funding_allocation"

    id: Mapped[UuidPk]
    farmer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farmer.id"), nullable=False)
    crop_cycle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("crop_cycle.id"))
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization.id"), nullable=False
    )
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recommendation.id"))

    #: Model C: inputs in kind plus working capital (FR-604).
    inputs_in_kind_paise: Mapped[Paise] = mapped_column(nullable=False, default=0)
    working_capital_paise: Mapped[Paise] = mapped_column(nullable=False, default=0)
    approved_on: Mapped[dt.date | None] = mapped_column(Date)
    acknowledged_on: Mapped[dt.date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
