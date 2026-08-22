"""Buyers, lots, matching and sales.

The Market module's job is that price is not value: a buyer offering more per kilogram
180 km away on 60-day terms can land less in a farmer's hand than a nearer buyer offering
less. ``BuyerMatch`` stores the whole derivation so the score is never a black box (FR-543).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agrivardhak.db.base import (
    AppendOnlyMixin,
    Base,
    Confidence,
    Json,
    Kg,
    Paise,
    ShortText,
    Timestamp,
    TimestampMixin,
    UuidPk,
)
from agrivardhak.domain import enums


class Buyer(Base, TimestampMixin):
    """FR-541."""

    __tablename__ = "buyer"
    __table_args__ = (Index("ix_buyer_org", "organization_id"),)

    id: Mapped[UuidPk]
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization.id"), nullable=False
    )
    name: Mapped[ShortText] = mapped_column(nullable=False)
    type: Mapped[enums.BuyerType] = mapped_column(
        Enum(enums.BuyerType, name="buyer_type"), nullable=False
    )
    location: Mapped[str | None] = mapped_column(String(160))
    distance_km: Mapped[float | None] = mapped_column(Numeric(8, 2))
    payment_terms_days: Mapped[int | None] = mapped_column(Integer)
    #: 0..1 from settlement history. Absent for a new buyer — treated as unknown, not zero.
    reliability: Mapped[Confidence | None]
    rejection_rate: Mapped[float | None] = mapped_column(Numeric(4, 3))
    min_quantity_kg: Mapped[Kg | None]
    max_quantity_kg: Mapped[Kg | None]
    quality_requirement: Mapped[enums.Grade | None] = mapped_column(Enum(enums.Grade, name="grade"))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class DemandSignal(Base, AppendOnlyMixin):
    """An expressed or inferred requirement for a commodity, quantity, grade and window."""

    __tablename__ = "demand_signal"
    __table_args__ = (Index("ix_demand_signal_crop_window", "crop_id", "window_start"),)

    id: Mapped[UuidPk]
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization.id"), nullable=False
    )
    buyer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("buyer.id"))
    crop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crop.id"), nullable=False)
    quantity_kg: Mapped[Kg | None]
    grade: Mapped[enums.Grade | None] = mapped_column(Enum(enums.Grade, name="grade"))
    price_paise_per_kg: Mapped[Paise | None]
    window_start: Mapped[dt.date | None] = mapped_column(Date)
    window_end: Mapped[dt.date | None] = mapped_column(Date)
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_source.id"))
    confidence: Mapped[Confidence | None]


class Lot(Base, TimestampMixin):
    """An aggregation of produce from one or more crop cycles, offered as one unit."""

    __tablename__ = "lot"
    __table_args__ = (Index("ix_lot_org_crop", "organization_id", "crop_id"),)

    id: Mapped[UuidPk]
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization.id"), nullable=False
    )
    crop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crop.id"), nullable=False)
    label: Mapped[ShortText] = mapped_column(nullable=False)
    quantity_kg: Mapped[Kg] = mapped_column(nullable=False)
    grade: Mapped[enums.Grade | None] = mapped_column(Enum(enums.Grade, name="grade"))
    ready_date: Mapped[dt.date | None] = mapped_column(Date)
    origin_location: Mapped[str | None] = mapped_column(String(160))

    items: Mapped[list[LotItem]] = relationship(back_populates="lot")


class LotItem(Base, TimestampMixin):
    """Which farmer's crop cycle contributed how much — the basis of fair settlement.

    This is what makes lot-level buyer matching visible to the individual farmer as well as
    the organization (FR-546), and what makes a share dispute resolvable.
    """

    __tablename__ = "lot_item"

    id: Mapped[UuidPk]
    lot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lot.id"), nullable=False)
    crop_cycle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crop_cycle.id"), nullable=False)
    farmer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farmer.id"), nullable=False)
    quantity_kg: Mapped[Kg] = mapped_column(nullable=False)
    grade: Mapped[enums.Grade | None] = mapped_column(Enum(enums.Grade, name="grade"))

    lot: Mapped[Lot] = relationship(back_populates="items")


class BuyerMatch(Base, AppendOnlyMixin):
    """A scored pairing of a lot with a buyer (FR-542, FR-543).

    ``components`` holds every term of the effective-price and attractiveness calculation
    so the UI can render the full breakdown. A score without its components is a black box,
    and a black box is not something an FPO should act on.
    """

    __tablename__ = "buyer_match"
    __table_args__ = (Index("ix_buyer_match_lot", "lot_id"),)

    id: Mapped[UuidPk]
    lot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lot.id"), nullable=False)
    buyer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("buyer.id"), nullable=False)

    headline_price_paise_per_kg: Mapped[Paise] = mapped_column(nullable=False)
    effective_price_paise_per_kg: Mapped[Paise] = mapped_column(nullable=False)
    attractiveness: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    #: {logistics, handling, quality_loss, transaction, storage, financing, weights{...}}
    components: Mapped[Json] = mapped_column(nullable=False)
    rank: Mapped[int | None] = mapped_column(Integer)
    negotiation_brief: Mapped[str | None] = mapped_column(Text)
    computed_at: Mapped[Timestamp] = mapped_column(nullable=False)
    module_version: Mapped[str] = mapped_column(String(32), nullable=False)


class Sale(Base, TimestampMixin):
    __tablename__ = "sale"

    id: Mapped[UuidPk]
    lot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lot.id"), nullable=False)
    buyer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("buyer.id"), nullable=False)
    buyer_match_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("buyer_match.id"))
    quantity_kg: Mapped[Kg] = mapped_column(nullable=False)
    price_paise_per_kg: Mapped[Paise] = mapped_column(nullable=False)
    agreed_on: Mapped[dt.date | None] = mapped_column(Date)
    delivered_on: Mapped[dt.date | None] = mapped_column(Date)
    payment_received_on: Mapped[dt.date | None] = mapped_column(Date)
    actual_grade: Mapped[enums.Grade | None] = mapped_column(Enum(enums.Grade, name="grade"))
    notes: Mapped[str | None] = mapped_column(Text)


class RiskRegisterEntry(Base, TimestampMixin):
    """FR-552. The organization's standing view of what could go wrong and who is exposed."""

    __tablename__ = "risk_register_entry"
    __table_args__ = (Index("ix_risk_org_status", "organization_id", "status"),)

    id: Mapped[UuidPk]
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization.id"), nullable=False
    )
    domain: Mapped[enums.RiskDomain] = mapped_column(
        Enum(enums.RiskDomain, name="risk_domain"), nullable=False
    )
    title: Mapped[ShortText] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    likelihood: Mapped[enums.Likelihood] = mapped_column(
        Enum(enums.Likelihood, name="likelihood"), nullable=False
    )
    impact: Mapped[enums.Impact] = mapped_column(Enum(enums.Impact, name="impact"), nullable=False)

    farmers_affected: Mapped[int | None] = mapped_column(Integer)
    area_affected_sqm: Mapped[float | None] = mapped_column(Numeric(14, 2))
    value_at_risk_paise: Mapped[Paise | None]

    #: {trigger, chain[{step, confidence}], exposure, recommended_action} — FR-553.
    causal_chain: Mapped[Json | None]
    recommended_action: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list[Any] | None] = mapped_column(JSONB)

    owner_role: Mapped[enums.Role | None] = mapped_column(Enum(enums.Role, name="role"))
    status: Mapped[enums.RiskStatus] = mapped_column(
        Enum(enums.RiskStatus, name="risk_status"), nullable=False, default=enums.RiskStatus.OPEN
    )
    review_on: Mapped[dt.date | None] = mapped_column(Date)


class NewsEvent(Base, AppendOnlyMixin):
    """A classified external event, before the Risk module reasons about exposure (FR-404)."""

    __tablename__ = "news_event"
    __table_args__ = (Index("ix_news_event_domain_occurred", "domain", "occurred_at"),)

    id: Mapped[UuidPk]
    external_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("external_record.id"))
    domain: Mapped[enums.NewsDomain] = mapped_column(
        Enum(enums.NewsDomain, name="news_domain"), nullable=False
    )
    headline: Mapped[ShortText] = mapped_column(nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[Timestamp] = mapped_column(nullable=False)
    #: True when the event itself is constructed for the demo. The UI must never present a
    #: constructed event as a real headline (seed/sources.md X8).
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
