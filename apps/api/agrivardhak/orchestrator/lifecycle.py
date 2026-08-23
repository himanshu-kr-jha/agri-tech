"""Recommendation lifecycle and approval — M14, FR-705…710, INV-1.

    SUGGESTED -> REVIEWED -> APPROVED -> EXECUTED -> OUTCOME_RECORDED
                     \\-> REJECTED
                      \\-> SUPERSEDED

This module is the only thing in the codebase that may advance a recommendation's status,
and that is the entire design. INV-1 says AI never autonomously performs a consequential
action. A rule written in a document is a rule someone will route around under deadline; a
rule expressed as *there is no other function that can write this column* is one they
cannot.

Three properties are enforced here rather than asked for:

**No execution without a signed approval.** :func:`execute` reads the approval row back from
the database before it will move anything. Passing it an approver's id is not enough — the
approval must exist, must belong to this recommendation, and must have been made by someone
holding the right role at the time.

**Approval is by a role, not a person.** The role exercised is recorded on the approval, so
"who approved this and by what authority" survives the approver leaving the organization
(FR-709). A ₹40 lakh allocation approved by a field officer is a different fact from the
same allocation approved by the board, and eight months later the distinction is the whole
of the audit.

**Modification is a first-class outcome.** ``APPROVED_WITH_MODIFICATION`` exists because the
common real answer to a recommendation is neither yes nor no but "yes, at ₹32,000 rather
than ₹35,000". Recording that as a plain approval would teach the system that its number was
accepted, and it would keep proposing that number. The modified value is stored, and it is
the modified value that executes.

On supersession (INV-10)
------------------------
New evidence never mutates an approved recommendation. It emits
``RecommendationSuperseded`` and flags the prior decision for review. Editing history in
place would make the audit trail a record of what we currently believe rather than of what
we decided — which is the opposite of its purpose.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from agrivardhak.domain import enums
from agrivardhak.domain.models.decisions import Approval, Intervention, Recommendation
from agrivardhak.domain.models.operations import AuditRecord, CalendarEvent, DomainEvent, Task

#: Which roles may approve which kind of recommendation (FR-707).
#:
#: The CEO is not in every row. A market officer approving a buyer selection is the normal
#: path and routing it through the CEO would guarantee the workflow gets bypassed. But a
#: funding allocation needs the finance officer or the CEO, and crop protection needs
#: someone who has actually seen a field.
APPROVAL_ROLES: dict[enums.RecommendationType, frozenset[enums.Role]] = {
    enums.RecommendationType.BUYER_SELECTION: frozenset(
        {enums.Role.MARKET_OFFICER, enums.Role.FPO_CEO}
    ),
    enums.RecommendationType.LOT_ALLOCATION: frozenset(
        {enums.Role.MARKET_OFFICER, enums.Role.FPO_CEO}
    ),
    enums.RecommendationType.CROP_PLAN: frozenset({enums.Role.FPO_CEO}),
    enums.RecommendationType.CROP_PROTECTION: frozenset(
        {enums.Role.FIELD_OFFICER, enums.Role.FPO_CEO}
    ),
    enums.RecommendationType.FUNDING_ALLOCATION: frozenset(
        {enums.Role.FINANCE_OFFICER, enums.Role.FPO_CEO}
    ),
    enums.RecommendationType.PROCUREMENT: frozenset(
        {enums.Role.MARKET_OFFICER, enums.Role.FPO_CEO}
    ),
    enums.RecommendationType.SCHEME_PURSUIT: frozenset(
        {enums.Role.FIELD_OFFICER, enums.Role.FPO_CEO}
    ),
    enums.RecommendationType.RISK_MITIGATION: frozenset({enums.Role.FPO_CEO}),
    enums.RecommendationType.SCHEDULE: frozenset({enums.Role.FPO_CEO}),
}

#: Statuses a recommendation may move to from each status. Anything not listed is refused.
TRANSITIONS: dict[enums.RecommendationStatus, frozenset[enums.RecommendationStatus]] = {
    enums.RecommendationStatus.SUGGESTED: frozenset(
        {
            enums.RecommendationStatus.REVIEWED,
            enums.RecommendationStatus.APPROVED,
            enums.RecommendationStatus.REJECTED,
            enums.RecommendationStatus.SUPERSEDED,
        }
    ),
    enums.RecommendationStatus.REVIEWED: frozenset(
        {
            enums.RecommendationStatus.APPROVED,
            enums.RecommendationStatus.REJECTED,
            enums.RecommendationStatus.SUPERSEDED,
        }
    ),
    enums.RecommendationStatus.APPROVED: frozenset(
        {enums.RecommendationStatus.EXECUTED, enums.RecommendationStatus.SUPERSEDED}
    ),
    enums.RecommendationStatus.EXECUTED: frozenset({enums.RecommendationStatus.OUTCOME_RECORDED}),
    enums.RecommendationStatus.OUTCOME_RECORDED: frozenset(),
    enums.RecommendationStatus.REJECTED: frozenset(),
    enums.RecommendationStatus.SUPERSEDED: frozenset(),
}


class LifecycleViolation(Exception):
    """Raised when something tries to move a recommendation somewhere it cannot go.

    Named for the invariant rather than for the error, so a caller reading a traceback
    learns what rule they hit rather than merely that something failed.
    """


@dataclass(frozen=True)
class ApprovalResult:
    recommendation_id: uuid.UUID
    approval_id: uuid.UUID
    status: enums.RecommendationStatus
    approved_value_paise: int | None
    was_modified: bool


# --------------------------------------------------------------------------- guards


def assert_transition(
    current: enums.RecommendationStatus, target: enums.RecommendationStatus
) -> None:
    if target not in TRANSITIONS[current]:
        raise LifecycleViolation(
            f"cannot move a recommendation from {current.value} to {target.value}; "
            f"allowed: {sorted(s.value for s in TRANSITIONS[current])}"
        )


def assert_may_approve(
    recommendation_type: enums.RecommendationType, roles: frozenset[enums.Role]
) -> enums.Role:
    """Return the role being exercised, or refuse.

    The *exercised* role is returned rather than the whole set because it is what gets
    recorded. Someone holding three roles approved this under one of them, and which one
    is the answer to "by what authority".
    """
    if enums.Role.PLATFORM_ADMIN in roles:
        raise LifecycleViolation(
            "a platform administrator may not approve an organization's decisions; "
            "operating the system is not the same authority as running the collective"
        )
    permitted = APPROVAL_ROLES.get(recommendation_type, frozenset({enums.Role.FPO_CEO}))
    held = roles & permitted
    if not held:
        raise LifecycleViolation(
            f"{recommendation_type.value} needs one of "
            f"{sorted(r.value for r in permitted)}; caller holds "
            f"{sorted(r.value for r in roles)}"
        )
    # Deterministic pick so the recorded authority does not depend on set iteration order.
    return sorted(held, key=lambda r: r.value)[0]


# --------------------------------------------------------------------------- transitions


def review(
    session: Session,
    *,
    recommendation: Recommendation,
    reviewer_user_id: uuid.UUID,
    note: str | None = None,
    at: dt.datetime | None = None,
) -> Recommendation:
    """Mark that a human has read this. Not an approval, and deliberately separate.

    Conflating "I have seen it" with "do it" is how rubber-stamping starts.
    """
    at = at or dt.datetime.now(dt.UTC)
    assert_transition(recommendation.status, enums.RecommendationStatus.REVIEWED)
    recommendation.status = enums.RecommendationStatus.REVIEWED
    _audit(
        session,
        recommendation=recommendation,
        actor_id=reviewer_user_id,
        action="review_recommendation",
        at=at,
        detail={"note": note},
    )
    return recommendation


def decide(
    session: Session,
    *,
    recommendation: Recommendation,
    approver_user_id: uuid.UUID,
    roles: frozenset[enums.Role],
    decision: enums.ApprovalDecision,
    rationale: str | None = None,
    approved_value_paise: int | None = None,
    at: dt.datetime | None = None,
) -> ApprovalResult:
    """Record a human decision. The only door to APPROVED (FR-705, INV-1)."""
    at = at or dt.datetime.now(dt.UTC)
    role = assert_may_approve(recommendation.type, roles)

    target = (
        enums.RecommendationStatus.REJECTED
        if decision is enums.ApprovalDecision.REJECTED
        else enums.RecommendationStatus.APPROVED
    )
    assert_transition(recommendation.status, target)

    modified = decision is enums.ApprovalDecision.APPROVED_WITH_MODIFICATION
    if modified and approved_value_paise is None:
        raise LifecycleViolation(
            "APPROVED_WITH_MODIFICATION without a modified value says nothing was modified. "
            "Use APPROVED, or supply the value that was actually agreed."
        )
    if decision is enums.ApprovalDecision.REJECTED and not rationale:
        raise LifecycleViolation(
            "a rejection needs a reason. It is the most valuable training signal the system "
            "gets, and an unexplained no teaches nothing (FR-706)"
        )

    approval = Approval(
        recommendation_id=recommendation.id,
        approver_user_id=approver_user_id,
        role_exercised=role,
        decision=decision,
        approved_value=approved_value_paise
        if modified
        else (
            recommendation.recommended_value
            if target == enums.RecommendationStatus.APPROVED
            else None
        ),
        rationale=rationale,
        decided_at=at,
    )
    session.add(approval)
    recommendation.status = target
    session.flush()

    _emit(
        session,
        recommendation=recommendation,
        event_type=(
            "RecommendationRejected"
            if target is enums.RecommendationStatus.REJECTED
            else "RecommendationApproved"
        ),
        at=at,
        actor_id=approver_user_id,
        payload={
            "decision": decision.value,
            "role_exercised": role.value,
            "approved_value_paise": approval.approved_value,
            "recommended_value_paise": recommendation.recommended_value,
            "modified": modified,
            "rationale": rationale,
        },
    )
    _audit(
        session,
        recommendation=recommendation,
        actor_id=approver_user_id,
        action=f"{decision.value.lower()}_recommendation",
        at=at,
        authority=role.value,
        detail={"rationale": rationale, "approved_value_paise": approval.approved_value},
    )
    return ApprovalResult(
        recommendation_id=recommendation.id,
        approval_id=approval.id,
        status=recommendation.status,
        approved_value_paise=approval.approved_value,
        was_modified=modified,
    )


def execute(
    session: Session,
    *,
    recommendation: Recommendation,
    executed_by: uuid.UUID,
    action_taken: str,
    cost_paise: int | None = None,
    at: dt.datetime | None = None,
) -> Intervention:
    """Move to EXECUTED. Refuses unless a real Approval row exists (INV-1).

    The approval is re-read from the database rather than trusted from an argument. A caller
    that has *just* approved something still has to have persisted it, which closes the gap
    where a well-meaning refactor passes a flag instead of a row.
    """
    at = at or dt.datetime.now(dt.UTC)

    # The approval is checked BEFORE the transition, and the order is about the message
    # rather than the outcome. Both refuse a SUGGESTED recommendation, but "cannot move
    # from SUGGESTED to EXECUTED" describes a state machine, while "no approval on record"
    # tells the caller what is actually missing and which invariant they hit.
    approval = (
        session.execute(
            select(Approval)
            .where(
                Approval.recommendation_id == recommendation.id,
                Approval.decision.in_(
                    (
                        enums.ApprovalDecision.APPROVED,
                        enums.ApprovalDecision.APPROVED_WITH_MODIFICATION,
                    )
                ),
            )
            .order_by(Approval.decided_at.desc())
        )
        .scalars()
        .first()
    )
    if approval is None:
        raise LifecycleViolation(
            "no approval on record for this recommendation. Nothing executes without one "
            "(INV-1) — this is the invariant, not a validation step to be relaxed."
        )
    assert_transition(recommendation.status, enums.RecommendationStatus.EXECUTED)

    recommendation.status = enums.RecommendationStatus.EXECUTED
    intervention = Intervention(
        recommendation_id=recommendation.id,
        action_taken=action_taken,
        executed_at=at,
        executed_by=executed_by,
        cost_paise=cost_paise,
        followed=enums.Adherence.YES,
    )
    session.add(intervention)
    session.flush()

    _emit(
        session,
        recommendation=recommendation,
        event_type="RecommendationExecuted",
        at=at,
        actor_id=executed_by,
        payload={
            "intervention_id": str(intervention.id),
            "approval_id": str(approval.id),
            "approved_value_paise": approval.approved_value,
            "action_taken": action_taken,
        },
    )
    _audit(
        session,
        recommendation=recommendation,
        actor_id=executed_by,
        action="execute_recommendation",
        at=at,
        authority=approval.role_exercised.value,
        detail={"approval_id": str(approval.id), "action_taken": action_taken},
    )
    return intervention


def supersede(
    session: Session,
    *,
    recommendation: Recommendation,
    replacement: Recommendation,
    reason: str,
    at: dt.datetime | None = None,
) -> Recommendation:
    """INV-10. New evidence replaces a decision; it never edits one."""
    at = at or dt.datetime.now(dt.UTC)
    assert_transition(recommendation.status, enums.RecommendationStatus.SUPERSEDED)
    recommendation.status = enums.RecommendationStatus.SUPERSEDED
    recommendation.superseded_by = replacement.id
    session.flush()
    _emit(
        session,
        recommendation=recommendation,
        event_type="RecommendationSuperseded",
        at=at,
        actor_id=None,
        payload={"replacement_id": str(replacement.id), "reason": reason},
    )
    return recommendation


def schedule_from(
    session: Session,
    *,
    recommendation: Recommendation,
    organization_id: uuid.UUID,
    title: str,
    starts_at: dt.datetime,
    ends_at: dt.datetime | None = None,
    subject_type: str = "recommendation",
    subject_id: uuid.UUID | None = None,
) -> CalendarEvent:
    """Create a calendar event from an approved recommendation.

    Lands at ``PENDING_APPROVAL`` (FR-904). A system that could write into a field officer's
    calendar unprompted would be performing a consequential action — somebody's Tuesday is a
    consequence.
    """
    if recommendation.status not in (
        enums.RecommendationStatus.APPROVED,
        enums.RecommendationStatus.EXECUTED,
    ):
        raise LifecycleViolation(
            "a calendar event may only be scheduled from an approved recommendation"
        )
    event = CalendarEvent(
        organization_id=organization_id,
        title=title,
        subject_type=subject_type,
        subject_id=subject_id or recommendation.id,
        starts_at=starts_at,
        ends_at=ends_at,
        origin=enums.CalendarOrigin.AI_RECOMMENDED,
        status=enums.CalendarStatus.PENDING_APPROVAL,
        recommendation_id=recommendation.id,
    )
    session.add(event)
    session.flush()
    return event


def task_from(
    session: Session,
    *,
    recommendation: Recommendation,
    organization_id: uuid.UUID,
    role: enums.Role,
    title: str,
    due_on: dt.date | None = None,
) -> Task:
    """FR-805: an action with an owner and a date. Created only after approval."""
    if recommendation.status not in (
        enums.RecommendationStatus.APPROVED,
        enums.RecommendationStatus.EXECUTED,
    ):
        raise LifecycleViolation("a task may only be created from an approved recommendation")
    task = Task(
        organization_id=organization_id,
        title=title,
        assignee_role=role,
        due_on=due_on,
        status=enums.TaskStatus.OPEN,
        recommendation_id=recommendation.id,
    )
    session.add(task)
    session.flush()
    return task


# --------------------------------------------------------------------------- plumbing


def _emit(
    session: Session,
    *,
    recommendation: Recommendation,
    event_type: str,
    at: dt.datetime,
    actor_id: uuid.UUID | None,
    payload: dict[str, object],
) -> None:
    session.add(
        DomainEvent(
            event_type=event_type,
            aggregate_type="recommendation",
            aggregate_id=recommendation.id,
            organization_id=recommendation.organization_id,
            actor_id=actor_id,
            actor_kind=enums.ActorKind.HUMAN if actor_id else enums.ActorKind.SYSTEM,
            occurred_at=at,
            payload={"recommendation_type": recommendation.type.value, **payload},
        )
    )


def _audit(
    session: Session,
    *,
    recommendation: Recommendation,
    actor_id: uuid.UUID | None,
    action: str,
    at: dt.datetime,
    authority: str | None = None,
    detail: dict[str, object] | None = None,
) -> None:
    session.add(
        AuditRecord(
            organization_id=recommendation.organization_id,
            actor_id=actor_id,
            actor_kind=enums.ActorKind.HUMAN if actor_id else enums.ActorKind.SYSTEM,
            action=action,
            subject_type="recommendation",
            subject_id=recommendation.id,
            authority=authority,
            evidence_ref={"snapshot_id": str(recommendation.snapshot_id)},
            detail=detail,
            occurred_at=at,
        )
    )
