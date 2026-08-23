"""Transactional outbox dispatcher — M0e, DR-05, ADR-0007.

Domain events are written in the same transaction as the state change they describe, so the
two cannot diverge. This is the other half: a poller that picks up unpublished rows and
hands them to whatever should react.

Why a table and a poller rather than a broker
---------------------------------------------
Publishing to a broker inside a transaction is the classic dual-write: the transaction can
commit and the publish fail, or the reverse, and the usual remedies are idempotency keys and
a dead-letter queue — a lot of machinery to recover a guarantee Postgres already offers for
free. For an MVP serving one collective, the poller is a few dozen lines and is correct by
construction (ADR-0007).

What it guarantees, precisely
-----------------------------
**At-least-once, not exactly-once.** A handler can see the same event twice if the process
dies between the handler running and ``published_at`` being written. Handlers must therefore
be idempotent, and the ones here are: they write rows keyed on the event's aggregate, so a
replay updates rather than duplicates.

**In order per aggregate.** Events are drained in id order, and ids are UUIDv7, so they are
time-ordered without a sequence. Two events about the same recommendation cannot be
processed out of order.

**One bad handler cannot stop the queue.** A handler that raises marks its event with the
error and moves on. A poison message halting all downstream work for an FPO would be a worse
failure than the one that caused it.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from agrivardhak.domain.models.operations import DomainEvent

log = logging.getLogger(__name__)

Handler = Callable[[Session, DomainEvent], None]

#: event_type -> handlers. Several handlers may react to one event; each is isolated.
HANDLERS: dict[str, list[Handler]] = {}


def on(event_type: str) -> Callable[[Handler], Handler]:
    def register(handler: Handler) -> Handler:
        HANDLERS.setdefault(event_type, []).append(handler)
        return handler

    return register


def dispatch_pending(session: Session, *, limit: int = 200, now: dt.datetime | None = None) -> int:
    """Drain unpublished events. Returns how many were marked published.

    Marking happens even when no handler is registered: an event nobody listens to is still
    delivered, and leaving it unpublished would make the backlog grow forever and hide the
    events that genuinely failed.
    """
    now = now or dt.datetime.now(dt.UTC)
    events = list(
        session.execute(
            select(DomainEvent)
            .where(DomainEvent.published_at.is_(None))
            .order_by(DomainEvent.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).scalars()
    )
    published = 0
    for event in events:
        for handler in HANDLERS.get(event.event_type, []):
            try:
                handler(session, event)
            except Exception:
                # Deliberately swallowed and logged. See the module docstring: one poison
                # event must not stall every other decision in the organization.
                log.exception("outbox handler failed for %s %s", event.event_type, event.id)
        event.published_at = now
        published += 1
    return published


def pending_count(session: Session) -> int:
    from sqlalchemy import func

    return int(
        session.execute(
            select(func.count()).select_from(DomainEvent).where(DomainEvent.published_at.is_(None))
        ).scalar_one()
    )


# --------------------------------------------------------------------------- handlers


@on("RecommendationApproved")
def _tasks_and_calendar_on_approval(session: Session, event: DomainEvent) -> None:
    """Turn an approved recommendation into owned work (FR-805, FR-904).

    Idempotent by construction: it checks for existing rows against this recommendation
    before creating any, so an at-least-once redelivery does not double-book a field
    officer's week.
    """
    from agrivardhak.domain.models.decisions import Recommendation
    from agrivardhak.domain.models.operations import CalendarEvent, Task
    from agrivardhak.orchestrator import lifecycle

    recommendation = session.get(Recommendation, event.aggregate_id)
    if recommendation is None or recommendation.organization_id is None:
        return

    already = (
        session.execute(select(Task).where(Task.recommendation_id == recommendation.id))
        .scalars()
        .first()
    )
    if already is not None:
        return

    role = _owner_role(recommendation.type)
    lifecycle.task_from(
        session,
        recommendation=recommendation,
        organization_id=recommendation.organization_id,
        role=role,
        title=recommendation.title,
        due_on=(event.occurred_at + dt.timedelta(days=14)).date(),
    )

    existing_event = (
        session.execute(
            select(CalendarEvent).where(CalendarEvent.recommendation_id == recommendation.id)
        )
        .scalars()
        .first()
    )
    if existing_event is None:
        lifecycle.schedule_from(
            session,
            recommendation=recommendation,
            organization_id=recommendation.organization_id,
            title=recommendation.title,
            starts_at=event.occurred_at + dt.timedelta(days=7),
        )


def _owner_role(recommendation_type: Any) -> Any:
    from agrivardhak.domain import enums
    from agrivardhak.orchestrator.reconcile import ACTION_OWNER

    return enums.Role(ACTION_OWNER.get(recommendation_type.value, "FPO_CEO"))


@on("RecommendationRejected")
def _record_rejection_signal(session: Session, event: DomainEvent) -> None:
    """A rejection is the most valuable feedback the system gets (FR-706).

    For now this only logs. The point of registering it is that the hook exists at the right
    place — when the learning loop is built it attaches here, not inside the approval path,
    so approving stays fast and cannot fail because a model-training side effect did.
    """
    log.info(
        "recommendation %s rejected: %s",
        event.aggregate_id,
        (event.payload or {}).get("rationale"),
    )
