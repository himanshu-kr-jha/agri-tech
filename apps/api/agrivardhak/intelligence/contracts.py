"""The intelligence module contract (ARCHITECTURE.md §3).

Every module is a pure function ``run(ModuleInput) -> ModuleOutput``: no I/O, no clock, no
network, no database. Inputs are gathered once by the orchestrator and passed in.

That purity is not fastidiousness — three properties depend on it:

* a module can be **replayed against an EvidenceSnapshot** to reproduce a historical answer
  (INV-2), which is what the replay test proves;
* golden-file tests over seeded scenarios are trivial (NFR-602);
* modules run concurrently without coordination.

These contracts are frozen at the end of Phase 0. Changing a field shape after that point
invalidates stored snapshots, so bump ``ModuleOutput.version`` instead.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EvidenceKind = Literal["observation", "external_record", "prediction", "domain_row"]


class EvidenceRef(BaseModel):
    """A pointer from a claim back to the thing that supports it.

    A claim with no EvidenceRef is dropped before rendering (FR-804). This is the mechanism
    that stops an orchestrator-invented number from reaching a user.
    """

    model_config = ConfigDict(frozen=True)

    kind: EvidenceKind
    id: uuid.UUID
    #: Human-readable, rendered in the packet's Evidence section.
    label: str
    as_of: dt.datetime


class AffectedSet(BaseModel):
    """Who and what a finding touches, quantified (FR-554).

    Reporting an event without exposure is a news feed. Exposure is what makes it a decision.
    """

    model_config = ConfigDict(frozen=True)

    farmer_ids: list[uuid.UUID] = Field(default_factory=list)
    plot_ids: list[uuid.UUID] = Field(default_factory=list)
    crop_cycle_ids: list[uuid.UUID] = Field(default_factory=list)
    lot_ids: list[uuid.UUID] = Field(default_factory=list)
    buyer_ids: list[uuid.UUID] = Field(default_factory=list)
    area_sqm: Decimal | None = None
    quantity_kg: Decimal | None = None
    value_paise: int | None = None

    @property
    def farmer_count(self) -> int:
        return len(self.farmer_ids)


class Finding(BaseModel):
    """One evidenced statement from a module.

    ``statement`` is one sentence, no hedging and no narrative — hedging belongs in
    ``confidence``, narrative belongs to the orchestrator.
    """

    model_config = ConfigDict(frozen=True)

    #: Stable identifier, e.g. "oversupply_risk.potato". Used for dedup and for tracking a
    #: finding across regenerations.
    key: str
    statement: str
    magnitude: Decimal | None = None
    unit: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceRef] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)
    affected: AffectedSet = Field(default_factory=AffectedSet)

    @field_validator("statement")
    @classmethod
    def _statement_is_a_sentence(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("statement must not be empty")
        return v.strip()


class ProposedAction(BaseModel):
    """What a module thinks should be done. Becomes a Recommendation only via the orchestrator."""

    model_config = ConfigDict(frozen=True)

    key: str
    title: str
    rationale: str
    #: Matches domain.enums.RecommendationType; kept as str so intelligence/ stays free of
    #: any ORM or persistence coupling.
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


class ProvenancedValue(BaseModel):
    """A value that has passed through the provenance layer (INV-3).

    Modules accept only these for consequential inputs. A bare float cannot enter a module,
    because a bare float cannot answer where it came from or how stale it is.
    """

    model_config = ConfigDict(frozen=True)

    attribute: str
    value: Decimal | None = None
    value_text: str | None = None
    unit: str | None = None
    #: Already combines source trust, verification status and age decay.
    confidence: float = Field(ge=0.0, le=1.0)
    source_type: str
    observed_at: dt.datetime
    is_stale: bool = False
    has_open_discrepancy: bool = False
    evidence: EvidenceRef


class ModuleInput(BaseModel):
    """Everything a module gets. Gathered by the orchestrator, never fetched by the module."""

    model_config = ConfigDict(frozen=True)

    organization_id: uuid.UUID
    #: Passed in rather than read from the clock, so a replay produces identical output.
    as_of: dt.datetime
    #: Module-specific payload, already provenance-resolved.
    data: dict[str, Any]


class ModuleOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    module: str
    #: Bumped on any formula change, and recorded on every recommendation generated from it.
    version: str
    findings: list[Finding] = Field(default_factory=list)
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    #: Sources that were stale or missing. Drives graceful degradation (NFR-301): a dead
    #: external source lowers one module's confidence rather than failing the request.
    degraded_inputs: list[str] = Field(default_factory=list)

    @property
    def confidence(self) -> float:
        """Weakest-link confidence across findings; 0.0 when the module found nothing."""
        if not self.findings:
            return 0.0
        return min(f.confidence for f in self.findings)
