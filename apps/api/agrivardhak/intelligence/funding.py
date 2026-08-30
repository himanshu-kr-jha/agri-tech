"""Funding requirement — M12, FR-601…606, SAF-04.

Deliberately thin (D-21). The MVP answers one question: *how much working capital does this
season need, when, and what happens if we are short?* Anything resembling credit scoring is
out of scope, and not only for scope reasons.

The line this module will not cross
-----------------------------------
FR-605 and SAF-04 forbid the system from ever recommending that support be withheld from a
named farmer, or ranking farmers by anything resembling "worth investing in". That is not a
policy bolted on at the end — it decides the shape of the module:

* Requirements are computed **per crop and per tract**, never per farmer.
* When capital is short, the output is a **timing and sourcing problem** — stagger the
  disbursement, pursue the scheme, borrow against the warehouse receipt — never a shortlist
  of who to fund.
* The word "eligible" appears only about *schemes*, where it is the government's criterion,
  never about a member's worth.

An FPO with a shortfall has a financing problem. Turning it into a selection problem is how
a collective stops being one, and it is the single most plausible way this software could do
real harm.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from agrivardhak.domain.units import format_lakh
from agrivardhak.intelligence.contracts import (
    AffectedSet,
    EvidenceRef,
    Finding,
    ModuleInput,
    ModuleOutput,
    ProposedAction,
)

MODULE = "funding_intelligence"
VERSION = "1.0.0"

SQM_PER_HA = Decimal(10000)

#: Buffer over computed requirement. A plan funded to the last rupee fails on the first
#: late payment, and late payments are the norm, not the exception.
PRUDENT_BUFFER = 0.15


@dataclass(frozen=True)
class CapitalNeed:
    """What one crop on one tract needs, and when."""

    crop_name: str
    tract: str
    area_sqm: Decimal
    cost_paise_per_ha: int
    #: When the money is actually needed — sowing, not harvest.
    needed_by: dt.date | None
    farmer_ids: list[uuid.UUID] = field(default_factory=list)
    evidence: list[EvidenceRef] = field(default_factory=list)

    @property
    def total_paise(self) -> int:
        return int(float(self.area_sqm / SQM_PER_HA) * self.cost_paise_per_ha)


@dataclass(frozen=True)
class FundingSource:
    """Capital the collective could draw on, with what it costs and how fast it arrives."""

    label: str
    available_paise: int | None
    #: Annual cost of the money, as a fraction. None = unknown, not free.
    interest_rate: float | None
    #: Working days from decision to cash. A cheap source that arrives after sowing is not a
    #: source for this season.
    lead_time_days: int
    evidence: EvidenceRef | None = None


def run(inputs: ModuleInput) -> ModuleOutput:
    data = inputs.data
    needs: list[CapitalNeed] = data.get("needs") or []
    sources: list[FundingSource] = data.get("sources") or []
    available: int | None = data.get("working_capital_paise")

    findings: list[Finding] = []
    actions: list[ProposedAction] = []
    degraded: list[str] = ["Cost-of-cultivation figures are modelled, not surveyed."]

    if not needs:
        return ModuleOutput(
            module=MODULE, version=VERSION, degraded_inputs=[*degraded, "no crop plan to fund"]
        )
    if available is None:
        degraded.append("working capital is not recorded — the shortfall cannot be computed")

    required = sum(n.total_paise for n in needs)
    prudent = int(required * (1 + PRUDENT_BUFFER))
    evidence = [e for n in needs for e in n.evidence[:1]][:5]
    if not evidence:
        return ModuleOutput(
            module=MODULE,
            version=VERSION,
            degraded_inputs=[*degraded, "no evidence behind the crop plan"],
        )

    all_farmers = sorted({f for n in needs for f in n.farmer_ids}, key=str)
    findings.append(
        Finding(
            key="capital_requirement",
            statement=(
                f"The season's plan needs about Rs {format_lakh(required)} lakh of working "
                f"capital across {len(needs)} crop-tract blocks, or Rs "
                f"{format_lakh(prudent)} lakh with a {PRUDENT_BUFFER:.0%} buffer."
            ),
            magnitude=Decimal(required),
            unit="paise",
            confidence=0.60,
            evidence=evidence,
            assumptions=[
                "Costed at placeholder cost-of-cultivation figures, not surveyed ones.",
                f"The {PRUDENT_BUFFER:.0%} buffer is a judgement, not a computed reserve — a "
                "plan funded to the last rupee fails on the first late payment.",
            ],
            affected=AffectedSet(
                farmer_ids=all_farmers,
                area_sqm=sum((n.area_sqm for n in needs), Decimal(0)),
                value_paise=required,
            ),
        )
    )

    if available is not None and prudent > available:
        shortfall = prudent - available
        findings.append(
            Finding(
                key="capital_shortfall",
                statement=(
                    f"Rs {format_lakh(shortfall)} lakh short of funding this plan prudently "
                    f"(Rs {format_lakh(available)} lakh on hand). This is a timing and "
                    f"sourcing problem for the collective, not a question of which members "
                    f"to support."
                ),
                magnitude=Decimal(shortfall),
                unit="paise",
                confidence=0.60,
                evidence=evidence,
                assumptions=[
                    "Assumes the whole plan is funded at once. Staggering by sowing window "
                    "usually reduces the peak requirement substantially.",
                ],
                affected=AffectedSet(value_paise=shortfall),
            )
        )

        usable = [s for s in sources if s.available_paise]
        by_cost = sorted(
            usable, key=lambda s: s.interest_rate if s.interest_rate is not None else 1.0
        )
        options = [
            f"{s.label}: Rs {format_lakh(s.available_paise or 0)} lakh"
            + (f" at {s.interest_rate:.1%}" if s.interest_rate is not None else " (rate unknown)")
            + f", {s.lead_time_days} days to arrive"
            for s in by_cost[:4]
        ]
        actions.append(
            ProposedAction(
                key="close_capital_gap",
                title=f"Close a Rs {format_lakh(shortfall)} lakh working-capital gap",
                rationale=(
                    "Three levers, in order of what they cost the collective: stagger "
                    "disbursement so the peak requirement falls below what is on hand; pursue "
                    "the scheme and credit lines the organization already qualifies for; and "
                    "only then borrow at commercial rates. Reducing the planted area is a "
                    "fourth lever and should be a board decision taken in the open, applied "
                    "across the membership rather than to selected members."
                ),
                recommendation_type="FUNDING_ALLOCATION",
                target_type="organization",
                target_id=inputs.organization_id,
                value_paise=shortfall,
                value_unit="paise_shortfall",
                expected_impact={
                    "metric": "working capital available at sowing",
                    "direction": "increase",
                    "sources_considered": options or ["no funding sources are recorded"],
                    "peak_requirement_paise": prudent,
                    "on_hand_paise": available,
                    # Stated in the payload as well as the prose: anything consuming this
                    # programmatically must see the constraint too.
                    "never": (
                        "This module does not rank members and must not be used to decide "
                        "who to support (FR-605, SAF-04)."
                    ),
                },
                risks=[
                    "Borrowing at commercial rates against a crop whose price is uncertain "
                    "transfers market risk onto the collective's balance sheet.",
                    "Staggering disbursement pushes some sowing later, which has its own "
                    "yield cost.",
                ],
                alternatives=[
                    "Fund the plan partially and carry the rest to the next season.",
                    *options,
                ],
                confidence=0.60,
                evidence=evidence,
            )
        )

    for need in sorted(needs, key=lambda n: -n.total_paise)[:3]:
        if not need.evidence:
            continue
        when = f" by {need.needed_by:%d %b}" if need.needed_by else ""
        findings.append(
            Finding(
                key=f"capital_need.{need.tract.lower()}.{need.crop_name.lower()}",
                statement=(
                    f"{need.tract.replace('_', '-').title()} {need.crop_name}: Rs "
                    f"{format_lakh(need.total_paise)} lakh needed{when}, across "
                    f"{float(need.area_sqm / Decimal('4046.86')):,.0f} acres."
                ),
                magnitude=Decimal(need.total_paise),
                unit="paise",
                confidence=0.60,
                evidence=need.evidence,
                assumptions=["Money is needed at sowing, not at harvest."],
                affected=AffectedSet(
                    farmer_ids=need.farmer_ids,
                    area_sqm=need.area_sqm,
                    value_paise=need.total_paise,
                ),
            )
        )

    return ModuleOutput(
        module=MODULE,
        version=VERSION,
        findings=findings,
        proposed_actions=actions,
        degraded_inputs=degraded,
    )
