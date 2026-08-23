"""The DecisionPacket schema (FR-801, FR-803).

Nine sections in fixed order: Situation, Impact, Recommendation, Expected outcome,
Confidence, Evidence, Actions, Schedule, Drill-down — plus the overrides the orchestrator
applied, which are shown rather than hidden.

The orchestrator emits this via tool use against this exact schema. Free-text parsing is
prohibited: a model asked to write JSON in prose will eventually write invalid JSON in
prose, and this object is what a human approves.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from agrivardhak.intelligence.contracts import AffectedSet, EvidenceRef


class Claim(BaseModel):
    """An evidenced statement in a packet section.

    ``evidence`` is required and non-empty. The renderer drops any claim that arrives
    without it (FR-804) — the last line of defence against a hallucinated number.
    """

    model_config = ConfigDict(frozen=True)

    statement: str
    magnitude: Decimal | None = None
    unit: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceRef] = Field(min_length=1)
    affected: AffectedSet | None = None


class PacketProposedAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    rationale: str
    recommendation_type: str
    target_type: str
    target_id: uuid.UUID | None = None
    value_paise: int | None = None
    value_unit: str | None = None
    expected_impact: dict[str, Any] = Field(default_factory=dict)
    risks: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceRef] = Field(min_length=1)


class AssignedAction(BaseModel):
    """FR-805: a role, a task and a due date. An action with no owner is not an action."""

    model_config = ConfigDict(frozen=True)

    role: str
    task: str
    due_on: dt.date | None = None
    related_target_type: str | None = None
    related_target_id: uuid.UUID | None = None


class ProposedCalendarEvent(BaseModel):
    """Lands as PENDING_APPROVAL when consequential (FR-904)."""

    model_config = ConfigDict(frozen=True)

    title: str
    subject_type: str
    subject_id: uuid.UUID
    starts_at: dt.datetime
    ends_at: dt.datetime | None = None
    origin: str = "AI_RECOMMENDED"


class OverrideNote(BaseModel):
    """A module finding the orchestrator declined to follow (FR-802).

    Rendered in the packet. A silent override would be a trust failure — the whole point is
    that the CEO can see the reasoning and disagree with it.
    """

    model_config = ConfigDict(frozen=True)

    overridden_key: str
    overridden_module: str
    reason: str
    prevailing_evidence: list[EvidenceRef] = Field(min_length=1)


class ConfidenceBlock(BaseModel):
    """FR-813: when overall confidence is below the floor, say what would raise it."""

    model_config = ConfigDict(frozen=True)

    overall: float = Field(ge=0.0, le=1.0)
    per_section: dict[str, float] = Field(default_factory=dict)
    below_floor: bool = False
    what_would_raise_it: list[str] = Field(default_factory=list)
    degraded_inputs: list[str] = Field(default_factory=list)


class DrilldownRefs(BaseModel):
    """FR-806: resolves to concrete ids the UI can navigate to."""

    model_config = ConfigDict(frozen=True)

    farmer_ids: list[uuid.UUID] = Field(default_factory=list)
    plot_ids: list[uuid.UUID] = Field(default_factory=list)
    crop_cycle_ids: list[uuid.UUID] = Field(default_factory=list)
    lot_ids: list[uuid.UUID] = Field(default_factory=list)
    buyer_ids: list[uuid.UUID] = Field(default_factory=list)


class PacketScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    organization_id: uuid.UUID
    #: FPO | FARMER — the context scope this packet was produced under (INV-5).
    audience: str
    farmer_id: uuid.UUID | None = None
    season: str | None = None
    season_year: int | None = None


class DecisionPacket(BaseModel):
    """The canonical answer. Nine sections, fixed order."""

    model_config = ConfigDict(frozen=True)

    question: str
    scope: PacketScope

    situation: list[Claim] = Field(default_factory=list)
    impact: list[Claim] = Field(default_factory=list)
    recommendation: list[PacketProposedAction] = Field(default_factory=list)
    expected_outcome: list[Claim] = Field(default_factory=list)
    confidence: ConfidenceBlock
    evidence: list[EvidenceRef] = Field(default_factory=list)
    actions: list[AssignedAction] = Field(default_factory=list)
    schedule: list[ProposedCalendarEvent] = Field(default_factory=list)
    drilldown: DrilldownRefs = Field(default_factory=DrilldownRefs)

    overrides: list[OverrideNote] = Field(default_factory=list)

    generated_at: dt.datetime
    snapshot_id: uuid.UUID
    prompt_version: str
    model_id: str

    #: Fixed section order, used by the renderer and by the SSE stream (FR-801).
    #:
    #: ``ClassVar`` and not a plain annotation: without it Pydantic treats this as a *field*,
    #: so every packet carries a redundant copy of the section list, it lands in the frozen
    #: snapshot, and ``DecisionPacket.SECTION_ORDER`` raises AttributeError on the class.
    SECTION_ORDER: ClassVar[tuple[str, ...]] = (
        "situation",
        "impact",
        "recommendation",
        "expected_outcome",
        "confidence",
        "evidence",
        "actions",
        "schedule",
        "drilldown",
    )
