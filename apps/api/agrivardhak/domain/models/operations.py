"""Calendar, tasks, consent, audit and the domain-event outbox.

The calendar is deliberately *contextual* rather than one organizational calendar: events
are scoped per subject (farmer, plot, crop cycle, organization) and merged into whatever
view the reader is entitled to (FR-901, FR-905).

Auto-generated consequential events land as PENDING_APPROVAL — the AI schedules, a human
authorizes (FR-904, INV-1).
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from agrivardhak.db.base import (
    AppendOnlyMixin,
    Base,
    Json,
    ShortText,
    Timestamp,
    TimestampMixin,
    UuidPk,
)
from agrivardhak.domain import enums


class CalendarEvent(Base, TimestampMixin):
    __tablename__ = "calendar_event"
    __table_args__ = (
        Index("ix_calendar_subject", "subject_type", "subject_id", "starts_at"),
        Index("ix_calendar_org_status", "organization_id", "status"),
    )

    id: Mapped[UuidPk]
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organization.id"))
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(nullable=False)

    title: Mapped[ShortText] = mapped_column(nullable=False)
    title_hi: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)

    starts_at: Mapped[Timestamp] = mapped_column(nullable=False)
    ends_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    origin: Mapped[enums.CalendarOrigin] = mapped_column(
        Enum(enums.CalendarOrigin, name="calendar_origin"), nullable=False
    )
    status: Mapped[enums.CalendarStatus] = mapped_column(
        Enum(enums.CalendarStatus, name="calendar_status"),
        nullable=False,
        default=enums.CalendarStatus.PENDING_APPROVAL,
    )
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recommendation.id"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    visibility: Mapped[enums.VisibilityScope] = mapped_column(
        Enum(enums.VisibilityScope, name="visibility_scope"),
        nullable=False,
        default=enums.VisibilityScope.OWNER,
    )


class Task(Base, TimestampMixin):
    """FR-906. Generated from approved calendar events; feeds the intervention record."""

    __tablename__ = "task"
    __table_args__ = (Index("ix_task_org_status", "organization_id", "status"),)

    id: Mapped[UuidPk]
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization.id"), nullable=False
    )
    calendar_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("calendar_event.id"))
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recommendation.id"))

    title: Mapped[ShortText] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    assignee_role: Mapped[enums.Role] = mapped_column(Enum(enums.Role, name="role"), nullable=False)
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    due_on: Mapped[dt.date | None] = mapped_column(Date)

    status: Mapped[enums.TaskStatus] = mapped_column(
        Enum(enums.TaskStatus, name="task_status"), nullable=False, default=enums.TaskStatus.OPEN
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Consent(Base, AppendOnlyMixin):
    """INV-9, FR-1101.

    Append-only and versioned: granting and revoking are both new rows, so we can always
    answer what a farmer had agreed to at the moment we used their data. ``revoked_at`` on
    the grant row is the only mutation, applied by a targeted UPDATE in the service layer.
    """

    __tablename__ = "consent"
    __table_args__ = (Index("ix_consent_farmer_purpose", "farmer_id", "purpose", "granted_at"),)

    id: Mapped[UuidPk]
    farmer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farmer.id"), nullable=False)
    purpose: Mapped[enums.ConsentPurpose] = mapped_column(
        Enum(enums.ConsentPurpose, name="consent_purpose"), nullable=False
    )
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    #: Version of the consent text shown at the time. Consent to v1 is not consent to v2.
    consent_text_version: Mapped[str] = mapped_column(String(32), nullable=False)
    granted_at: Mapped[Timestamp] = mapped_column(nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    captured_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))


class AuditRecord(Base, AppendOnlyMixin):
    """Who did what, when, on what evidence, with what authority (FR-709).

    This exists as a farmer protection first: it is what lets a member contest an FPO
    decision that affected them, not only what lets the FPO defend itself (SAF-10).
    """

    __tablename__ = "audit_record"
    __table_args__ = (
        Index("ix_audit_subject", "subject_type", "subject_id", "created_at"),
        Index("ix_audit_actor", "actor_id", "created_at"),
    )

    id: Mapped[UuidPk]
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organization.id"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    actor_kind: Mapped[enums.ActorKind] = mapped_column(
        Enum(enums.ActorKind, name="actor_kind"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[uuid.UUID | None]
    authority: Mapped[str | None] = mapped_column(String(64))
    evidence_ref: Mapped[Json | None]
    detail: Mapped[Json | None]
    occurred_at: Mapped[Timestamp] = mapped_column(nullable=False)


class DomainEvent(Base, AppendOnlyMixin):
    """Transactional outbox (ADR-0007).

    Written in the same transaction as the state change it describes, so a change and its
    event cannot diverge — the bug a message broker introduces and then makes you solve
    with idempotency keys and dead-letter queues.

    Ordering comes from ``seq``, not from the id.

    The id is a UUIDv7 and those are time-ordered — but only to **millisecond** resolution;
    below that, ``uuid_generate_v7()`` fills the remaining 74 bits with random bytes. Two
    events written in the same transaction land in the same millisecond almost every time,
    so ordering by id shuffled them at random. ``test_events_drain_in_order`` caught it by
    passing on one run and failing on the next with ``['2', '1', '3']``.

    That is not a cosmetic ordering: this table is what carries ``RecommendationApproved``
    and ``RecommendationSuperseded``, and a superseding event delivered before the approval
    it supersedes is INV-10 inverted. So the outbox now orders by a ``BIGINT`` identity
    column, which is monotonic by construction.
    """

    __tablename__ = "domain_event"
    __table_args__ = (
        Index("ix_domain_event_unpublished", "published_at"),
        Index("ix_domain_event_aggregate", "aggregate_type", "aggregate_id"),
        Index("ix_domain_event_type", "event_type", "occurred_at"),
        Index("ix_domain_event_seq", "seq"),
    )

    id: Mapped[UuidPk]
    #: Insertion order. The only correct thing to sort this table by.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organization.id"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    actor_kind: Mapped[enums.ActorKind] = mapped_column(
        Enum(enums.ActorKind, name="actor_kind"), nullable=False
    )
    occurred_at: Mapped[Timestamp] = mapped_column(nullable=False)
    payload: Mapped[Json] = mapped_column(nullable=False)
    #: Null until the dispatcher fans it out. The only mutable column on this table.
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class LlmCallLog(Base, AppendOnlyMixin):
    """NFR-603. Every model call, with the prompt version recorded on the resulting packet."""

    __tablename__ = "llm_call_log"

    id: Mapped[UuidPk]
    packet_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("decision_packet.id"))
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    latency_ms: Mapped[int | None]
    stop_reason: Mapped[str | None] = mapped_column(String(40))
    error: Mapped[str | None] = mapped_column(Text)


class ConversationTurn(Base, AppendOnlyMixin):
    """One question and the answer it got. Append-only (FR-709, SAF-10).

    Why this table exists when ``decision_packet`` already records questions: it only records
    the ones that produced a Decision Packet. Under a conversational assistant most answers
    are lookups and explanations, and a system whose promise is "a farmer can contest a
    decision" cannot log its decisions and not its answers. Every turn is recorded, whatever
    shape it took.

    Append-only for the same reason as the audit trail: the value of the record is that it
    cannot be tidied afterwards.

    ``answer`` holds the rendered claims or the refusal, not the packet. A DECISION turn
    points at ``packet_id`` and the packet carries its own frozen evidence — copying it here
    would create a second copy that could drift from the one INV-2 protects.
    """

    __tablename__ = "conversation_turn"
    __table_args__ = (
        Index("ix_conversation_turn_conversation", "conversation_id", "created_at"),
        Index("ix_conversation_turn_org", "organization_id", "created_at"),
    )

    id: Mapped[UuidPk]
    #: Groups turns into one session. Client-supplied; a new id simply starts a new thread.
    conversation_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organization.id"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    #: Set when a farmer asked. Which assistant answered is not inferable from roles alone
    #: once staff can also hold a farmer account.
    farmer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("farmer.id"))

    question: Mapped[str] = mapped_column(Text, nullable=False)
    #: DECISION | LOOKUP | EXPLAIN | REFUSE
    shape: Mapped[str] = mapped_column(String(16), nullable=False)
    lookup_key: Mapped[str | None] = mapped_column(String(48))
    #: The router's own output, kept so a bad answer can be traced to a bad route.
    intent_plan: Mapped[Json | None]
    #: True when the router fell back to keywords — a degraded answer, recorded as degraded.
    fell_back: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    packet_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("decision_packet.id"))
    #: The rendered claims, or the refusal text. Absent for DECISION turns, which point at
    #: the packet instead.
    answer: Mapped[Json | None]
    grounded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    latency_ms: Mapped[int | None]
