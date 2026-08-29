"""The assistant's two contracts — the seam the hackathon orchestrator hangs off.

There are deliberately *two*, nested, and they are load-bearing in different ways.

:class:`AssistantAnswer` is the **outer** seam. The web tier, the SSE protocol and the
``conversation_turn`` table depend on this shape and nothing else. A future orchestrator
that returns one of these can replace everything below it without the UI noticing — which
is the whole point of drawing the boundary here rather than inside ``api/``.

:class:`IntentPlan` is the **inner** seam. It is what the hackathon router produces and the
only thing that decides which path a question takes. It is a separate type so the router can
be unit-tested without a database, and so a replacement router has one obvious thing to
satisfy.

Neither type does I/O, imports an ORM, or reads a clock. They are shapes.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agrivardhak.orchestrator.packet import Claim, DecisionPacket

#: How long a question may be. Not a security control — the question never reaches a model
#: as instructions — but an unbounded string on a public endpoint wastes a round trip.
MAX_QUESTION_CHARS = 500


class ResponseShape(StrEnum):
    """What kind of answer a question earns.

    The distinction that matters is ``DECISION`` versus everything else. A DECISION freezes
    an ``EvidenceSnapshot`` and writes ``Recommendation`` rows at ``SUGGESTED``; the others
    write nothing but a turn. Freezing a snapshot for "which farmers need attention" would
    devalue the snapshot for the decisions that actually need one (INV-2).
    """

    DECISION = "DECISION"
    LOOKUP = "LOOKUP"
    EXPLAIN = "EXPLAIN"
    REFUSE = "REFUSE"


class LookupKey(StrEnum):
    """The closed set of answerable lookups.

    Closed on purpose. The alternative — letting a model compose a query — is text-to-SQL,
    which is an injection surface and an accuracy problem that cannot be tested in the time
    available. Picking one item from a list is the task a model is most reliable at, and
    every key here resolves to a named function with its own tests and its own evidence.

    A question that maps to nothing falls through to ``DECISION``: a worse-fitting answer,
    never a wrong one.
    """

    # -- organization ------------------------------------------------------------
    #: The plainest questions there are — how many of us, how much land. Added after the
    #: assistant answered "how many farmers do we have?" with a season-long crop plan,
    #: because the vocabulary had been designed around decisions and omitted plain facts.
    MEMBERSHIP_SUMMARY = "MEMBERSHIP_SUMMARY"
    LAND_SUMMARY = "LAND_SUMMARY"
    TODAYS_PRIORITIES = "TODAYS_PRIORITIES"
    FARMERS_NEEDING_ATTENTION = "FARMERS_NEEDING_ATTENTION"
    PRODUCTION_FORECAST = "PRODUCTION_FORECAST"
    RISK_SUMMARY = "RISK_SUMMARY"
    SCHEME_ELIGIBILITY = "SCHEME_ELIGIBILITY"
    MARKET_SNAPSHOT = "MARKET_SNAPSHOT"
    FUNDING_POSITION = "FUNDING_POSITION"
    WHATS_CHANGED = "WHATS_CHANGED"

    # -- farmer ------------------------------------------------------------------
    MY_FARM_PROFILE = "MY_FARM_PROFILE"
    MY_YIELD_GAP = "MY_YIELD_GAP"
    MY_TASKS_TODAY = "MY_TASKS_TODAY"
    MY_SCHEMES = "MY_SCHEMES"
    MY_ANNOUNCEMENTS = "MY_ANNOUNCEMENTS"


#: Which lookups each audience may reach. This is INV-5 expressed as data rather than as a
#: runtime check that someone can forget to write: a farmer turn cannot name an organization
#: lookup, because the router validates its own output against this before returning.
FPO_LOOKUPS: frozenset[LookupKey] = frozenset(
    {
        LookupKey.MEMBERSHIP_SUMMARY,
        LookupKey.LAND_SUMMARY,
        LookupKey.TODAYS_PRIORITIES,
        LookupKey.FARMERS_NEEDING_ATTENTION,
        LookupKey.PRODUCTION_FORECAST,
        LookupKey.RISK_SUMMARY,
        LookupKey.SCHEME_ELIGIBILITY,
        LookupKey.MARKET_SNAPSHOT,
        LookupKey.FUNDING_POSITION,
        LookupKey.WHATS_CHANGED,
    }
)

FARMER_LOOKUPS: frozenset[LookupKey] = frozenset(
    {
        LookupKey.MY_FARM_PROFILE,
        LookupKey.MY_YIELD_GAP,
        LookupKey.MY_TASKS_TODAY,
        LookupKey.MY_SCHEMES,
        LookupKey.MY_ANNOUNCEMENTS,
    }
)


def lookups_for(audience: str) -> frozenset[LookupKey]:
    return FARMER_LOOKUPS if audience == "FARMER" else FPO_LOOKUPS


class AssistantRequest(BaseModel):
    """One turn's input."""

    model_config = ConfigDict(frozen=True)

    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    conversation_id: uuid.UUID | None = None
    #: The packet a follow-up refers to. Set by the client from the previous DECISION turn;
    #: ``EXPLAIN`` is only reachable when this is present, because "why?" with nothing to
    #: point at is not a question we can answer honestly.
    anchor_packet_id: uuid.UUID | None = None
    season: str | None = None


class IntentPlan(BaseModel):
    """What the router decided, and why. Streamed to the UI before any work begins.

    ``rationale`` is shown to the user (``"reading market and risk over the last 30 days"``).
    That is not decoration: the router is the one genuinely early thing on the wire, and
    showing its reasoning is both real information and honest about what the system is doing.
    """

    model_config = ConfigDict(frozen=True)

    shape: ResponseShape
    lookup: LookupKey | None = None
    #: DECISION only. Always a subset of ``engine.MODULES``; validated by the router, so a
    #: hallucinated module name cannot reach the orchestrator.
    modules: list[str] = Field(default_factory=list)
    #: Extracted parameters — crop, tract, horizon_days. Advisory: a lookup that does not
    #: recognise a key ignores it rather than failing.
    entities: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    router_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    #: True when the LLM router was unavailable and keyword planning produced this. Surfaced
    #: so a degraded answer is visibly degraded rather than quietly worse.
    fell_back: bool = False


class AssistantAnswer(BaseModel):
    """One turn's output. The only shape the web tier knows about."""

    model_config = ConfigDict(frozen=True)

    shape: ResponseShape
    plan: IntentPlan

    #: LOOKUP and EXPLAIN. Reuses the packet's ``Claim`` verbatim, which is what makes
    #: evidence non-optional at the schema level (``evidence`` is ``min_length=1``) and lets
    #: one renderer and one grounding validator serve both response paths.
    claims: list[Claim] = Field(default_factory=list)

    #: DECISION only.
    packet: DecisionPacket | None = None
    #: The persisted packet row. The client needs it twice over: to link through to the
    #: approval screen, and to send back as ``anchor_packet_id`` on the next turn so a
    #: follow-up has something frozen to read.
    packet_id: uuid.UUID | None = None
    content_hash: str | None = None

    #: REFUSE only. Says what the actor may *not* see and, crucially, what they can.
    refusal: str | None = None

    #: Verdict of the deterministic grounding pass. ``False`` means the reviewed output was
    #: discarded and this is the unreviewed answer — never that the answer is unevidenced.
    grounded: bool = True

    turn_id: uuid.UUID | None = None

    def as_wire(self) -> dict[str, Any]:
        """The JSON the browser receives. Kept here so the shape has exactly one definition."""
        return {
            "shape": self.shape.value,
            "plan": self.plan.model_dump(mode="json"),
            "claims": [c.model_dump(mode="json") for c in self.claims],
            "packet": self.packet.model_dump(mode="json") if self.packet else None,
            "packet_id": str(self.packet_id) if self.packet_id else None,
            "content_hash": self.content_hash,
            "refusal": self.refusal,
            "grounded": self.grounded,
            "turn_id": str(self.turn_id) if self.turn_id else None,
        }


#: Sections a relevance selector may never drop, whatever it returns.
#:
#: ``reconcile.py`` already argues this for overrides — "a silent override is a trust
#: failure" — and the argument extends unchanged to a selector. A filter that can delete an
#: override, a below-floor warning or a safety caveat is a filter that makes the answer look
#: tidier by removing exactly the parts that make it trustworthy (INV-1, FR-802, INV-8).
#:
#: ``situation``, ``recommendation`` and ``evidence`` are here for a different reason: they
#: are the reason, the answer and the citation. A packet that dropped any of them would not
#: be a tidier packet, it would be a different kind of object. ``situation`` earned its place
#: empirically — asked "what should we do this season", the selector dropped it, producing a
#: recommendation with no account of what it was responding to.
PROTECTED_SECTIONS: frozenset[str] = frozenset(
    {"overrides", "confidence", "situation", "recommendation", "evidence"}
)
