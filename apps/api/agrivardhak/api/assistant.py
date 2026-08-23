"""Assistant, decisions and approvals — FR-807, FR-705…710, API-05.

The endpoints that make the system usable rather than merely correct:

* ``POST /assistant/ask`` and its SSE twin — the CEO's question becomes a Decision Packet
* ``GET  /decisions`` / ``/decisions/{id}`` — history, with the frozen evidence behind it
* ``POST /recommendations/{id}/approve|reject|review|execute`` — the human-in-the-loop gate
* ``GET  /risk-register`` — the standing view of what could go wrong and who is exposed

Two things here are load-bearing rather than incidental.

**Streaming is section-by-section, in the packet's fixed order (FR-801).** Not token-by-token.
The unit a CEO reads is a section, and a section either has its evidence or it does not
exist yet; streaming half-formed prose would show claims before the numbers that justify
them.

**The approval endpoints do no authorization of their own.** They resolve the scope, load
the row, and hand both to :mod:`agrivardhak.orchestrator.lifecycle`, which owns every rule
about who may approve what. One enforcement point, so a new endpoint cannot accidentally
open a second door into ``EXECUTED``.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agrivardhak.api.auth import CurrentScope
from agrivardhak.api.scope import ContextScope, ScopeViolation
from agrivardhak.config import get_settings
from agrivardhak.db.session import get_session
from agrivardhak.domain import enums
from agrivardhak.domain.models.decisions import (
    Approval,
    EvidenceSnapshot,
    Intervention,
    Outcome,
    Recommendation,
)
from agrivardhak.domain.models.decisions import (
    DecisionPacket as DecisionPacketRow,
)
from agrivardhak.domain.models.market import RiskRegisterEntry
from agrivardhak.domain.models.operations import AuditRecord
from agrivardhak.learning import attribution
from agrivardhak.orchestrator import briefing as briefing_service
from agrivardhak.orchestrator import engine, lifecycle
from agrivardhak.orchestrator.packet import DecisionPacket

router = APIRouter(prefix="/api/v1", tags=["assistant"])

SessionDep = Annotated[Session, Depends(get_session)]

#: Cap on question length. Not a security control — the question never reaches a model as
#: instructions — but an unbounded string on a public endpoint is an easy way to waste a
#: database round trip.
MAX_QUESTION_CHARS = 500


def _require_org(scope: ContextScope) -> uuid.UUID:
    if not scope.is_org_staff or scope.organization_id is None:
        raise ScopeViolation(
            "The FPO assistant answers on behalf of the collective. A farmer account gets "
            "the farmer assistant, which sees only their own farm (INV-5)."
        )
    return scope.organization_id


def _question(body: dict[str, Any]) -> str:
    question = str(body.get("question", "")).strip()
    if not question:
        raise HTTPException(status_code=422, detail="question is required")
    return question[:MAX_QUESTION_CHARS]


# --------------------------------------------------------------------------- ask


@router.post("/assistant/ask")
def ask(
    session: SessionDep, scope: CurrentScope, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Generate a Decision Packet. Everything it proposes lands at SUGGESTED (INV-1)."""
    _require_org(scope)
    settings = get_settings()
    result = engine.ask(
        session,
        scope=scope,
        question=_question(body),
        season=body.get("season"),
        confidence_floor=settings.confidence_floor,
        model_id=settings.orchestrator_model if settings.anthropic_api_key else "deterministic",
        narrate=bool(settings.anthropic_api_key) and not settings.use_fixtures,
    )
    session.commit()
    return {
        "packet_id": str(result.packet_row_id),
        "snapshot_id": str(result.snapshot_id),
        "content_hash": result.content_hash,
        "plan": result.plan,
        "elapsed_ms": result.elapsed_ms,
        "recommendation_ids": [str(r) for r in result.recommendation_ids],
        "packet": json.loads(result.packet.model_dump_json()),
    }


@router.post("/assistant/ask/stream")
def ask_stream(
    session: SessionDep, scope: CurrentScope, body: dict[str, Any] = Body(...)
) -> StreamingResponse:
    """Same answer, streamed a section at a time in the packet's fixed order (API-05).

    The work is not actually incremental — the modules run, then reconciliation decides, then
    sections exist. What streaming buys is that a CEO sees Situation while the rest renders,
    instead of six seconds of a spinner. Pretending the sections were computed one by one
    would be a lie told by the transport layer.
    """
    _require_org(scope)
    settings = get_settings()
    question = _question(body)

    def emit() -> Iterator[str]:
        yield _sse("status", {"state": "planning", "question": question})
        result = engine.ask(
            session,
            scope=scope,
            question=question,
            season=body.get("season"),
            confidence_floor=settings.confidence_floor,
            model_id=settings.orchestrator_model if settings.anthropic_api_key else "deterministic",
            narrate=bool(settings.anthropic_api_key) and not settings.use_fixtures,
        )
        session.commit()
        yield _sse(
            "status",
            {"state": "modules_complete", "plan": result.plan, "elapsed_ms": result.elapsed_ms},
        )
        body_json = json.loads(result.packet.model_dump_json())
        for section in DecisionPacket.SECTION_ORDER:
            yield _sse("section", {"section": section, "content": body_json.get(section)})
        if result.packet.overrides:
            yield _sse("section", {"section": "overrides", "content": body_json["overrides"]})
        yield _sse(
            "done",
            {
                "packet_id": str(result.packet_row_id),
                "snapshot_id": str(result.snapshot_id),
                "content_hash": result.content_hash,
                "recommendation_ids": [str(r) for r in result.recommendation_ids],
            },
        )

    return StreamingResponse(
        emit(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


# --------------------------------------------------------------------------- decisions


@router.get("/decisions")
def decisions(session: SessionDep, scope: CurrentScope, limit: int = 20) -> dict[str, Any]:
    org_id = _require_org(scope)
    rows = list(
        session.execute(
            select(DecisionPacketRow)
            .where(DecisionPacketRow.organization_id == org_id)
            .order_by(DecisionPacketRow.generated_at.desc())
            .limit(min(limit, 100))
        ).scalars()
    )
    return {
        "decisions": [
            {
                "id": str(row.id),
                "question": row.question,
                "generated_at": row.generated_at.isoformat(),
                "overall_confidence": round(float(row.overall_confidence), 3),
                "model_id": row.model_id,
                "recommendations": session.execute(
                    select(func.count())
                    .select_from(Recommendation)
                    .where(Recommendation.packet_id == row.id)
                ).scalar_one(),
            }
            for row in rows
        ]
    }


@router.get("/decisions/{packet_id}")
def decision(packet_id: uuid.UUID, session: SessionDep, scope: CurrentScope) -> dict[str, Any]:
    org_id = _require_org(scope)
    row = session.get(DecisionPacketRow, packet_id)
    if row is None or row.organization_id != org_id:
        raise HTTPException(status_code=404, detail="decision not found")
    snapshot = session.get(EvidenceSnapshot, row.snapshot_id)
    recommendations = list(
        session.execute(select(Recommendation).where(Recommendation.packet_id == row.id)).scalars()
    )
    return {
        "id": str(row.id),
        "question": row.question,
        "generated_at": row.generated_at.isoformat(),
        "packet": row.body,
        "evidence_snapshot": {
            "id": str(row.snapshot_id),
            "content_hash": snapshot.content_hash if snapshot else None,
            "captured_at": snapshot.captured_at.isoformat() if snapshot else None,
            "module_versions": (snapshot.payload or {}).get("module_versions") if snapshot else {},
            "coefficients": (snapshot.payload or {}).get("coefficients") if snapshot else {},
        },
        "recommendations": [_recommendation_payload(session, r) for r in recommendations],
    }


@router.get("/decisions/{packet_id}/replay")
def replay(packet_id: uuid.UUID, session: SessionDep, scope: CurrentScope) -> dict[str, Any]:
    """Rebuild the answer from frozen bytes and show whether it still matches (INV-2).

    This is the endpoint that makes "explainable forever" checkable rather than asserted. If
    the replay diverges from what was stored, something that should have been versioned was
    changed — and the honest thing is to show that, not to hide it.
    """
    org_id = _require_org(scope)
    row = session.get(DecisionPacketRow, packet_id)
    if row is None or row.organization_id != org_id:
        raise HTTPException(status_code=404, detail="decision not found")
    replayed = engine.replay(session, row.snapshot_id)
    original = row.body or {}
    matches = {
        section: replayed.get(section) == original.get(section)
        for section in ("situation", "impact", "recommendation", "overrides")
    }
    return {
        "packet_id": str(row.id),
        "snapshot_id": str(row.snapshot_id),
        "replayed": replayed,
        "matches_original": matches,
        "identical": all(matches.values()),
    }


# --------------------------------------------------------------------------- approvals


def _load(session: Session, recommendation_id: uuid.UUID, org_id: uuid.UUID) -> Recommendation:
    row = session.get(Recommendation, recommendation_id)
    if row is None or row.organization_id != org_id:
        raise HTTPException(status_code=404, detail="recommendation not found")
    return row


@router.get("/recommendations")
def recommendations(
    session: SessionDep, scope: CurrentScope, status: str | None = None, limit: int = 50
) -> dict[str, Any]:
    org_id = _require_org(scope)
    stmt = (
        select(Recommendation)
        .where(Recommendation.organization_id == org_id)
        .order_by(Recommendation.created_at.desc())
        .limit(min(limit, 200))
    )
    if status:
        stmt = stmt.where(Recommendation.status == enums.RecommendationStatus(status))
    rows = list(session.execute(stmt).scalars())
    return {"recommendations": [_recommendation_payload(session, r) for r in rows]}


@router.post("/recommendations/{recommendation_id}/review")
def review(
    recommendation_id: uuid.UUID,
    session: SessionDep,
    scope: CurrentScope,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    org_id = _require_org(scope)
    row = _load(session, recommendation_id, org_id)
    try:
        lifecycle.review(
            session,
            recommendation=row,
            reviewer_user_id=scope.actor_user_id,
            note=body.get("note"),
        )
    except lifecycle.LifecycleViolation as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return _recommendation_payload(session, row)


@router.post("/recommendations/{recommendation_id}/approve")
def approve(
    recommendation_id: uuid.UUID,
    session: SessionDep,
    scope: CurrentScope,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """FR-705. Approve, or approve with a modified value — the common real answer."""
    org_id = _require_org(scope)
    row = _load(session, recommendation_id, org_id)
    modified_value = body.get("approved_value_paise")
    decision_kind = (
        enums.ApprovalDecision.APPROVED_WITH_MODIFICATION
        if modified_value is not None
        else enums.ApprovalDecision.APPROVED
    )
    try:
        result = lifecycle.decide(
            session,
            recommendation=row,
            approver_user_id=scope.actor_user_id,
            roles=frozenset(scope.roles),
            decision=decision_kind,
            rationale=body.get("rationale"),
            approved_value_paise=int(modified_value) if modified_value is not None else None,
        )
    except lifecycle.LifecycleViolation as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return {
        **_recommendation_payload(session, row),
        "approval_id": str(result.approval_id),
        "was_modified": result.was_modified,
        "approved_value_paise": result.approved_value_paise,
    }


@router.post("/recommendations/{recommendation_id}/reject")
def reject(
    recommendation_id: uuid.UUID,
    session: SessionDep,
    scope: CurrentScope,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    org_id = _require_org(scope)
    row = _load(session, recommendation_id, org_id)
    try:
        lifecycle.decide(
            session,
            recommendation=row,
            approver_user_id=scope.actor_user_id,
            roles=frozenset(scope.roles),
            decision=enums.ApprovalDecision.REJECTED,
            rationale=body.get("rationale"),
        )
    except lifecycle.LifecycleViolation as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return _recommendation_payload(session, row)


@router.post("/recommendations/{recommendation_id}/execute")
def execute(
    recommendation_id: uuid.UUID,
    session: SessionDep,
    scope: CurrentScope,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Refused without an Approval row, whatever the caller sends (INV-1)."""
    org_id = _require_org(scope)
    row = _load(session, recommendation_id, org_id)
    try:
        intervention = lifecycle.execute(
            session,
            recommendation=row,
            executed_by=scope.actor_user_id,
            action_taken=body.get("action_taken") or row.title,
            cost_paise=body.get("cost_paise"),
        )
    except lifecycle.LifecycleViolation as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return {**_recommendation_payload(session, row), "intervention_id": str(intervention.id)}


def _recommendation_payload(session: Session, row: Recommendation) -> dict[str, Any]:
    approvals = list(
        session.execute(
            select(Approval)
            .where(Approval.recommendation_id == row.id)
            .order_by(Approval.decided_at)
        ).scalars()
    )
    return {
        "id": str(row.id),
        "packet_id": str(row.packet_id) if row.packet_id else None,
        "type": row.type.value,
        "title": row.title,
        "reasoning": row.reasoning,
        "status": row.status.value,
        "confidence": round(float(row.confidence), 3),
        "recommended_value_paise": row.recommended_value,
        "value_unit": row.value_unit,
        "expected_impact": row.expected_impact,
        "risks": row.risks,
        "alternatives": row.alternatives,
        "evidence": row.evidence,
        "snapshot_id": str(row.snapshot_id),
        "created_at": row.created_at.isoformat(),
        "approvals": [
            {
                "id": str(a.id),
                "decision": a.decision.value,
                "role_exercised": a.role_exercised.value,
                "approved_value_paise": a.approved_value,
                "rationale": a.rationale,
                "decided_at": a.decided_at.isoformat(),
            }
            for a in approvals
        ],
        # UI-11: what a human must still do before anything happens.
        "awaiting": _awaiting(session, row),
    }


def _awaiting(session: Session, row: Recommendation) -> str | None:
    """What a human must still do. ``None`` once the loop is closed.

    ``EXECUTED`` is not the end of the line — an executed action still owes an outcome
    record before it can be attributed (INV-7). But it stops owing one as soon as that
    outcome exists, and the earlier version of this function never checked: it derived the
    answer from ``status`` alone, so a fully closed loop from last season still rendered
    "Awaiting an outcome record. Nothing has happened yet." underneath its own recorded
    result.
    """
    if row.status is enums.RecommendationStatus.EXECUTED:
        recorded = session.execute(
            select(Outcome.id)
            .join(Intervention, Outcome.intervention_id == Intervention.id)
            .where(Intervention.recommendation_id == row.id)
            .limit(1)
        ).first()
        return None if recorded else "an outcome record"
    return {
        enums.RecommendationStatus.SUGGESTED: "review or approval by an authorised role",
        enums.RecommendationStatus.REVIEWED: "approval by an authorised role",
        enums.RecommendationStatus.APPROVED: "execution, then an outcome record",
    }.get(row.status)


# --------------------------------------------------------------------------- risk register


@router.get("/risk-register")
def risk_register(session: SessionDep, scope: CurrentScope) -> dict[str, Any]:
    """FR-552, UI-08. What could go wrong, who is exposed, and what would reduce it."""
    org_id = _require_org(scope)
    rows = list(
        session.execute(
            select(RiskRegisterEntry)
            .where(RiskRegisterEntry.organization_id == org_id)
            .order_by(RiskRegisterEntry.created_at.desc())
        ).scalars()
    )
    return {
        "entries": [
            {
                "id": str(row.id),
                "domain": row.domain.value,
                "title": row.title,
                "likelihood": row.likelihood.value,
                "impact": row.impact.value,
                "status": row.status.value,
                "farmers_affected": row.farmers_affected,
                "area_affected_acres": (
                    round(float(row.area_affected_sqm) / 4046.86, 1)
                    if row.area_affected_sqm
                    else None
                ),
                "value_at_risk_paise": row.value_at_risk_paise,
                "recommended_action": row.recommended_action,
                "owner_role": row.owner_role.value if row.owner_role else None,
                "review_on": row.review_on.isoformat() if row.review_on else None,
                "detail": row.causal_chain,
                "evidence": row.evidence,
            }
            for row in rows
        ]
    }


@router.get("/audit")
def audit(session: SessionDep, scope: CurrentScope, limit: int = 50) -> dict[str, Any]:
    """FR-709 / SAF-10. The decision trail exists so a farmer can contest a decision."""
    org_id = _require_org(scope)
    rows = list(
        session.execute(
            select(AuditRecord)
            .where(AuditRecord.organization_id == org_id)
            .order_by(AuditRecord.occurred_at.desc())
            .limit(min(limit, 200))
        ).scalars()
    )
    return {
        "records": [
            {
                "id": str(row.id),
                "action": row.action,
                "actor_kind": row.actor_kind.value,
                "authority": row.authority,
                "subject_type": row.subject_type,
                "subject_id": str(row.subject_id) if row.subject_id else None,
                "occurred_at": row.occurred_at.isoformat(),
                "detail": row.detail,
                "evidence_ref": row.evidence_ref,
            }
            for row in rows
        ]
    }


# --------------------------------------------------------------------------- briefing


@router.get("/briefing")
def briefing(session: SessionDep, scope: CurrentScope) -> dict[str, Any]:
    """FR-811. What a CEO sees before they have asked anything.

    Leads with what needs a decision, because that is the only thing on the screen that
    stalls if it is ignored.
    """
    org_id = _require_org(scope)
    return briefing_service.build(session, organization_id=org_id).as_dict()


@router.get("/impact")
def impact(session: SessionDep, scope: CurrentScope) -> dict[str, Any]:
    """FR-1201…1203. What the loop has recorded — including what it could not attribute.

    The unattributable count is reported alongside the successes on purpose. A panel showing
    only what worked would be measuring our own selection rather than our impact (SAF-12).
    """
    org_id = _require_org(scope)
    return attribution.summarise(session, organization_id=org_id)


# --------------------------------------------------------------------------- farmer


@router.get("/farmer/today")
def farmer_today(session: SessionDep, scope: CurrentScope) -> dict[str, Any]:
    """The farmer's own view — INV-5.

    Note what this endpoint does *not* do: it does not filter an organization-wide result
    down to one farmer. It builds a farmer-scoped result from the start, so org-internal rows
    are never in the result set at all and no rendering bug can leak them.

    Only content marked shared with members crosses the boundary. A recommendation about
    this farmer's own crop cycle is theirs; the collective's buyer negotiations are not.
    """
    if scope.farmer_id is None:
        raise ScopeViolation(
            "This is the farmer view. Organization staff have the FPO console instead."
        )
    farmer_id = scope.farmer_id

    from agrivardhak.domain.models.crops import Crop, CropCycle, Variety
    from agrivardhak.domain.models.land import Farm, Plot
    from agrivardhak.domain.models.market import Lot, LotItem
    from agrivardhak.domain.models.organization import Farmer
    from agrivardhak.provenance import resolver

    farmer = session.get(Farmer, farmer_id)
    if farmer is None:
        raise HTTPException(status_code=404, detail="farmer not found")

    now = dt.datetime.now(dt.UTC)
    cycles = list(
        session.execute(
            select(CropCycle, Crop.name, Variety.name)
            .join(Variety, CropCycle.variety_id == Variety.id)
            .join(Crop, Variety.crop_id == Crop.id)
            .join(Plot, CropCycle.plot_id == Plot.id)
            .join(Farm, Plot.farm_id == Farm.id)
            .where(
                Farm.operator_farmer_id == farmer_id,
                CropCycle.status.in_(
                    (
                        enums.CropCycleStatus.SOWN,
                        enums.CropCycleStatus.GROWING,
                        enums.CropCycleStatus.HARVEST_READY,
                    )
                ),
            )
        ).all()
    )

    crops = []
    for cycle, crop_name, variety_name in cycles:
        health = resolver.resolve(
            session,
            subject_type="crop_cycle",
            subject_id=cycle.id,
            attribute="crop_health_pct",
            as_of=now,
        )
        crops.append(
            {
                "id": str(cycle.id),
                "crop": crop_name,
                "variety": variety_name,
                "area_acres": round(float(cycle.area_sqm) / 4046.86, 2),
                "sown_on": cycle.sowing_date.isoformat() if cycle.sowing_date else None,
                "expected_harvest": (
                    cycle.expected_harvest_date.isoformat() if cycle.expected_harvest_date else None
                ),
                "health_pct": float(health.value) if health and health.value else None,
                "health_confidence": round(health.confidence, 3) if health else None,
                "health_observed_at": health.observed_at.isoformat() if health else None,
            }
        )

    contributions = list(
        session.execute(
            select(LotItem, Lot.label, Crop.name)
            .join(Lot, LotItem.lot_id == Lot.id)
            .join(Crop, Lot.crop_id == Crop.id)
            .where(LotItem.farmer_id == farmer_id)
        ).all()
    )

    return {
        "farmer": {
            "id": str(farmer.id),
            "name": farmer.full_name,
            "village": farmer.village,
            "block": farmer.block,
            "is_synthetic": farmer.is_synthetic,
        },
        "crops": crops,
        "lot_contributions": [
            {
                "lot": label,
                "crop": crop_name,
                "quantity_kg": float(item.quantity_kg),
                "grade": item.grade.value if item.grade else None,
            }
            for item, label, crop_name in contributions
        ],
        # The boundary, stated on the response itself rather than only in a doc.
        "boundary_note": (
            "You see your own farm. The collective's buyer negotiations, member list and "
            "internal decisions are not part of this view (INV-5)."
        ),
    }
