"""Reconcile — turning six module outputs into one answer (ARCHITECTURE §5, step 5).

Six modules will disagree. That is not a defect to be smoothed over; it is the most
valuable thing the system produces. The Farm module likes potato on gross margin, the
Market module says the harvest lands on the annual price floor, and a CEO who sees only the
winner has been given an opinion instead of a decision.

So reconciliation has three jobs and one prohibition.

**Rank.** By expected impact x confidence x urgency, so the top of the packet is what
actually moves member income rather than what happens to be most certain. A high-confidence
finding about nothing outranks nothing.

**Override, visibly.** When two modules point the same way about the same subject, with
more confidence than a third that points elsewhere, the third is overridden — and the
override is written into the packet with its reason and the evidence that beat it (FR-802).
A silent override is a trust failure: the CEO's ability to say "no, I disagree, and here is
why" is the entire human-in-the-loop guarantee (INV-1) and it needs something to disagree
*with*.

**Drop the unevidenced.** Any claim arriving without an ``EvidenceRef`` is discarded before
rendering (FR-804). This is the last barrier between a plausible sentence and a screen.

**The prohibition: reconciliation never invents a number.** It selects, orders, overrides
and explains. Every magnitude in the output packet traces to a module finding, which traces
to an observation or an external record. If reconciliation could compute, the audit chain
would have a hole in it exactly where the reasoning happens.

Determinism
-----------
This module is pure and deterministic. An LLM may narrate the result and may *propose* an
override, but the override rules below are what actually decide, and the packet is
constructed here. That ordering matters for three reasons: the demo runs with the network
off (NFR-303), a snapshot replays to an identical packet (INV-2), and a prompt injection in
ingested news can at worst produce a bad *claim* that still needs evidence and still needs a
human (NFR-405).
"""

from __future__ import annotations

import datetime as dt
import math
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from agrivardhak.intelligence.contracts import (
    AffectedSet,
    EvidenceRef,
    Finding,
    ModuleOutput,
    ProposedAction,
)
from agrivardhak.orchestrator.packet import (
    AssignedAction,
    Claim,
    ConfidenceBlock,
    DrilldownRefs,
    OverrideNote,
    PacketProposedAction,
)

#: A module's finding is overridden only when the opposing evidence is *clearly* stronger.
#: 0.05 rather than any margin at all: two findings within a rounding error of each other
#: are a disagreement to show the CEO, not one for the system to settle.
OVERRIDE_MARGIN = 0.05

#: At least this many independent modules must converge before an override fires. One module
#: disagreeing with another is a difference of opinion; two agreeing against a third is a
#: pattern.
OVERRIDE_QUORUM = 2

#: Findings weaker than this never reach the packet's headline sections. They remain in the
#: evidence and in the confidence block's explanation of what is weak.
HEADLINE_CONFIDENCE = 0.40

#: Which module's findings answer which packet section. A finding can inform more than one.
SITUATION_MODULES = ("risk_intelligence", "market_intelligence", "crop_health_intelligence")
IMPACT_MODULES = ("quality_intelligence", "risk_intelligence", "farm_intelligence")

#: Recommendation type -> the role that owns doing it (FR-805). An action with no owner is
#: not an action, and "the FPO" is not an owner.
ACTION_OWNER = {
    "BUYER_SELECTION": "MARKET_OFFICER",
    "LOT_ALLOCATION": "MARKET_OFFICER",
    "CROP_PLAN": "FPO_CEO",
    "CROP_PROTECTION": "FIELD_OFFICER",
    "FUNDING_ALLOCATION": "FINANCE_OFFICER",
    "PROCUREMENT": "MARKET_OFFICER",
    "SCHEME_PURSUIT": "FIELD_OFFICER",
    "RISK_MITIGATION": "FPO_CEO",
    "SCHEDULE": "FPO_CEO",
}


#: Findings whose subject is the same crop are comparable. Extracted from the key's tail,
#: which every module builds as ``<kind>.<subject>``.
def subject_of(key: str) -> str:
    parts = key.split(".")
    return parts[-1] if len(parts) > 1 else key


@dataclass(frozen=True)
class RankedFinding:
    finding: Finding
    module: str
    module_version: str
    score: float
    urgency: float


@dataclass
class Reconciled:
    situation: list[Claim] = field(default_factory=list)
    impact: list[Claim] = field(default_factory=list)
    recommendation: list[PacketProposedAction] = field(default_factory=list)
    expected_outcome: list[Claim] = field(default_factory=list)
    overrides: list[OverrideNote] = field(default_factory=list)
    actions: list[AssignedAction] = field(default_factory=list)
    evidence: list[EvidenceRef] = field(default_factory=list)
    drilldown: DrilldownRefs = field(default_factory=DrilldownRefs)
    confidence: ConfidenceBlock | None = None
    dropped_unevidenced: int = 0


# --------------------------------------------------------------------------- ranking


def urgency_of(finding: Finding, as_of: dt.datetime) -> float:
    """How soon this stops being actionable. 1.0 = now, 0.3 = no deadline in sight.

    Urgency is a multiplier rather than a sort key of its own. A trivial thing happening
    tomorrow should not outrank a large thing happening next month, but between two
    comparable findings the one with a closing window wins — which is how a human triages.
    """
    # A near-certain climatological event is a planning constant, not a deadline. It talks
    # about a harvest window and would otherwise score as urgent as a real hazard.
    if finding.key.startswith("climate_normal."):
        return 0.15

    horizon: dt.date | None = None
    if finding.affected.crop_cycle_ids and "harvest" in finding.statement.lower():
        horizon = as_of.date() + dt.timedelta(days=30)
    if "window closes" in finding.statement.lower() or "days away" in finding.statement.lower():
        horizon = as_of.date() + dt.timedelta(days=20)
    if horizon is None:
        return 0.3
    days = max(0, (horizon - as_of.date()).days)
    if days <= 14:
        return 1.0
    if days <= 45:
        return 0.7
    return 0.5


def impact_of(finding: Finding) -> float:
    """Normalised scale of what is at stake, 0..1.

    Log-scaled, and that matters more than it sounds. A linear scale with a ceiling
    saturates: on this collective's data a 9-acre guava hazard and a 1,868-tonne paddy
    exposure both pinned at 1.0, so the ordering fell through to confidence and put the
    small finding first. Rupees at stake span four orders of magnitude here, so the scale
    that orders them has to as well.

    Deliberately still crude — the number only ever orders a list, and a precise impact
    score would imply a precision the inputs do not have.
    """
    if finding.affected.value_paise:
        return _log_scale(abs(finding.affected.value_paise), floor=10_000, ceiling=10_000_000_00)
    if finding.affected.farmer_ids:
        return _log_scale(len(finding.affected.farmer_ids), floor=1, ceiling=1000)
    if finding.affected.quantity_kg:
        return _log_scale(float(finding.affected.quantity_kg), floor=100, ceiling=10_000_000)
    return 0.2


def _log_scale(value: float, *, floor: float, ceiling: float) -> float:
    """Map a value onto 0..1 by orders of magnitude between floor and ceiling."""
    if value <= floor:
        return 0.05
    if value >= ceiling:
        return 1.0
    return round(
        0.05
        + 0.95
        * (math.log10(value) - math.log10(floor))
        / (math.log10(ceiling) - math.log10(floor)),
        4,
    )


def rank_findings(outputs: list[ModuleOutput], as_of: dt.datetime) -> list[RankedFinding]:
    ranked: list[RankedFinding] = []
    for output in outputs:
        for finding in output.findings:
            if not finding.evidence:
                continue  # FR-804, enforced again here rather than trusted
            urgency = urgency_of(finding, as_of)
            ranked.append(
                RankedFinding(
                    finding=finding,
                    module=output.module,
                    module_version=output.version,
                    score=round(impact_of(finding) * finding.confidence * urgency, 5),
                    urgency=urgency,
                )
            )
    return sorted(ranked, key=lambda r: (-r.score, r.finding.key))


# --------------------------------------------------------------------------- override


def detect_overrides(ranked: list[RankedFinding]) -> list[OverrideNote]:
    """Find conclusions that the weight of other evidence contradicts.

    Two things get overridden, and the second one is the interesting case.

    **An explicit module proposal.** The Farm module proposes a crop on return per rupee. If
    at least :data:`OVERRIDE_QUORUM` *other* modules produce adverse findings about that same
    crop, each more confident than the proposal by more than :data:`OVERRIDE_MARGIN`, the
    proposal is marked. It is not deleted — it is shown next to what contradicts it.

    **The status quo.** This one took a correction to get right. The original rule could only
    override something a module had proposed, which quietly assumed the risky plan is always
    the one the AI suggests. On real data the opposite was true: on this collective, 99% of
    operated area is already in a single crop that the Market module finds realises a third
    below the mandi price and the Risk module finds harvests into a 36x arrival glut. Nobody
    *proposed* that. It is simply what is planted, and it was invisible to a reconciler that
    only examined proposals.

    So the dominant planted crop — named by the Risk module's concentration finding — is
    treated as an implicit plan and can be overridden the same way. Overriding the plan
    nobody argued for is usually the more valuable half.
    """
    overrides: list[OverrideNote] = []
    overrides.extend(_override_proposals(ranked))
    overrides.extend(_override_status_quo(ranked))
    return overrides


def _adverse_about(
    ranked: list[RankedFinding], subject: str, *, exclude_module: str
) -> list[RankedFinding]:
    return [
        r
        for r in ranked
        if r.module != exclude_module
        and subject_of(r.finding.key) == subject
        and _is_adverse(r.finding)
    ]


def _override_proposals(ranked: list[RankedFinding]) -> list[OverrideNote]:
    proposals = [
        r
        for r in ranked
        if r.module == "farm_intelligence" and r.finding.key.startswith("crop_return.")
    ]
    out: list[OverrideNote] = []
    seen: set[str] = set()
    for proposal in proposals:
        subject = subject_of(proposal.finding.key)
        if subject in seen:
            continue
        contradicting = [
            r
            for r in _adverse_about(ranked, subject, exclude_module=proposal.module)
            if r.finding.confidence > proposal.finding.confidence + OVERRIDE_MARGIN
        ]
        modules_agreeing = {r.module for r in contradicting}
        if len(modules_agreeing) < OVERRIDE_QUORUM:
            continue
        seen.add(subject)
        out.append(
            OverrideNote(
                overridden_key=proposal.finding.key,
                overridden_module=proposal.module,
                reason=(
                    f"{len(contradicting)} findings from {len(modules_agreeing)} other modules "
                    f"concern {subject} in the same window and each carry more confidence than "
                    f"this proposal ({proposal.finding.confidence:.2f}). They do not contradict "
                    f"the return calculation — they say the price it assumes will not hold. "
                    f"The proposal is kept and shown against them rather than dropped."
                ),
                prevailing_evidence=[e for r in contradicting for e in r.finding.evidence[:1]][:6],
            )
        )
    return out


def _override_status_quo(ranked: list[RankedFinding]) -> list[OverrideNote]:
    """Override the crop the collective is already committed to, when the evidence converges."""
    out: list[OverrideNote] = []
    concentrations = [r for r in ranked if r.finding.key.startswith("concentration.")]
    for concentration in concentrations:
        subject = subject_of(concentration.finding.key)
        contradicting = [
            r
            for r in _adverse_about(ranked, subject, exclude_module="__none__")
            if r.finding.key != concentration.finding.key
        ]
        modules_agreeing = {r.module for r in contradicting}
        if len(modules_agreeing) < OVERRIDE_QUORUM:
            continue
        detail = "; ".join(
            f"{r.module.replace('_intelligence', '')} at {r.finding.confidence:.2f}"
            for r in contradicting[:4]
        )
        out.append(
            OverrideNote(
                overridden_key=f"current_cropping.{subject}",
                overridden_module="status_quo",
                reason=(
                    f"The collective's current concentration in {subject} is contradicted by "
                    f"{len(contradicting)} findings from {len(modules_agreeing)} independent "
                    f"modules ({detail}), all pointing the same way about the same crop in the "
                    f"same window. Nobody proposed this cropping pattern — it is what is "
                    f"already planted, which is why it would otherwise go unexamined. This is "
                    f"not an instruction to stop growing {subject}: it is the case for the "
                    f"board to make that choice deliberately, with the alternatives priced."
                ),
                prevailing_evidence=[e for r in contradicting for e in r.finding.evidence[:1]][:6],
            )
        )
    return out


def _is_adverse(finding: Finding) -> bool:
    """Does this finding argue against acting on its subject?

    Matched on the finding *key*, never on the prose. Keys are a fixed vocabulary the
    modules control; statements are natural language and could in principle carry ingested
    text. Deciding an override by keyword-matching a sentence would be a place where
    untrusted content could steer the outcome.
    """
    adverse_prefixes = (
        "price_trough.",
        "arrival_glut.",
        "weather_hazard.",
        "concentration.",
        "price_reversal",
        "price_realisation_gap.",
        "condition.",
        "outbreak.",
        "water_constraint.",
        "underperforming_crop.",
    )
    return finding.key.startswith(adverse_prefixes)


# --------------------------------------------------------------------------- assembly


def to_claim(finding: Finding) -> Claim:
    return Claim(
        statement=finding.statement,
        magnitude=finding.magnitude,
        unit=finding.unit,
        confidence=finding.confidence,
        evidence=finding.evidence,
        affected=finding.affected,
    )


def to_packet_action(action: ProposedAction) -> PacketProposedAction:
    return PacketProposedAction(
        title=action.title,
        rationale=action.rationale,
        recommendation_type=action.recommendation_type,
        target_type=action.target_type,
        target_id=action.target_id,
        value_paise=action.value_paise,
        value_unit=action.value_unit,
        expected_impact=action.expected_impact,
        risks=action.risks,
        alternatives=action.alternatives,
        confidence=action.confidence,
        evidence=action.evidence,
    )


def assign(action: ProposedAction, as_of: dt.datetime) -> AssignedAction:
    return AssignedAction(
        role=ACTION_OWNER.get(action.recommendation_type, "FPO_CEO"),
        task=action.title,
        due_on=as_of.date() + dt.timedelta(days=14),
        related_target_type=action.target_type,
        related_target_id=action.target_id,
    )


def merge_drilldown(findings: list[Finding], actions: list[ProposedAction]) -> DrilldownRefs:
    farmers: set[uuid.UUID] = set()
    plots: set[uuid.UUID] = set()
    cycles: set[uuid.UUID] = set()
    lots: set[uuid.UUID] = set()
    buyers: set[uuid.UUID] = set()
    for finding in findings:
        affected: AffectedSet = finding.affected
        farmers.update(affected.farmer_ids)
        plots.update(affected.plot_ids)
        cycles.update(affected.crop_cycle_ids)
        lots.update(affected.lot_ids)
        buyers.update(affected.buyer_ids)
    for action in actions:
        if action.target_id and action.target_type == "buyer":
            buyers.add(action.target_id)
    return DrilldownRefs(
        farmer_ids=sorted(farmers, key=str),
        plot_ids=sorted(plots, key=str)[:500],
        crop_cycle_ids=sorted(cycles, key=str)[:500],
        lot_ids=sorted(lots, key=str),
        buyer_ids=sorted(buyers, key=str),
    )


def build_confidence(
    outputs: list[ModuleOutput],
    ranked: list[RankedFinding],
    floor: float,
) -> ConfidenceBlock:
    """Overall confidence, and — when it is low — what would actually raise it (FR-813).

    Overall is impact-weighted, not the minimum. A weakest-link rule was tried and produces
    a 0.0 on any packet that happens to contain one poorly-evidenced cycle, which is both
    useless and wrong: the packet's headline claim can be well evidenced while a footnote
    is not. The weak ones are named in ``what_would_raise_it`` instead of dragging the
    number down invisibly.
    """
    per_section: dict[str, float] = {}
    for output in outputs:
        if output.findings:
            weights = [impact_of(f) or 0.01 for f in output.findings]
            total = sum(weights)
            per_section[output.module] = round(
                sum(f.confidence * w for f, w in zip(output.findings, weights, strict=True))
                / total,
                3,
            )

    headline = ranked[:8]
    if headline:
        weights = [max(0.01, impact_of(r.finding)) for r in headline]
        overall = sum(
            r.finding.confidence * w for r, w in zip(headline, weights, strict=True)
        ) / sum(weights)
    else:
        overall = 0.0

    degraded = [d for output in outputs for d in output.degraded_inputs]
    remedies: list[str] = []
    weak = [r for r in ranked[:12] if r.finding.confidence < floor]
    for r in weak[:4]:
        remedies.append(
            f"'{r.finding.key}' is at {r.finding.confidence:.2f} — "
            + (
                r.finding.assumptions[0]
                if r.finding.assumptions
                else "verify its inputs to raise it"
            )
        )
    if any("crop-health observation" in d for d in degraded):
        remedies.append(
            "A field visit to the cycles with no health reading would raise the production "
            "forecast more than any other single action."
        )
    if any("working capital" in d for d in degraded):
        remedies.append("Recording working capital would let plans be checked for affordability.")
    if any("unsourced" in d.lower() or "SYNTHETIC" in d for d in degraded):
        remedies.append(
            "Replacing the placeholder cost and yield coefficients with cited figures "
            "(seed/sources.md A1-A15, E1-E6) lifts every economic claim here."
        )

    return ConfidenceBlock(
        overall=round(min(1.0, max(0.0, overall)), 3),
        per_section=per_section,
        below_floor=overall < floor,
        what_would_raise_it=remedies,
        degraded_inputs=sorted(set(degraded)),
    )


def reconcile(
    outputs: list[ModuleOutput],
    *,
    as_of: dt.datetime,
    confidence_floor: float = 0.45,
    max_situation: int = 5,
    max_impact: int = 4,
    max_recommendations: int = 5,
) -> Reconciled:
    """The deterministic core. An LLM narrates this; it does not decide it."""
    dropped = sum(1 for o in outputs for f in o.findings if not f.evidence)
    ranked = rank_findings(outputs, as_of)
    overrides = detect_overrides(ranked)

    situation = [
        r
        for r in ranked
        if r.module in SITUATION_MODULES and r.finding.confidence >= HEADLINE_CONFIDENCE
    ][:max_situation]
    impact = [
        r
        for r in ranked
        if r.module in IMPACT_MODULES
        and r.finding.confidence >= HEADLINE_CONFIDENCE
        and r.finding.key not in {s.finding.key for s in situation}
    ][:max_impact]

    all_actions = [(o.module, a) for o in outputs for a in o.proposed_actions if a.evidence]

    # An overridden proposal's action falls to the bottom rather than out: the CEO may still
    # choose it, and hiding the option they were told about is its own kind of dishonesty.
    def action_rank(item: tuple[str, ProposedAction]) -> tuple[int, float]:
        """Order by what it is worth, not by how sure we are of it.

        Ranking on confidence alone put four single-lot sale actions above the crop plan for
        976 hectares, because a sale is easier to be sure about than a season. Certainty
        about something small is not more useful than a well-founded call on something large.
        """
        module, action = item
        demoted = any(
            module == note.overridden_module and subject_of(note.overridden_key) in action.key
            for note in overrides
        )
        weight = (
            _log_scale(abs(action.value_paise), floor=10_000, ceiling=10_000_000_00)
            if action.value_paise
            else 0.3
        )
        return (1 if demoted else 0, -(weight * action.confidence))

    ordered = sorted(all_actions, key=action_rank)
    chosen = [a for _m, a in ordered][:max_recommendations]

    findings_used = [r.finding for r in (*situation, *impact)]
    evidence: list[EvidenceRef] = []
    seen: set[uuid.UUID] = set()
    for refs in [f.evidence for f in findings_used] + [a.evidence for a in chosen]:
        for ref in refs:
            if ref.id not in seen:
                seen.add(ref.id)
                evidence.append(ref)

    expected = [
        Claim(
            statement=(
                f"{action.title}: {action.expected_impact.get('metric', 'outcome')} expected to "
                f"{action.expected_impact.get('direction', 'change')}"
                + (
                    f", range {action.expected_impact['range'][0]} to "
                    f"{action.expected_impact['range'][1]}"
                    if isinstance(action.expected_impact.get("range"), list)
                    else ""
                )
                + ". Stated as a direction and a range, never a promised figure."
            ),
            magnitude=Decimal(action.value_paise) if action.value_paise else None,
            unit=action.value_unit,
            confidence=action.confidence,
            evidence=action.evidence,
        )
        for action in chosen[:3]
    ]

    return Reconciled(
        situation=[to_claim(r.finding) for r in situation],
        impact=[to_claim(r.finding) for r in impact],
        recommendation=[to_packet_action(a) for a in chosen],
        expected_outcome=expected,
        overrides=overrides,
        actions=[assign(a, as_of) for a in chosen],
        evidence=evidence[:60],
        drilldown=merge_drilldown(findings_used, chosen),
        confidence=build_confidence(outputs, ranked, confidence_floor),
        dropped_unevidenced=dropped,
    )
