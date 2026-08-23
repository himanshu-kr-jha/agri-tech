"""Morning briefing — M19, FR-811.

The design question this file exists to protect: what earns a place on a screen someone
glances at for fifteen seconds. A briefing that always has ten items teaches the reader to
skim it, and then the day it matters they skim that too.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import select

from agrivardhak.api.scope import ContextScope
from agrivardhak.domain import enums
from agrivardhak.domain.models.organization import Organization, RoleGrant
from agrivardhak.orchestrator import briefing, engine, lifecycle

pytestmark = pytest.mark.usefixtures("db")


@pytest.fixture(scope="module")
def seeded() -> dict[str, uuid.UUID]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from agrivardhak.config import get_settings

    db = create_engine(get_settings().database_url)
    with Session(db) as session:
        org = session.execute(select(Organization)).scalars().first()
        grant = (
            session.execute(select(RoleGrant).where(RoleGrant.role == enums.Role.FPO_CEO))
            .scalars()
            .first()
        )
    db.dispose()
    if org is None or grant is None:
        pytest.skip("database not seeded — run `make seed`")
    return {"org_id": org.id, "ceo_user_id": grant.user_id}


@pytest.fixture
def with_decisions(session, seeded):
    scope = ContextScope(
        actor_user_id=seeded["ceo_user_id"],
        roles=frozenset({enums.Role.FPO_CEO}),
        organization_id=seeded["org_id"],
    )
    result = engine.ask(session, scope=scope, question="Who should we sell the paddy to?")
    session.flush()
    return result


def test_the_briefing_leads_with_what_needs_a_decision(session, seeded, with_decisions) -> None:
    """An unapproved recommendation is work the collective paid for and is not yet getting.

    It comes first because it is the only thing on the page that *stops* if it is ignored.
    Ten healthy totals underneath are context.
    """
    result = briefing.build(session, organization_id=seeded["org_id"])
    assert result.needs_decision
    assert result.needs_decision[0].kind in ("recommendation", "calendar")
    assert not result.is_quiet


def test_an_approved_recommendation_leaves_the_decision_queue(
    session, seeded, with_decisions
) -> None:
    """The queue must drain, or it becomes wallpaper.

    Asserted on the specific recommendation rather than on a count: the briefing caps its
    lists, so approving five of twenty leaves the count unchanged while the queue has in fact
    moved. Counting would pass or fail depending on how much else was pending.
    """
    from agrivardhak.domain.models.decisions import Recommendation

    approved = [session.get(Recommendation, rec_id) for rec_id in with_decisions.recommendation_ids]
    for row in approved:
        lifecycle.decide(
            session,
            recommendation=row,
            approver_user_id=seeded["ceo_user_id"],
            roles=frozenset({enums.Role.FPO_CEO}),
            decision=enums.ApprovalDecision.APPROVED,
            rationale="Agreed.",
        )
    session.flush()

    still_waiting = {
        item.headline
        for item in briefing.build(session, organization_id=seeded["org_id"]).needs_decision
    }
    for row in approved:
        assert row.status is enums.RecommendationStatus.APPROVED
        assert row.title not in still_waiting, (
            "an approved recommendation must leave the decision queue"
        )


def test_open_data_conflicts_are_reported_as_data_health_not_as_a_decision(session, seeded) -> None:
    """INV-4 surfaced where it belongs: it qualifies every number above, it is not a task."""
    result = briefing.build(session, organization_id=seeded["org_id"])
    assert any(item.kind == "discrepancy" for item in result.data_health)
    assert not any(item.kind == "discrepancy" for item in result.needs_decision)


def test_the_briefing_stays_short(session, seeded, with_decisions) -> None:
    """Caps are the whole design. A long briefing is an unread briefing."""
    result = briefing.build(session, organization_id=seeded["org_id"])
    assert len(result.needs_decision) <= 6
    assert len(result.closing_soon) <= 8
    assert len(result.watch) <= 3


def test_a_quiet_day_is_reported_as_quiet_not_padded(session) -> None:
    """ "Nothing needs a decision" is a real answer. Filling the screen to look busy is not."""
    empty = briefing.build(session, organization_id=uuid.uuid4())
    assert empty.is_quiet
    assert empty.needs_decision == []


def test_the_briefing_reads_the_clock_only_through_its_argument(session, seeded) -> None:
    """So a briefing can be rebuilt for a past morning and compared with what was shown."""
    at = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    result = briefing.build(session, organization_id=seeded["org_id"], as_of=at)
    assert result.generated_at == at
