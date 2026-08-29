"""The conversational assistant endpoint (API-05, FR-807).

Additive. ``/assistant/ask`` is untouched and still serves the decision-only path and its
tests; this is the entry point the chat UI uses, and it can produce any of the four response
shapes rather than always a Decision Packet.

The endpoints are thin on purpose. All of the behaviour lives behind
``orchestrator.chat.answer``, which is the seam a future orchestrator replaces — an endpoint
that reached past it into the router or the lookups would put a second door in the wall.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from agrivardhak.api.auth import CurrentScope
from agrivardhak.api.scope import ScopeViolation
from agrivardhak.db.session import get_session
from agrivardhak.orchestrator import chat
from agrivardhak.orchestrator import router as intent_router
from agrivardhak.orchestrator.assistant_contracts import (
    MAX_QUESTION_CHARS,
    AssistantRequest,
    ResponseShape,
)
from agrivardhak.orchestrator.packet import DecisionPacket

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["assistant"])

SessionDep = Annotated[Session, Depends(get_session)]


def _request(body: dict[str, Any]) -> AssistantRequest:
    question = str(body.get("question", "")).strip()
    if not question:
        raise HTTPException(status_code=422, detail="question is required")
    return AssistantRequest(
        question=question[:MAX_QUESTION_CHARS],
        conversation_id=_uuid(body.get("conversation_id")),
        anchor_packet_id=_uuid(body.get("anchor_packet_id")),
        season=body.get("season"),
    )


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except (ValueError, TypeError):
        return None


def _guard(scope: Any) -> None:
    """Anyone signed in may ask; *what* they can ask about is decided by their scope.

    Deliberately not the ``_require_org`` gate the decision endpoint uses. That gate exists
    because a Decision Packet is organization-scoped; a farmer asking about their own farm is
    a legitimate use of this endpoint and the router simply never offers them a shape or a
    lookup outside their own world.
    """
    if scope.farmer_id is None and not (scope.is_org_staff or scope.is_platform_admin):
        raise ScopeViolation("this account is neither organization staff nor a farmer")


@router.post("/assistant/chat")
def ask(
    session: SessionDep, scope: CurrentScope, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    _guard(scope)
    answer = chat.answer(session, scope=scope, request=_request(body))
    session.commit()
    return answer.as_wire()


@router.post("/assistant/chat/stream")
def ask_stream(
    session: SessionDep, scope: CurrentScope, body: dict[str, Any] = Body(...)
) -> StreamingResponse:
    """Same answer, with the routing decision on the wire before the work begins.

    The old ``/ask/stream`` opened with a ``planning`` frame that carried no information —
    the only genuinely early thing it could send, and it said nothing. Here the first frame
    is the router's actual decision ("reading buyers and prices"), which is both real and
    what makes the ~700ms of classification feel like progress rather than latency.
    """
    _guard(scope)
    request = _request(body)

    def emit() -> Iterator[str]:
        try:
            yield from _turn(session, scope, request)
        except Exception as exc:
            # Once the first frame is on the wire the status code is already 200, so an
            # exception here would otherwise reach the browser as a stream that simply stops:
            # no error, no answer, and a spinner that never resolves. Saying so is the
            # minimum; the traceback is still logged for us.
            log.exception("assistant turn failed mid-stream")
            yield _sse("error", {"detail": f"{type(exc).__name__}: {exc}"})

    def _turn(session: Session, scope: Any, request: AssistantRequest) -> Iterator[str]:
        plan = intent_router.plan(
            question=request.question,
            audience=scope.audience,
            anchor_packet_id=request.anchor_packet_id,
        )
        yield _sse(
            "routing",
            {
                "shape": plan.shape.value,
                "lookup": plan.lookup.value if plan.lookup else None,
                "modules": plan.modules,
                # What the router understood from the question, not just what it will read.
                # Without this the first frame cannot tell a reader whether the crop they
                # named was picked up — which is the one thing they want to know.
                "entities": plan.entities,
                "rationale": plan.rationale,
                "fell_back": plan.fell_back,
            },
        )

        answer = chat.answer(session, scope=scope, request=request, plan=plan)
        session.commit()
        wire = answer.as_wire()

        if answer.shape is ResponseShape.REFUSE:
            yield _sse("refusal", {"text": answer.refusal})
        elif answer.packet is not None:
            body_json = wire["packet"] or {}
            # The relevance selector's order, falling back to the packet's fixed order if it
            # did not run. A section is emitted only once it exists in full — a claim without
            # its evidence is not half a claim, it is not one.
            order = answer.plan.entities.get("sections") or list(DecisionPacket.SECTION_ORDER)
            for section in order:
                yield _sse("section", {"section": section, "content": body_json.get(section)})
        else:
            for index, claim in enumerate(wire["claims"]):
                yield _sse("claim", {"index": index, "content": claim})

        yield _sse(
            "done",
            {
                "turn_id": wire["turn_id"],
                "packet_id": wire["packet_id"],
                "content_hash": wire["content_hash"],
                "grounded": wire["grounded"],
                "shape": wire["shape"],
            },
        )

    return StreamingResponse(
        emit(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
