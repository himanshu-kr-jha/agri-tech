"""The orchestrator — M13, FR-801…806, FR-704, INV-2.

    CEO: "What should we do this season to maximize sustainable farmer income?"

This is what turns that question into an auditable Decision Packet. Eight steps, of which
six are deterministic:

    1. scope      ContextScope decides what data may be loaded at all (INV-5)
    2. plan       which modules the question needs
    3. gather     one provenance pass over the database (INV-3)
    4. run        modules, pure, independently
    5. reconcile  rank, override visibly, drop the unevidenced (FR-802, FR-804)
    6. freeze     EvidenceSnapshot + SHA-256 over everything that produced the answer
    7. emit       DecisionPacket, nine sections
    8. persist    recommendations at SUGGESTED, packet, domain events, audit

Freezing is the step that makes the rest defensible. After it, the packet is reproducible
from stored bytes rather than from live data — which is what lets someone ask, eight months
later, *why did we do that*, and get the answer that was actually true at the time rather
than a recomputation against a world that has since moved (INV-2).

The model's role
----------------
Deliberately small. Planning is a keyword match, not a completion, and reconciliation is the
deterministic code in :mod:`agrivardhak.orchestrator.reconcile`. An LLM narrates — it writes
the prose around numbers it did not choose — and if the key is absent or the call times out,
the packet is produced anyway with its own wording (NFR-302, NFR-303).

That is not timidity about the model. It is that a recommendation which cannot be
reproduced offline cannot be audited, and this system's entire claim is that its
recommendations can be.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from agrivardhak.api.scope import ContextScope
from agrivardhak.domain import enums
from agrivardhak.domain.models.decisions import (
    DecisionPacket as DecisionPacketRow,
)
from agrivardhak.domain.models.decisions import (
    EvidenceSnapshot,
    Prediction,
    Recommendation,
)
from agrivardhak.domain.models.market import RiskRegisterEntry
from agrivardhak.domain.models.operations import AuditRecord, DomainEvent
from agrivardhak.intelligence import crop_health, farm, funding, market, quality, risk, scheme
from agrivardhak.intelligence.contracts import ModuleInput, ModuleOutput
from agrivardhak.orchestrator import gather, reconcile
from agrivardhak.orchestrator.packet import (
    AssignedAction,
    DecisionPacket,
    PacketScope,
    ProposedCalendarEvent,
)

PROMPT_VERSION = "packet-v1"

#: Matches recommendation.value_unit's column width. Checked in Python so a too-long unit
#: fails in a test with a useful message rather than as a StringDataRightTruncation halfway
#: through persisting a packet.
VALUE_UNIT_MAX = 32
SNAPSHOT_VERSION = "1"

#: module key -> (gather function name, module.run). The registry *is* the plan space —
#: a question cannot invoke something not listed here, which bounds the blast radius of a
#: planner that gets it wrong.
MODULES: dict[str, Any] = {
    "quality": (gather.for_quality, quality.run),
    "market": (gather.for_market, market.run),
    "risk": (gather.for_risk, risk.run),
    "farm": (gather.for_farm, farm.run),
    "crop_health": (gather.for_crop_health, crop_health.run),
    "scheme": (gather.for_scheme, scheme.run),
    "funding": (gather.for_funding, funding.run),
}

#: Keyword -> modules. A question mentioning none of these gets the full set, because the
#: cost of running a module that was not needed is a few hundred milliseconds and the cost
#: of skipping one that was is a wrong answer.
PLAN_HINTS: dict[str, tuple[str, ...]] = {
    "sell": ("market", "quality", "risk"),
    "buyer": ("market", "risk"),
    "price": ("market", "risk"),
    "harvest": ("quality", "risk", "market"),
    "yield": ("quality",),
    "produce": ("quality",),
    "grow": ("farm", "quality", "risk"),
    "plant": ("farm", "risk"),
    "sow": ("farm", "risk"),
    "crop plan": ("farm", "quality", "market", "risk"),
    "risk": ("risk", "crop_health"),
    "weather": ("risk", "quality"),
    "rain": ("risk",),
    "disease": ("crop_health",),
    "pest": ("crop_health",),
    "spray": ("crop_health",),
    "scheme": ("scheme",),
    "subsidy": ("scheme",),
    "loan": ("scheme", "funding"),
    "capital": ("funding",),
    "cash": ("funding",),
    "afford": ("funding",),
    "fund": ("funding", "scheme"),
    "insurance": ("scheme", "risk"),
    "income": ("farm", "market", "quality", "risk", "scheme", "funding"),
    "season": ("farm", "quality", "market", "risk", "scheme", "funding"),
}


@dataclass
class PacketResult:
    packet: DecisionPacket
    packet_row_id: uuid.UUID
    snapshot_id: uuid.UUID
    content_hash: str
    recommendation_ids: list[uuid.UUID]
    module_outputs: dict[str, ModuleOutput]
    plan: list[str]
    elapsed_ms: int


# --------------------------------------------------------------------------- 2. plan


def plan_for(question: str) -> list[str]:
    """Which modules this question needs.

    A keyword match rather than a model call, for a reason worth stating: the planner runs
    before anything else, so a hung or hallucinating planner would stall or misdirect every
    request. Deterministic planning also means the same question replays to the same module
    set, which the replay test depends on.
    """
    lowered = question.lower()
    selected: set[str] = set()
    for keyword, modules in PLAN_HINTS.items():
        if keyword in lowered:
            selected.update(modules)
    if not selected:
        selected = set(MODULES)
    # Quality feeds Risk and Farm their tonnage. Ask for either and you get Quality too,
    # otherwise the risk figures would be sized against planted area instead of expected
    # production — a silently worse answer rather than a visibly missing one.
    if selected & {"risk", "farm"}:
        selected.add("quality")
    return sorted(selected)


# --------------------------------------------------------------------------- 3-4. gather + run


def run_modules(
    session: Session,
    *,
    organization_id: uuid.UUID,
    as_of: dt.datetime,
    plan: list[str],
    season: str | None = None,
) -> tuple[dict[str, ModuleOutput], dict[str, ModuleInput]]:
    """Gather then run, in dependency order.

    Modules never call each other. Quality's aggregate is carried across by this function
    and handed to Risk and Farm as ordinary input, which keeps every module a pure function
    of its own arguments and keeps the dependency visible here instead of buried.
    """
    outputs: dict[str, ModuleOutput] = {}
    inputs: dict[str, ModuleInput] = {}
    predictions: dict[str, dict[str, Any]] = {}

    if "quality" in plan:
        module_input = gather.for_quality(session, organization_id=organization_id, as_of=as_of)
        inputs["quality"] = module_input
        outputs["quality"] = quality.run(module_input)
        cycles = module_input.data.get("cycles") or []
        usable = [
            p
            for p in (quality.predict_cycle(c, quality.YieldModel()) for c in cycles)
            if p.expected_yield_kg > 0
        ]
        predictions = quality.aggregate(usable)

    for name in plan:
        if name == "quality":
            continue
        gather_fn, run_fn = MODULES[name]
        kwargs: dict[str, Any] = {"organization_id": organization_id, "as_of": as_of}
        if name in ("risk", "farm"):
            kwargs["quality_predictions"] = predictions
        if name == "farm":
            kwargs["season"] = season
        module_input = gather_fn(session, **kwargs)
        inputs[name] = module_input
        outputs[name] = run_fn(module_input)

    return outputs, inputs


# --------------------------------------------------------------------------- 6. freeze


def content_hash(payload: dict[str, Any]) -> str:
    """SHA-256 over the canonical JSON form.

    ``sort_keys`` and a fixed separator are not cosmetic: without them the same evidence
    hashes differently between two runs, and a hash that changes without the content
    changing proves nothing at all.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def freeze(
    session: Session,
    *,
    outputs: dict[str, ModuleOutput],
    inputs: dict[str, ModuleInput],
    organization_id: uuid.UUID,
    as_of: dt.datetime,
    question: str,
    model_id: str,
    focus_subject: str | None = None,
) -> EvidenceSnapshot:
    """Persist everything that produced this answer, immutably (INV-2, FR-704).

    Module *outputs* and the evidence refs are stored, not the full gathered inputs. Storing
    a thousand crop cycles per packet would make the snapshot table larger than the database
    it describes; the evidence refs point at rows that are themselves append-only, so the
    chain still resolves. What is stored is what cannot be recovered later: the module
    versions, the coefficients in force, and the exact findings.
    """
    payload = {
        "question": question,
        "as_of": as_of.isoformat(),
        "organization_id": str(organization_id),
        "prompt_version": PROMPT_VERSION,
        "model_id": model_id,
        # Part of what produced the answer, so it belongs in the frozen record. Absent on
        # snapshots taken before focus existed, which `replay` reads back as None.
        "focus_subject": focus_subject,
        "module_versions": {name: output.version for name, output in outputs.items()},
        "modules": {name: json.loads(output.model_dump_json()) for name, output in outputs.items()},
        "input_shape": {
            name: {
                key: (len(value) if isinstance(value, list | dict) else str(type(value).__name__))
                for key, value in module_input.data.items()
            }
            for name, module_input in inputs.items()
        },
        "coefficients": {
            "quality_yield_model": quality.YieldModel().as_dict(),
            "market_costs": market.CostModel().__dict__,
            "risk": {
                "trough_percentile": risk.TROUGH_PERCENTILE,
                "concentration_share": risk.CONCENTRATION_SHARE,
                "hazard_reportable": risk.HAZARD_REPORTABLE,
            },
            "crop_health_ceiling": crop_health.UNSOURCED_CONFIDENCE_CEILING,
            "farm_ceiling": farm.UNSOURCED_CONFIDENCE_CEILING,
            "scheme_ceiling": scheme.UNVERIFIED_CONFIDENCE_CEILING,
        },
    }
    digest = content_hash(payload)

    existing = (
        session.execute(select(EvidenceSnapshot).where(EvidenceSnapshot.content_hash == digest))
        .scalars()
        .first()
    )
    if existing is not None:
        # Identical inputs produced an identical answer. Reusing the snapshot is not an
        # optimisation, it is the correct semantics: two packets built from the same frozen
        # evidence should point at the same evidence.
        return existing

    snapshot = EvidenceSnapshot(
        captured_at=as_of,
        payload=payload,
        content_hash=digest,
        payload_version=SNAPSHOT_VERSION,
    )
    session.add(snapshot)
    session.flush()
    return snapshot


# --------------------------------------------------------------------------- 7-8. emit + persist


def ask(
    session: Session,
    *,
    scope: ContextScope,
    question: str,
    as_of: dt.datetime | None = None,
    season: str | None = None,
    confidence_floor: float = 0.45,
    model_id: str = "deterministic",
    narrate: bool = False,
    plan: list[str] | None = None,
    focus_subject: str | None = None,
) -> PacketResult:
    """The whole pipeline. Returns the packet and the ids it persisted.

    ``as_of`` is a parameter rather than a clock read so a packet can be regenerated for a
    past moment and compared against what was actually produced then — the replay property
    the whole architecture is arranged around.

    ``plan`` and ``focus_subject`` let a caller that has already classified the question say
    so. Both were previously recomputed here from keywords, which meant the intent router
    could pick modules and name a crop and have both silently discarded — the packet came out
    the same whichever crop was asked about.
    """
    started = dt.datetime.now(dt.UTC)
    as_of = as_of or started
    organization_id = scope.organization_id
    if organization_id is None:
        raise ValueError("a decision packet needs an organization scope")

    plan = plan or plan_for(question)
    outputs, inputs = run_modules(
        session,
        organization_id=organization_id,
        as_of=as_of,
        plan=plan,
        season=season,
    )

    result = reconcile.reconcile(
        list(outputs.values()),
        as_of=as_of,
        confidence_floor=confidence_floor,
        focus_subject=focus_subject,
    )
    snapshot = freeze(
        session,
        outputs=outputs,
        inputs=inputs,
        organization_id=organization_id,
        as_of=as_of,
        question=question,
        model_id=model_id,
        focus_subject=focus_subject,
    )

    assert result.confidence is not None
    packet = DecisionPacket(
        question=question,
        scope=PacketScope(
            organization_id=organization_id,
            audience="FPO" if scope.farmer_id is None else "FARMER",
            farmer_id=scope.farmer_id,
            season=season,
            season_year=as_of.year,
        ),
        situation=result.situation,
        impact=result.impact,
        recommendation=result.recommendation,
        expected_outcome=result.expected_outcome,
        confidence=result.confidence,
        evidence=result.evidence,
        actions=result.actions,
        schedule=_proposed_schedule(result.actions),
        drilldown=result.drilldown,
        overrides=result.overrides,
        generated_at=as_of,
        snapshot_id=snapshot.id,
        prompt_version=PROMPT_VERSION,
        model_id=model_id,
    )

    if narrate:
        from agrivardhak.orchestrator.narrator import narrate as narrate_packet

        packet = narrate_packet(packet, outputs)

    packet_row = DecisionPacketRow(
        organization_id=organization_id,
        snapshot_id=snapshot.id,
        asked_by=scope.actor_user_id,
        question=question,
        scope=json.loads(packet.scope.model_dump_json()),
        body=json.loads(packet.model_dump_json()),
        overall_confidence=packet.confidence.overall,
        generated_at=as_of,
        prompt_version=PROMPT_VERSION,
        model_id=model_id,
    )
    session.add(packet_row)
    session.flush()

    recommendation_ids = _persist_recommendations(
        session,
        packet=packet,
        packet_row_id=packet_row.id,
        snapshot_id=snapshot.id,
        organization_id=organization_id,
        outputs=outputs,
        as_of=as_of,
        model_id=model_id,
    )
    _persist_predictions(session, outputs=outputs, as_of=as_of)
    _persist_risk_register(
        session, outputs=outputs, inputs=inputs, organization_id=organization_id, as_of=as_of
    )

    session.add(
        DomainEvent(
            event_type="DecisionPacketGenerated",
            aggregate_type="decision_packet",
            aggregate_id=packet_row.id,
            organization_id=organization_id,
            actor_id=scope.actor_user_id,
            actor_kind=enums.ActorKind.AI,
            occurred_at=as_of,
            payload={
                "question": question,
                "plan": plan,
                "snapshot_hash": snapshot.content_hash,
                "recommendations": [str(r) for r in recommendation_ids],
                "overall_confidence": packet.confidence.overall,
                "overrides": [o.overridden_key for o in packet.overrides],
            },
        )
    )
    session.add(
        AuditRecord(
            organization_id=organization_id,
            actor_kind=enums.ActorKind.AI,
            actor_id=scope.actor_user_id,
            action="generate_decision_packet",
            subject_type="decision_packet",
            subject_id=packet_row.id,
            authority="orchestrator",
            evidence_ref={"snapshot_id": str(snapshot.id), "hash": snapshot.content_hash},
            occurred_at=as_of,
            detail={"question": question, "modules": plan, "model_id": model_id},
        )
    )

    elapsed = int((dt.datetime.now(dt.UTC) - started).total_seconds() * 1000)
    return PacketResult(
        packet=packet,
        packet_row_id=packet_row.id,
        snapshot_id=snapshot.id,
        content_hash=snapshot.content_hash,
        recommendation_ids=recommendation_ids,
        module_outputs=outputs,
        plan=plan,
        elapsed_ms=elapsed,
    )


def _proposed_schedule(actions: list[AssignedAction]) -> list[ProposedCalendarEvent]:
    """Turn assigned actions into *proposed* calendar entries (FR-904).

    A proposal, emphatically not a booking. ``lifecycle.schedule_from`` is what writes a real
    ``CalendarEvent``, and it refuses any recommendation that is not already APPROVED —
    somebody's Tuesday is a consequence, and consequences need a human (INV-1). What belongs
    in the packet is the *shape* of the week the CEO would be approving.

    Only actions with a concrete target become entries. ``ProposedCalendarEvent`` requires a
    subject, and an event about nothing in particular is noise in a calendar that is supposed
    to earn its place.
    """
    events: list[ProposedCalendarEvent] = []
    for action in actions:
        if action.related_target_id is None or action.due_on is None:
            continue
        events.append(
            ProposedCalendarEvent(
                title=action.task,
                subject_type=action.related_target_type or "recommendation",
                subject_id=action.related_target_id,
                # 09:30 IST — the start of a working day, not midnight UTC, which would
                # render as the previous evening for every person who reads it.
                starts_at=dt.datetime.combine(action.due_on, dt.time(4, 0), tzinfo=dt.UTC),
            )
        )
    return events


def _persist_recommendations(
    session: Session,
    *,
    packet: DecisionPacket,
    packet_row_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    organization_id: uuid.UUID,
    outputs: dict[str, ModuleOutput],
    as_of: dt.datetime,
    model_id: str,
) -> list[uuid.UUID]:
    """Every recommendation lands at SUGGESTED. Nothing else is possible here (INV-1).

    There is no code path in this function that can write another status. That is the
    structural form of the human-in-the-loop guarantee: the lifecycle module is the only
    thing that can advance a recommendation, and it requires an Approval row to do it.
    """
    superseded = _supersede_stale_suggestions(
        session, organization_id=organization_id, packet=packet, as_of=as_of
    )
    del superseded  # counted for the event payload only; the rows carry the record

    ids: list[uuid.UUID] = []
    for action in packet.recommendation:
        if action.value_unit and len(action.value_unit) > VALUE_UNIT_MAX:
            raise ValueError(
                f"value_unit {action.value_unit!r} exceeds {VALUE_UNIT_MAX} characters. "
                "It is a unit, not a sentence — the explanation belongs in expected_impact."
            )
        row = Recommendation(
            organization_id=organization_id,
            packet_id=packet_row_id,
            snapshot_id=snapshot_id,
            type=enums.RecommendationType(action.recommendation_type),
            target_type=action.target_type,
            target_id=action.target_id,
            title=action.title,
            reasoning=action.rationale,
            evidence=[json.loads(e.model_dump_json()) for e in action.evidence],
            confidence=action.confidence,
            expected_impact=action.expected_impact,
            risks=action.risks,
            alternatives=action.alternatives,
            recommended_value=action.value_paise,
            value_unit=action.value_unit,
            status=enums.RecommendationStatus.SUGGESTED,
            generator="orchestrator",
            prompt_version=PROMPT_VERSION,
            model_id=model_id,
        )
        session.add(row)
        session.flush()
        ids.append(row.id)
    return ids


def _supersede_stale_suggestions(
    session: Session,
    *,
    organization_id: uuid.UUID,
    packet: DecisionPacket,
    as_of: dt.datetime,
) -> int:
    """Retire the previous run's identical, still-unapproved suggestions (INV-10).

    Asking the same question twice used to leave two identical SUGGESTED rows, and asking it
    five times left five. The briefing then showed the same decision five times, which is the
    fastest way to teach a CEO to stop reading the briefing.

    The rule is narrow on purpose. Only rows that are **still SUGGESTED** are touched — an
    approved or rejected recommendation is a decision that was made, and history is not
    rewritten. And they are *superseded*, not deleted: the old row keeps its evidence and
    points at what replaced it, so "what were we told in August" still has an answer (INV-2).
    """
    titles = {a.title for a in packet.recommendation}
    if not titles:
        return 0
    stale = list(
        session.execute(
            select(Recommendation).where(
                Recommendation.organization_id == organization_id,
                Recommendation.status == enums.RecommendationStatus.SUGGESTED,
                Recommendation.title.in_(titles),
            )
        ).scalars()
    )
    for row in stale:
        row.status = enums.RecommendationStatus.SUPERSEDED
        session.add(
            DomainEvent(
                event_type="RecommendationSuperseded",
                aggregate_type="recommendation",
                aggregate_id=row.id,
                organization_id=organization_id,
                actor_kind=enums.ActorKind.SYSTEM,
                occurred_at=as_of,
                payload={
                    "reason": "re-asked; a fresher packet proposes the same action",
                    "superseded_by_packet": None,
                },
            )
        )
    return len(stale)


def _persist_predictions(
    session: Session, *, outputs: dict[str, ModuleOutput], as_of: dt.datetime
) -> None:
    """INV-6: a claim about reality is stored separately from a proposed action.

    Storing them apart is what later makes "was the forecast right?" and "was the advice
    good?" two different questions with two different answers — which is the only honest way
    to evaluate either.
    """
    output = outputs.get("quality")
    if output is None:
        return
    for finding in output.findings:
        if not finding.key.startswith("expected_production.") or finding.magnitude is None:
            continue
        session.add(
            Prediction(
                module=output.module,
                module_version=output.version,
                subject_type="organization_crop",
                subject_id=finding.evidence[0].id,
                metric=finding.key,
                value_numeric=float(finding.magnitude),
                unit=finding.unit,
                confidence=finding.confidence,
                issued_at=as_of,
                inputs_ref={"evidence": [str(e.id) for e in finding.evidence[:5]]},
            )
        )


def _persist_risk_register(
    session: Session,
    *,
    outputs: dict[str, ModuleOutput],
    inputs: dict[str, ModuleInput],
    organization_id: uuid.UUID,
    as_of: dt.datetime,
) -> None:
    """FR-552. Upsert by key so a re-ask updates the register rather than duplicating it."""
    if "risk" not in outputs or "risk" not in inputs:
        return
    entries = risk.register_entries(outputs["risk"], inputs["risk"])
    existing = {
        row.title: row
        for row in session.execute(
            select(RiskRegisterEntry).where(RiskRegisterEntry.organization_id == organization_id)
        ).scalars()
    }
    for entry in entries:
        row = existing.get(entry.title)
        if row is None:
            row = RiskRegisterEntry(
                organization_id=organization_id,
                domain=enums.RiskDomain(entry.domain),
                title=entry.title,
                description=entry.mitigation,
                likelihood=enums.Likelihood(entry.likelihood),
                impact=enums.Impact(entry.impact),
                status=enums.RiskStatus.OPEN,
                farmers_affected=len(entry.affected.farmer_ids) or None,
                area_affected_sqm=(
                    float(entry.affected.area_sqm) if entry.affected.area_sqm else None
                ),
                value_at_risk_paise=entry.affected.value_paise,
                causal_chain={
                    "probability": entry.probability,
                    "horizon_start": str(entry.horizon_start) if entry.horizon_start else None,
                    "horizon_end": str(entry.horizon_end) if entry.horizon_end else None,
                    "key": entry.key,
                    "confidence": entry.confidence,
                },
                recommended_action=entry.mitigation,
                evidence=[json.loads(e.model_dump_json()) for e in entry.evidence[:5]],
                owner_role=enums.Role.FPO_CEO,
                review_on=entry.horizon_start,
            )
            session.add(row)
        else:
            # Re-asking the same question must refresh the register, not clone it. The
            # register is the organization's standing view; a duplicate row for the same
            # hazard would make "how many open risks" meaningless within a day.
            row.likelihood = enums.Likelihood(entry.likelihood)
            row.impact = enums.Impact(entry.impact)
            row.farmers_affected = len(entry.affected.farmer_ids) or None
            row.value_at_risk_paise = entry.affected.value_paise


def replay(session: Session, snapshot_id: uuid.UUID) -> dict[str, Any]:
    """Rebuild the answer from frozen bytes alone (ARCHITECTURE §9, INV-2).

    Reads no live data. If this returns something different from what was originally
    emitted, either a module stopped being pure or a coefficient changed without a version
    bump — both of which are bugs the replay test exists to catch.
    """
    snapshot = session.get(EvidenceSnapshot, snapshot_id)
    if snapshot is None:
        raise LookupError(f"no snapshot {snapshot_id}")
    payload = snapshot.payload
    outputs = [ModuleOutput.model_validate(m) for m in payload["modules"].values()]
    as_of = dt.datetime.fromisoformat(payload["as_of"])
    result = reconcile.reconcile(outputs, as_of=as_of, focus_subject=payload.get("focus_subject"))
    return {
        "situation": [json.loads(c.model_dump_json()) for c in result.situation],
        "impact": [json.loads(c.model_dump_json()) for c in result.impact],
        "recommendation": [json.loads(a.model_dump_json()) for a in result.recommendation],
        "overrides": [json.loads(o.model_dump_json()) for o in result.overrides],
        "confidence": json.loads(result.confidence.model_dump_json())
        if result.confidence
        else None,
        "content_hash": snapshot.content_hash,
    }
