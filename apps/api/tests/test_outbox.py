"""Transactional outbox — M0e, DR-05, ADR-0007."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import select

from agrivardhak import outbox
from agrivardhak.domain import enums
from agrivardhak.domain.models.operations import DomainEvent, Task
from agrivardhak.domain.models.organization import Organization

pytestmark = pytest.mark.usefixtures("db")


@pytest.fixture
def org(session) -> Organization:
    row = session.execute(select(Organization)).scalars().first()
    if row is None:
        pytest.skip("database not seeded — run `make seed`")
    return row


def _event(org, event_type="TestEvent", aggregate_id=None) -> DomainEvent:
    return DomainEvent(
        event_type=event_type,
        aggregate_type="test",
        aggregate_id=aggregate_id or uuid.uuid4(),
        organization_id=org.id,
        actor_kind=enums.ActorKind.SYSTEM,
        occurred_at=dt.datetime.now(dt.UTC),
        payload={},
    )


def test_an_event_with_no_listener_is_still_marked_published(session, org) -> None:
    """Otherwise the backlog grows forever and hides the events that genuinely failed."""
    event = _event(org, "NobodyIsListening")
    session.add(event)
    session.flush()
    assert outbox.dispatch_pending(session) >= 1
    assert event.published_at is not None


def test_a_failing_handler_does_not_stall_the_queue(session, org) -> None:
    """A poison message halting every other decision would be worse than the message."""
    calls: list[str] = []

    @outbox.on("PoisonPill")
    def _boom(_session, _event) -> None:
        calls.append("boom")
        raise RuntimeError("handler exploded")

    try:
        first = _event(org, "PoisonPill")
        second = _event(org, "Harmless")
        session.add_all([first, second])
        session.flush()
        outbox.dispatch_pending(session)
        assert calls == ["boom"]
        assert first.published_at is not None, "the poison event is marked, not retried forever"
        assert second.published_at is not None, "and the one behind it still went out"
    finally:
        outbox.HANDLERS["PoisonPill"].remove(_boom)


def test_events_drain_in_order(session, org) -> None:
    """UUIDv7 ids are time-ordered, so two events about one aggregate cannot cross."""
    seen: list[str] = []

    @outbox.on("Ordered")
    def _record(_session, event) -> None:
        seen.append(event.payload["n"])

    try:
        aggregate = uuid.uuid4()
        for n in ("1", "2", "3"):
            row = _event(org, "Ordered", aggregate)
            row.payload = {"n": n}
            session.add(row)
            session.flush()
        outbox.dispatch_pending(session)
        assert seen == ["1", "2", "3"]
    finally:
        outbox.HANDLERS["Ordered"].remove(_record)


def test_approving_a_recommendation_creates_owned_work(session, org) -> None:
    """FR-805 / FR-904, through the outbox rather than inline in the approval path.

    Keeping it here means approving stays fast and cannot fail because a downstream side
    effect did — a calendar write must never be able to block a board decision.
    """
    from agrivardhak.api.scope import ContextScope
    from agrivardhak.domain.models.decisions import Recommendation
    from agrivardhak.domain.models.organization import RoleGrant
    from agrivardhak.orchestrator import engine, lifecycle

    grant = (
        session.execute(select(RoleGrant).where(RoleGrant.role == enums.Role.FPO_CEO))
        .scalars()
        .first()
    )
    if grant is None:
        pytest.skip("seed incomplete")
    scope = ContextScope(
        actor_user_id=grant.user_id,
        roles=frozenset({enums.Role.FPO_CEO}),
        organization_id=org.id,
    )
    result = engine.ask(session, scope=scope, question="Who should we sell the paddy to?")
    row = session.get(Recommendation, result.recommendation_ids[0])
    lifecycle.decide(
        session,
        recommendation=row,
        approver_user_id=grant.user_id,
        roles=frozenset({enums.Role.FPO_CEO}),
        decision=enums.ApprovalDecision.APPROVED,
        rationale="Agreed.",
    )
    session.flush()
    outbox.dispatch_pending(session)

    tasks = list(session.execute(select(Task).where(Task.recommendation_id == row.id)).scalars())
    assert len(tasks) == 1
    assert tasks[0].assignee_role is not None
    assert tasks[0].due_on is not None

    # At-least-once delivery: a redelivery must not double-book anyone.
    outbox._tasks_and_calendar_on_approval(
        session,
        session.execute(
            select(DomainEvent).where(
                DomainEvent.aggregate_id == row.id,
                DomainEvent.event_type == "RecommendationApproved",
            )
        )
        .scalars()
        .one(),
    )
    session.flush()
    again = list(session.execute(select(Task).where(Task.recommendation_id == row.id)).scalars())
    assert len(again) == 1, "handlers must be idempotent under at-least-once delivery"


def test_a_calendar_event_from_a_recommendation_lands_pending_approval(session, org) -> None:
    """FR-904. Somebody's Tuesday is a consequence, so the system may not just write it."""
    from agrivardhak.domain.models.operations import CalendarEvent

    events = list(
        session.execute(
            select(CalendarEvent).where(CalendarEvent.origin == enums.CalendarOrigin.AI_RECOMMENDED)
        ).scalars()
    )
    for event in events:
        assert event.status is not enums.CalendarStatus.APPROVED, (
            "an AI-originated calendar event may not approve itself"
        )
