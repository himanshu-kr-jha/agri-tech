"""Morning briefing — M19, FR-811.

What a CEO sees before they have asked anything. The whole design question is what earns a
place on a screen someone glances at for fifteen seconds with tea in the other hand, and the
answer is not "a summary of everything".

It leads with **what needs a decision**, because that is the only thing on the screen that
stops if it is ignored. A recommendation waiting for approval is work the collective has
already paid for and is not yet getting. Then what changed since yesterday, then what is
closing soon, then what is broken in the data.

Explicitly not here: totals that did not move, a recap of yesterday's decisions, anything
whose only purpose is to make the screen look full. A briefing that always has ten items
teaches the reader to skim it, and then the day it matters they skim that too.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agrivardhak.domain import enums
from agrivardhak.domain.models.decisions import Recommendation
from agrivardhak.domain.models.market import RiskRegisterEntry
from agrivardhak.domain.models.operations import CalendarEvent, Task
from agrivardhak.domain.models.provenance import DataDiscrepancy
from agrivardhak.domain.units import format_lakh

#: A deadline inside this many days is "soon". Two weeks is roughly how far ahead an FPO
#: can still change what it does about something.
SOON_DAYS = 14


@dataclass
class BriefingItem:
    kind: str
    headline: str
    detail: str | None = None
    href: str | None = None
    count: int | None = None
    value_paise: int | None = None
    #: The unit ``value_paise`` is in. Carried because a buyer-selection value is paise *per
    #: kilogram*, not a total — rendering it as a rupee total produced "Rs 0.0 lakh · ₹18.54"
    #: side by side, both wrong in different ways.
    unit: str | None = None


@dataclass
class Briefing:
    generated_at: dt.datetime
    needs_decision: list[BriefingItem] = field(default_factory=list)
    closing_soon: list[BriefingItem] = field(default_factory=list)
    watch: list[BriefingItem] = field(default_factory=list)
    data_health: list[BriefingItem] = field(default_factory=list)

    @property
    def is_quiet(self) -> bool:
        return not (self.needs_decision or self.closing_soon or self.watch)

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "quiet": self.is_quiet,
            "needs_decision": [i.__dict__ for i in self.needs_decision],
            "closing_soon": [i.__dict__ for i in self.closing_soon],
            "watch": [i.__dict__ for i in self.watch],
            "data_health": [i.__dict__ for i in self.data_health],
        }


def build(
    session: Session, *, organization_id: uuid.UUID, as_of: dt.datetime | None = None
) -> Briefing:
    as_of = as_of or dt.datetime.now(dt.UTC)
    briefing = Briefing(generated_at=as_of)

    # 1. What is waiting on a human. First because it is the only thing here that stalls.
    pending = list(
        session.execute(
            select(Recommendation)
            .where(
                Recommendation.organization_id == organization_id,
                Recommendation.status.in_(
                    (
                        enums.RecommendationStatus.SUGGESTED,
                        enums.RecommendationStatus.REVIEWED,
                    )
                ),
            )
            .order_by(Recommendation.confidence.desc())
            .limit(5)
        ).scalars()
    )
    for row in pending:
        briefing.needs_decision.append(
            BriefingItem(
                kind="recommendation",
                headline=row.title,
                detail=(
                    f"{row.type.value.replace('_', ' ').lower()} · "
                    f"{round(float(row.confidence) * 100)}% confidence"
                    + (
                        f" · Rs {format_lakh(row.recommended_value)} lakh"
                        if row.recommended_value and row.value_unit != "paise_per_kg"
                        else ""
                    )
                ),
                href=f"/decisions/{row.packet_id}" if row.packet_id else None,
                value_paise=row.recommended_value,
                unit=row.value_unit,
            )
        )

    calendar_pending = session.execute(
        select(func.count())
        .select_from(CalendarEvent)
        .where(
            CalendarEvent.organization_id == organization_id,
            CalendarEvent.status == enums.CalendarStatus.PENDING_APPROVAL,
        )
    ).scalar_one()
    if calendar_pending:
        briefing.needs_decision.append(
            BriefingItem(
                kind="calendar",
                headline=f"{calendar_pending} calendar events await approval",
                detail="Nothing is in anyone's week until you approve it (FR-904).",
                href="/decisions",
                count=calendar_pending,
            )
        )

    # 2. Closing soon — where the window, not the size, is what makes it urgent.
    horizon = (as_of + dt.timedelta(days=SOON_DAYS)).date()
    for task in session.execute(
        select(Task)
        .where(
            Task.organization_id == organization_id,
            Task.status.in_((enums.TaskStatus.OPEN, enums.TaskStatus.IN_PROGRESS)),
            Task.due_on.is_not(None),
            Task.due_on <= horizon,
        )
        .order_by(Task.due_on)
        .limit(5)
    ).scalars():
        overdue = task.due_on is not None and task.due_on < as_of.date()
        briefing.closing_soon.append(
            BriefingItem(
                kind="task",
                headline=task.title,
                detail=(
                    f"{'overdue since' if overdue else 'due'} "
                    f"{task.due_on:%d %b} · {task.assignee_role.value.replace('_', ' ').lower()}"
                ),
            )
        )

    for risk in session.execute(
        select(RiskRegisterEntry)
        .where(
            RiskRegisterEntry.organization_id == organization_id,
            RiskRegisterEntry.status == enums.RiskStatus.OPEN,
            RiskRegisterEntry.review_on.is_not(None),
            RiskRegisterEntry.review_on <= horizon,
        )
        .order_by(RiskRegisterEntry.review_on)
        .limit(3)
    ).scalars():
        briefing.closing_soon.append(
            BriefingItem(
                kind="risk",
                headline=risk.title,
                detail=(
                    f"review by {risk.review_on:%d %b}"
                    + (f" · {risk.farmers_affected} farmers" if risk.farmers_affected else "")
                ),
                href="/risk",
                value_paise=risk.value_at_risk_paise,
                unit="paise",
            )
        )

    # 3. Standing exposure, biggest first. Not urgent, but not to be forgotten either.
    for risk in sorted(
        session.execute(
            select(RiskRegisterEntry).where(
                RiskRegisterEntry.organization_id == organization_id,
                RiskRegisterEntry.status == enums.RiskStatus.OPEN,
                RiskRegisterEntry.impact == enums.Impact.HIGH,
            )
        )
        .scalars()
        .all(),
        key=lambda r: -(r.value_at_risk_paise or 0),
    )[:3]:
        briefing.watch.append(
            BriefingItem(
                kind="risk",
                headline=risk.title,
                detail=(
                    f"{risk.likelihood.value.lower()} likelihood, high impact"
                    + (
                        f" · Rs {format_lakh(risk.value_at_risk_paise)} lakh at stake"
                        if risk.value_at_risk_paise
                        else ""
                    )
                ),
                href="/risk",
                value_paise=risk.value_at_risk_paise,
                unit="paise",
            )
        )

    # 4. Data health. Last, because it is about us rather than about the season — but present,
    # because every number above is only as good as this.
    open_conflicts = session.execute(
        select(func.count())
        .select_from(DataDiscrepancy)
        .where(DataDiscrepancy.status == enums.DiscrepancyStatus.OPEN)
    ).scalar_one()
    if open_conflicts:
        briefing.data_health.append(
            BriefingItem(
                kind="discrepancy",
                headline=f"{open_conflicts} unresolved data conflicts",
                detail=(
                    "Sources disagree about these values. Every figure derived from them "
                    "carries lower confidence until someone decides (INV-4)."
                ),
                href="/dashboard",
                count=open_conflicts,
            )
        )

    return briefing
