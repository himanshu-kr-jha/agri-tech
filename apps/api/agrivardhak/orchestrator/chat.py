"""``answer(AssistantRequest) -> AssistantAnswer`` — the outer seam.

Everything above this function knows only the two contract types. Everything below is the
hackathon orchestrator, and is meant to be replaceable: a future implementation that returns
an ``AssistantAnswer`` leaves the API, the SSE protocol, the conversation table and the whole
web tier untouched. That is the entire reason the boundary is a function here rather than a
set of endpoints in ``api/``.

The dispatch is four lines of logic and a lot of care about which of them a given asker can
reach. A farmer never reaches ``DECISION`` — Decision Packets are organization-scoped by
construction — and never reaches an organization lookup, because the router's vocabulary is
filtered by audience and the dispatch below imports the two lookup modules separately.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from agrivardhak.api.scope import ContextScope
from agrivardhak.config import get_settings
from agrivardhak.domain.models.decisions import DecisionPacket as DecisionPacketRow
from agrivardhak.domain.models.operations import ConversationTurn
from agrivardhak.orchestrator import engine, gather, review, router
from agrivardhak.orchestrator.assistant_contracts import (
    PROTECTED_SECTIONS,
    AssistantAnswer,
    AssistantRequest,
    IntentPlan,
    ResponseShape,
)
from agrivardhak.orchestrator.lookups import farmer as farmer_lookups
from agrivardhak.orchestrator.lookups import fpo as fpo_lookups
from agrivardhak.orchestrator.packet import Claim, DecisionPacket

log = logging.getLogger(__name__)

#: What a farmer is told when they ask for something on the other side of the boundary.
#: It names what they *can* see, because a refusal that only says no is indistinguishable
#: from a broken assistant, and the point of INV-5 is that the boundary is principled.
FARMER_REFUSAL = (
    "That is the collective's own information, and it stays with the collective until they "
    "choose to share it. What I can show you is your own farm — your crops and how they are "
    "doing, what is expected at harvest, which schemes you may claim, and anything the FPO "
    "has announced to members."
)

STAFF_REFUSAL = (
    "That is outside what this assistant covers. I can answer about this collective's "
    "members, crops, production, risks, buyers, schemes and working capital."
)


def answer(
    session: Session,
    *,
    scope: ContextScope,
    request: AssistantRequest,
    as_of: dt.datetime | None = None,
    plan: IntentPlan | None = None,
) -> AssistantAnswer:
    """Route, dispatch, review, record. Never raises for an ordinary bad question.

    ``plan`` may be supplied by a caller that already routed — the streaming endpoint does
    this so it can put the routing decision on the wire before the work starts, which is the
    only part of the response that is genuinely early.
    """
    started = dt.datetime.now(dt.UTC)
    as_of = as_of or started
    audience = scope.audience

    if plan is None:
        plan = router.plan(
            question=request.question,
            audience=audience,
            anchor_packet_id=request.anchor_packet_id,
        )

    if plan.entities.get("unknown_crop"):
        # Checked before the shape, because "we hold nothing about grapes" is the true answer
        # whatever the question was going to be. Answering about the collective instead would
        # be answering a question nobody asked, which is the failure this whole focus
        # mechanism exists to prevent.
        result = _unknown_crop(plan)
    elif plan.shape is ResponseShape.REFUSE:
        result = _refusal(plan, audience)
    elif plan.shape is ResponseShape.EXPLAIN:
        result = _explain(session, request=request, scope=scope, plan=plan)
    elif plan.shape is ResponseShape.LOOKUP:
        result = _lookup(session, scope=scope, plan=plan, as_of=as_of)
    else:
        result = _decision(session, scope=scope, request=request, plan=plan, as_of=as_of)

    turn = _record(
        session,
        scope=scope,
        request=request,
        answer=result,
        latency_ms=int((dt.datetime.now(dt.UTC) - started).total_seconds() * 1000),
    )
    return result.model_copy(update={"turn_id": turn.id})


# --------------------------------------------------------------------------- shapes


def _refusal(plan: IntentPlan, audience: str) -> AssistantAnswer:
    return AssistantAnswer(
        shape=ResponseShape.REFUSE,
        plan=plan,
        refusal=FARMER_REFUSAL if audience == "FARMER" else STAFF_REFUSAL,
    )


def _unknown_crop(plan: IntentPlan) -> AssistantAnswer:
    """The question named a crop this collective does not grow.

    A data gap, said plainly, and not dressed up as a policy refusal — the collective could
    grow it next season and then this answer changes. Naming what *is* grown turns a dead end
    into a next question.
    """
    named = str(plan.entities["unknown_crop"])
    grown = ", ".join(gather.DEMO_CROPS[:-1]) + f" and {gather.DEMO_CROPS[-1]}"
    return AssistantAnswer(
        shape=ResponseShape.REFUSE,
        plan=plan,
        refusal=(
            f"Nothing on record is about {named} — this collective does not currently grow "
            f"it, so there is no cycle, buyer or price for me to reason from. What it does "
            f"grow is {grown}. Ask about one of those, or about the collective as a whole."
        ),
    )


def _lookup(
    session: Session, *, scope: ContextScope, plan: IntentPlan, as_of: dt.datetime
) -> AssistantAnswer:
    """Run one named lookup, in the module that belongs to this audience.

    The two branches import from different modules on purpose. There is no shared query
    helper a mistake could route through, so a farmer turn cannot reach organization data
    even if every check above this line were removed (INV-5).
    """
    assert plan.lookup is not None  # guaranteed by router validation
    if scope.farmer_id is not None and not scope.is_org_staff:
        claims = farmer_lookups.run(
            session, key=plan.lookup, farmer_id=scope.farmer_id, as_of=as_of, entities=plan.entities
        )
    else:
        organization_id = scope.require_org()
        claims = fpo_lookups.run(
            session,
            key=plan.lookup,
            organization_id=organization_id,
            as_of=as_of,
            entities=plan.entities,
        )
    return AssistantAnswer(
        shape=ResponseShape.LOOKUP,
        plan=plan,
        claims=claims,
        # Nothing reorders a lookup's claims today — they arrive already ranked by the same
        # impact x confidence x urgency the packet uses — so the source set is the rendered
        # set and grounding is trivially true. It is still asserted rather than assumed.
        grounded=review.grounded(claims, claims),
    )


def _explain(
    session: Session, *, request: AssistantRequest, scope: ContextScope, plan: IntentPlan
) -> AssistantAnswer:
    """Answer a follow-up from the frozen packet, reading nothing live.

    This is the property worth protecting: "why did you say that?" must be answered from the
    bytes that produced the original answer, not by asking the question again. Re-running the
    orchestrator would give a *different* answer to a question about the first one, which is
    the exact failure this system exists to prevent (INV-2).
    """
    row = (
        session.get(DecisionPacketRow, request.anchor_packet_id)
        if request.anchor_packet_id
        else None
    )
    if row is None or (scope.organization_id and row.organization_id != scope.organization_id):
        return AssistantAnswer(
            shape=ResponseShape.REFUSE,
            plan=plan,
            refusal="I do not have that earlier answer to explain. Ask the question again.",
        )

    body: dict[str, Any] = row.body or {}
    claims: list[Claim] = []
    for section in ("situation", "impact", "expected_outcome"):
        for raw in body.get(section) or []:
            try:
                claims.append(Claim.model_validate(raw))
            except Exception:  # a stored claim we can no longer parse is not one we quote
                continue
    if not claims:
        return AssistantAnswer(
            shape=ResponseShape.REFUSE,
            plan=plan,
            refusal="That answer carried no explainable claims.",
        )
    return AssistantAnswer(
        shape=ResponseShape.EXPLAIN,
        plan=plan,
        claims=claims,
        grounded=review.grounded(claims, claims),
    )


def _decision(
    session: Session,
    *,
    scope: ContextScope,
    request: AssistantRequest,
    plan: IntentPlan,
    as_of: dt.datetime,
) -> AssistantAnswer:
    """The existing pipeline, unchanged, with a relevance ordering applied to its sections."""
    settings = get_settings()
    result = engine.ask(
        session,
        scope=scope,
        question=request.question,
        as_of=as_of,
        season=request.season,
        confidence_floor=settings.confidence_floor,
        model_id=settings.orchestrator_model if settings.anthropic_api_key else "deterministic",
        narrate=bool(settings.anthropic_api_key) and not settings.use_fixtures,
        # The router's own output, finally used. Previously computed and discarded, so a
        # question naming a crop produced the same packet as one that did not.
        plan=plan.modules or None,
        focus_subject=plan.entities.get("crop"),
    )
    sections = review.select_sections(request.question, result.packet)
    return AssistantAnswer(
        shape=ResponseShape.DECISION,
        plan=plan.model_copy(update={"entities": {**plan.entities, "sections": sections}}),
        packet=result.packet,
        packet_id=result.packet_row_id,
        content_hash=result.content_hash,
        grounded=_sections_valid(sections, result.packet),
    )


def _sections_valid(chosen: list[str], packet: DecisionPacket) -> bool:
    """Did the selector stay inside its remit?

    Two things must hold: it invented no section, and it dropped nothing protected. Reported
    rather than corrected — ``select_sections`` already re-appends protected sections, so a
    ``False`` here means something upstream of that changed and should be visible.
    """
    populated = {name for name in DecisionPacket.SECTION_ORDER if getattr(packet, name, None)}
    if packet.overrides:
        populated.add("overrides")
    if not set(chosen) <= populated:
        return False
    return (PROTECTED_SECTIONS & populated) <= set(chosen)


# --------------------------------------------------------------------------- record


def _record(
    session: Session,
    *,
    scope: ContextScope,
    request: AssistantRequest,
    answer: AssistantAnswer,
    latency_ms: int,
) -> ConversationTurn:
    """Every turn, whatever shape it took (FR-709).

    ``decision_packet`` only records the questions that produced a packet. Under a
    conversational assistant most answers are lookups, and a system whose promise is that a
    farmer can contest a decision cannot log its decisions and not its answers.
    """
    turn = ConversationTurn(
        conversation_id=request.conversation_id or uuid.uuid4(),
        organization_id=scope.organization_id,
        actor_user_id=scope.actor_user_id,
        farmer_id=scope.farmer_id,
        question=request.question,
        shape=answer.shape.value,
        lookup_key=answer.plan.lookup.value if answer.plan.lookup else None,
        intent_plan=json.loads(answer.plan.model_dump_json()),
        fell_back=answer.plan.fell_back,
        packet_id=answer.packet_id,
        answer=(
            {"refusal": answer.refusal}
            if answer.refusal
            else {"claims": [json.loads(c.model_dump_json()) for c in answer.claims]}
            if answer.claims
            # A DECISION turn stores a pointer, not a copy. Duplicating the packet body here
            # would create a second version that could drift from the one INV-2 protects.
            else {"packet_id": str(answer.packet_id) if answer.packet_id else None}
        ),
        grounded=answer.grounded,
        latency_ms=latency_ms,
    )
    session.add(turn)
    session.flush()
    return turn
