"""Market Intelligence — one of the two hero capabilities (D-03).

The thesis in one line: **price is not value**. A buyer offering ₹34/kg 180 km away on
60-day terms with an 11% rejection rate lands ₹28.12/kg, while one offering ₹30/kg 22 km
away on 15-day terms lands ₹28.28/kg. This module computes what actually arrives, and shows
every term of the subtraction.

Worth knowing before reading the formulas: on realistic numbers **rejection risk is the
largest deduction**, not freight. Over 180 km freight costs about ₹0.81/kg; an 11% rejection
rate on ₹34/kg costs ₹3.74/kg. An early draft of this module left rejection out of the price
and only scored it as risk, and the reversal the whole product rests on did not occur.

Pure function (ARCHITECTURE §3): no I/O, no clock, no database. ``as_of`` comes in with the
input so a replay against a stored EvidenceSnapshot reproduces the answer exactly.

Two rules shape the output:

* **Never emit a bare score.** ``components`` carries every term, because an FPO asked to
  act on a number it cannot decompose is being asked to trust us, and trust is not what we
  are selling.
* **Never emit a claim without evidence.** ``Finding`` refuses to construct without an
  ``EvidenceRef``, so an unbacked number cannot leave this module (FR-804).
"""

from __future__ import annotations

import datetime as dt
import statistics
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from agrivardhak.intelligence.contracts import (
    AffectedSet,
    EvidenceRef,
    Finding,
    ModuleInput,
    ModuleOutput,
    ProposedAction,
)

MODULE = "market_intelligence"
#: Bump on any formula change. Recorded on every recommendation built from this output.
VERSION = "1.0.0"


# --------------------------------------------------------------------------- tunables


@dataclass(frozen=True)
class CostModel:
    """Cost assumptions. Configuration, not constants — and shown in the UI.

    Defaults are order-of-magnitude placeholders pending `seed/sources.md` M10-M12. Every
    output that uses an unsourced default lists it in ``assumptions``, so a reader can see
    which numbers are ours rather than the market's.
    """

    #: Freight per tonne per km, in paise. Scales with distance and fuel.
    freight_paise_per_tonne_km: int = 450
    #: Fuel index; 1.0 = the price the freight rate was calibrated at.
    fuel_index: float = 1.0
    #: Loading, weighing, bagging — per kg, largely distance-independent.
    handling_paise_per_kg: int = 30
    #: Commission, weighment, market fee — per kg.
    transaction_paise_per_kg: int = 25
    #: Cold storage, per kg per day.
    storage_paise_per_kg_per_day: int = 2
    #: Annual cost of capital, for pricing a payment delay.
    cost_of_capital_annual_pct: float = 14.0
    #: Value lost per grade step below what the buyer wants, as a fraction of price.
    quality_loss_per_grade_step: float = 0.12
    #: Additional loss per day in transit for a perishable.
    perishable_loss_per_transit_day: float = 0.02

    def sources(self) -> list[str]:
        return [
            "Freight, handling and transaction costs are unsourced defaults "
            "(seed/sources.md M10-M12) — they set the scale of the subtraction, not its shape.",
        ]


@dataclass(frozen=True)
class AttractivenessWeights:
    """Weights for the composite score (FR-543). Displayed alongside the score."""

    effective_price: float = 0.45
    reliability: float = 0.20
    rejection_risk: float = 0.15
    payment_delay: float = 0.10
    quantity_fit: float = 0.07
    distance: float = 0.03

    def as_dict(self) -> dict[str, float]:
        return {
            "effective_price": self.effective_price,
            "reliability": self.reliability,
            "rejection_risk": self.rejection_risk,
            "payment_delay": self.payment_delay,
            "quantity_fit": self.quantity_fit,
            "distance": self.distance,
        }


GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "REJECT": 3}


# --------------------------------------------------------------------------- inputs


@dataclass(frozen=True)
class Lot:
    id: uuid.UUID
    crop_name: str
    quantity_kg: Decimal
    grade: str | None
    ready_date: dt.date | None
    #: Days the lot has already been held, for storage cost already sunk.
    days_held: int = 0
    #: True for crops with no real storage option — the urgency case.
    perishable: bool = False


@dataclass(frozen=True)
class Offer:
    """A buyer's stated willingness to buy: the input to effective price."""

    buyer_id: uuid.UUID
    buyer_name: str
    price_paise_per_kg: int
    quantity_kg: Decimal
    grade_required: str | None
    distance_km: float
    payment_terms_days: int
    reliability: float | None
    rejection_rate: float | None
    min_quantity_kg: Decimal | None
    max_quantity_kg: Decimal | None
    evidence: EvidenceRef
    transit_days: int = 1


@dataclass(frozen=True)
class StorageOption:
    """What the organization can hold, and at what cost.

    ``capacity_kg = None`` means *unknown*, not zero (FR-103). The module must say it does
    not know rather than silently planning as if there were no store.
    """

    capacity_kg: Decimal | None
    cost_paise_per_kg_per_day: int
    evidence: EvidenceRef | None = None


@dataclass(frozen=True)
class PricePoint:
    date: dt.date
    modal_paise_per_kg: int
    arrivals_kg: Decimal | None
    market_name: str
    evidence: EvidenceRef


# --------------------------------------------------------------------------- outputs


@dataclass(frozen=True)
class EffectivePrice:
    """The subtraction, itemised. FR-542."""

    buyer_id: uuid.UUID
    buyer_name: str
    headline_paise_per_kg: int
    effective_paise_per_kg: int
    components: dict[str, Any]

    @property
    def total_deduction(self) -> int:
        return self.headline_paise_per_kg - self.effective_paise_per_kg


@dataclass(frozen=True)
class BuyerScore:
    effective: EffectivePrice
    attractiveness: float
    components: dict[str, Any]
    fits_quantity: bool
    meets_grade: bool
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- computation


def logistics_paise_per_kg(distance_km: float, quantity_kg: Decimal, costs: CostModel) -> int:
    """Freight, amortised per kg.

    Charged on the tonne-km actually moved, so a small lot travelling far is expensive per
    kg while a full load is not — which is exactly why aggregation is the FPO's advantage
    and why the module must model it rather than using a flat rate.
    """
    if quantity_kg <= 0:
        return 0
    tonnes = float(quantity_kg) / 1000.0
    total_paise = costs.freight_paise_per_tonne_km * costs.fuel_index * tonnes * distance_km
    return round(total_paise / float(quantity_kg))


def quality_loss_paise_per_kg(
    lot_grade: str | None,
    grade_required: str | None,
    price_paise_per_kg: int,
    transit_days: int,
    perishable: bool,
    costs: CostModel,
) -> int:
    """Value lost to a grade gap and to time in transit.

    A grade *better* than required earns nothing extra here — the buyer pays their stated
    price either way, and pretending otherwise would inflate the winner.
    """
    loss = 0.0
    if lot_grade and grade_required:
        gap = GRADE_ORDER.get(lot_grade, 3) - GRADE_ORDER.get(grade_required, 0)
        if gap > 0:
            loss += gap * costs.quality_loss_per_grade_step
    if perishable and transit_days > 0:
        loss += transit_days * costs.perishable_loss_per_transit_day
    return round(price_paise_per_kg * loss)


def financing_paise_per_kg(
    price_paise_per_kg: int, payment_delay_days: int, costs: CostModel
) -> int:
    """The cost of waiting to be paid.

    ₹35/kg in 90 days is not ₹35/kg. For a marginal farmer the delay is often the binding
    constraint rather than a financing line — this puts a number on it.
    """
    if payment_delay_days <= 0:
        return 0
    daily = costs.cost_of_capital_annual_pct / 100.0 / 365.0
    return round(price_paise_per_kg * daily * payment_delay_days)


def storage_paise_per_kg(days_held: int, costs: CostModel) -> int:
    """Storage cost already incurred on a lot. **Reported, never deducted.**

    This was a deduction once, and it was wrong in a way worth recording. A potato lot held
    292 days carried 292 paise/kg of accrued storage; subtracting that from a ₹7.05/kg offer
    produced an effective price of ₹3.23/kg and made every buyer look ruinous.

    The money is real and it is gone. It is *sunk*: identical under every option including
    not selling at all, so it cannot inform the choice between them. An FPO shown ₹3.23/kg
    would reasonably reject a fair offer and keep paying rent on the same potatoes.

    So it is surfaced as ``storage_already_sunk`` — the CEO should absolutely know what the
    holding has cost — and kept out of the arithmetic that ranks buyers. Storage *from here
    on* is a different number and does belong in a hold-versus-sell comparison, which is
    what :func:`allocate` uses it for.
    """
    return max(0, days_held) * costs.storage_paise_per_kg_per_day


def rejection_paise_per_kg(price_paise_per_kg: int, rejection_rate: float | None) -> int:
    """Expected value lost to consignment rejection.

    This belongs in the subtraction, not only in the composite score: produce a buyer
    rejects is produce the farmer is not paid for. On the numbers this is usually the
    *largest* single deduction for an unreliable buyer — an 11% rejection rate on ₹35/kg
    costs ₹3.85/kg, roughly five times the freight over 180 km.

    Unknown rejection history is priced at zero here rather than guessed. The uncertainty is
    carried in the attractiveness score and in the finding's confidence instead, so we do
    not fabricate a deduction we have no basis for.
    """
    if not rejection_rate or rejection_rate <= 0:
        return 0
    return round(price_paise_per_kg * min(1.0, rejection_rate))


def effective_price(lot: Lot, offer: Offer, costs: CostModel) -> EffectivePrice:
    """FR-542. Every deduction is named and returned."""
    quantity = min(lot.quantity_kg, offer.quantity_kg) or lot.quantity_kg

    logistics = logistics_paise_per_kg(offer.distance_km, quantity, costs)
    handling = costs.handling_paise_per_kg
    quality = quality_loss_paise_per_kg(
        lot.grade,
        offer.grade_required,
        offer.price_paise_per_kg,
        offer.transit_days,
        lot.perishable,
        costs,
    )
    transaction = costs.transaction_paise_per_kg
    sunk_storage = storage_paise_per_kg(lot.days_held, costs)
    financing = financing_paise_per_kg(offer.price_paise_per_kg, offer.payment_terms_days, costs)
    rejection = rejection_paise_per_kg(offer.price_paise_per_kg, offer.rejection_rate)

    # Sunk storage is deliberately absent from this sum. See storage_paise_per_kg.
    net = offer.price_paise_per_kg - (
        logistics + handling + quality + transaction + financing + rejection
    )
    return EffectivePrice(
        buyer_id=offer.buyer_id,
        buyer_name=offer.buyer_name,
        headline_paise_per_kg=offer.price_paise_per_kg,
        effective_paise_per_kg=net,
        components={
            "headline": offer.price_paise_per_kg,
            "logistics": logistics,
            "handling": handling,
            "quality_loss": quality,
            "transaction": transaction,
            "financing": financing,
            "rejection": rejection,
            "effective": net,
            "quantity_kg_used": float(quantity),
            "distance_km": offer.distance_km,
            "payment_terms_days": offer.payment_terms_days,
            # Reported for visibility, excluded from `effective` on purpose: it is the same
            # under every option, so it cannot discriminate between them.
            "storage_already_sunk": sunk_storage,
            "days_held": lot.days_held,
        },
    )


def _normalise(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.5
    return max(0.0, min(1.0, (value - low) / (high - low)))


def score_offers(
    lot: Lot,
    offers: list[Offer],
    costs: CostModel,
    weights: AttractivenessWeights,
) -> list[BuyerScore]:
    """FR-543. Ranks offers, exposing every component of the composite.

    Reliability and rejection rate may be unknown for a new buyer. Unknown is treated as a
    neutral 0.5 rather than 0 — an absent record is not evidence of unreliability, and
    scoring it as such would quietly lock new buyers out of the FPO's market.
    """
    if not offers:
        return []

    priced = [(offer, effective_price(lot, offer, costs)) for offer in offers]
    nets = [ep.effective_paise_per_kg for _, ep in priced]
    low, high = float(min(nets)), float(max(nets))
    max_distance = max((o.distance_km for o in offers), default=1.0) or 1.0
    max_delay = max((o.payment_terms_days for o in offers), default=1) or 1

    scored: list[BuyerScore] = []
    for offer, ep in priced:
        notes: list[str] = []

        reliability = offer.reliability
        if reliability is None:
            reliability = 0.5
            notes.append("No settlement history — reliability treated as neutral, not poor.")
        # Priced into effective_price when known. Here we score only how *unsure* we are:
        # a buyer with no history carries risk we cannot quantify, which is different from
        # a buyer with a known-bad rate (already paid for in the price).
        rejection_uncertainty = 0.0 if offer.rejection_rate is not None else 0.5
        if offer.rejection_rate is None:
            notes.append(
                "No rejection history — no deduction applied, but the unknown is scored as risk."
            )

        fits_quantity = True
        quantity_fit = 1.0
        if offer.min_quantity_kg is not None and lot.quantity_kg < offer.min_quantity_kg:
            fits_quantity = False
            quantity_fit = float(lot.quantity_kg / offer.min_quantity_kg)
            notes.append(
                f"Lot is below this buyer's minimum "
                f"({float(lot.quantity_kg):,.0f} kg vs {float(offer.min_quantity_kg):,.0f} kg)."
            )
        elif offer.max_quantity_kg is not None and lot.quantity_kg > offer.max_quantity_kg:
            quantity_fit = float(offer.max_quantity_kg / lot.quantity_kg)
            notes.append("Buyer cannot take the whole lot; a split would be required.")

        meets_grade = True
        if (
            lot.grade
            and offer.grade_required
            and GRADE_ORDER.get(lot.grade, 3) > GRADE_ORDER.get(offer.grade_required, 0)
        ):
            meets_grade = False
            notes.append(
                f"Lot grade {lot.grade} is below the buyer's requirement {offer.grade_required}."
            )

        components: dict[str, Any] = {
            "effective_price_norm": _normalise(float(ep.effective_paise_per_kg), low, high),
            "reliability": reliability,
            "rejection_uncertainty": rejection_uncertainty,
            "payment_delay_norm": _normalise(float(offer.payment_terms_days), 0, float(max_delay)),
            "quantity_fit": quantity_fit,
            "distance_norm": _normalise(offer.distance_km, 0, max_distance),
            "weights": weights.as_dict(),
        }
        # Rejection risk is already priced into effective_price, so the composite must not
        # subtract it a second time. What remains here is the *uncertainty* about the rate,
        # not the expected loss itself.
        effective_norm = _normalise(float(ep.effective_paise_per_kg), low, high)
        delay_norm = _normalise(float(offer.payment_terms_days), 0, float(max_delay))
        distance_norm = _normalise(offer.distance_km, 0, max_distance)
        score = (
            weights.effective_price * effective_norm
            + weights.reliability * reliability
            - weights.rejection_risk * rejection_uncertainty
            - weights.payment_delay * delay_norm
            + weights.quantity_fit * quantity_fit
            - weights.distance * distance_norm
        )
        components["score"] = round(score, 4)

        scored.append(
            BuyerScore(
                effective=ep,
                attractiveness=round(score, 4),
                components=components,
                fits_quantity=fits_quantity,
                meets_grade=meets_grade,
                notes=notes,
            )
        )

    # Buyers who cannot legally take the lot sort last regardless of price — a high score on
    # an offer the lot does not qualify for is worse than useless.
    scored.sort(key=lambda s: (s.meets_grade, s.fits_quantity, s.attractiveness), reverse=True)
    return scored


def negotiation_brief(lot: Lot, best: BuyerScore, runner_up: BuyerScore | None) -> str:
    """FR-544. The asking price plus the evidence for it.

    Written as something a market officer can say out loud on a phone call, because that is
    where it will be used.
    """
    ep = best.effective
    lines = [
        f"Lot: {float(lot.quantity_kg):,.0f} kg {lot.crop_name}"
        + (f", grade {lot.grade}" if lot.grade else "")
        + (f", ready {lot.ready_date:%d %b}" if lot.ready_date else ""),
        f"Buyer: {ep.buyer_name} at ₹{ep.headline_paise_per_kg / 100:.2f}/kg headline.",
        f"After logistics, handling, quality, fees, storage, rejection risk and "
        f"{ep.components['payment_terms_days']}-day payment terms, this lands at "
        f"₹{ep.effective_paise_per_kg / 100:.2f}/kg - a deduction of "
        f"₹{ep.total_deduction / 100:.2f}/kg.",
    ]
    if runner_up is not None:
        r = runner_up.effective
        delta = ep.effective_paise_per_kg - r.effective_paise_per_kg
        lines.append(
            f"Next best is {r.buyer_name} at ₹{r.headline_paise_per_kg / 100:.2f}/kg headline, "
            f"₹{r.effective_paise_per_kg / 100:.2f}/kg effective — "
            f"{'behind' if delta > 0 else 'ahead'} by ₹{abs(delta) / 100:.2f}/kg."
        )
        if r.headline_paise_per_kg > ep.headline_paise_per_kg:
            lines.append(
                "Note the reversal: the higher headline price is the worse deal once the "
                "costs of realising it are counted. Worth saying so in the negotiation."
            )
    ask = round(ep.headline_paise_per_kg * 1.04)
    lines.append(
        f"Suggested ask: ₹{ask / 100:.2f}/kg, justified by lot size and delivery readiness."
    )
    for note in best.notes:
        lines.append(f"Caveat: {note}")
    return "\n".join(lines)


def allocate(
    lot: Lot, scored: list[BuyerScore], storage: StorageOption | None
) -> tuple[list[dict[str, Any]], Decimal, list[str]]:
    """FR-545. Greedy allocation across buyers, with the residual reported explicitly.

    Greedy rather than optimal on purpose: the ranking is already the judgement, and an
    allocation an FPO officer cannot follow by hand is one they will not trust. What matters
    is that whatever cannot be placed is *stated*, not quietly dropped.
    """
    remaining = lot.quantity_kg
    plan: list[dict[str, Any]] = []
    notes: list[str] = []

    for score in scored:
        if remaining <= 0:
            break
        if not score.meets_grade:
            continue
        offer_cap = Decimal(str(score.effective.components["quantity_kg_used"]))
        take = min(remaining, offer_cap)
        if take <= 0:
            continue
        plan.append(
            {
                "buyer_id": str(score.effective.buyer_id),
                "buyer_name": score.effective.buyer_name,
                "quantity_kg": float(take),
                "effective_paise_per_kg": score.effective.effective_paise_per_kg,
                "expected_value_paise": int(take) * score.effective.effective_paise_per_kg,
            }
        )
        remaining -= take

    if remaining > 0:
        if storage is None or storage.capacity_kg is None:
            notes.append(
                f"{float(remaining):,.0f} kg cannot be placed with the current offers, and "
                "storage capacity is unknown — this needs a human decision, not an assumption."
            )
        else:
            stored = min(remaining, storage.capacity_kg)
            plan.append(
                {
                    "buyer_id": None,
                    "buyer_name": "Storage",
                    "quantity_kg": float(stored),
                    "effective_paise_per_kg": -storage.cost_paise_per_kg_per_day,
                    "expected_value_paise": None,
                }
            )
            remaining -= stored
            if remaining > 0:
                notes.append(
                    f"{float(remaining):,.0f} kg exceeds both offers and storage capacity."
                )
    return plan, remaining, notes


# --------------------------------------------------------------------------- module entry


def run(inputs: ModuleInput) -> ModuleOutput:
    """Score every lot against every offer and propose an allocation.

    Signature and purity per ARCHITECTURE §3 — everything needed arrives in ``inputs``.
    """
    data = inputs.data
    costs: CostModel = data.get("costs") or CostModel()
    weights: AttractivenessWeights = data.get("weights") or AttractivenessWeights()
    lots: list[Lot] = data.get("lots") or []
    offers_by_crop: dict[str, list[Offer]] = data.get("offers_by_crop") or {}
    storage: StorageOption | None = data.get("storage")
    price_history: dict[str, list[PricePoint]] = data.get("price_history") or {}

    findings: list[Finding] = []
    actions: list[ProposedAction] = []
    degraded: list[str] = []

    if not lots:
        degraded.append("no lots available to sell")
    if not offers_by_crop:
        degraded.append("no buyer offers on record")

    for lot in lots:
        offers = offers_by_crop.get(lot.crop_name, [])
        if not offers:
            degraded.append(f"no offers for {lot.crop_name}")
            continue

        scored = score_offers(lot, offers, costs, weights)
        if not scored:
            continue
        best = scored[0]
        runner_up = scored[1] if len(scored) > 1 else None

        offer_evidence = [o.evidence for o in offers]

        findings.append(
            Finding(
                key=f"effective_price.{lot.crop_name.lower()}.{best.effective.buyer_name}",
                statement=(
                    f"{best.effective.buyer_name} offers "
                    f"₹{best.effective.headline_paise_per_kg / 100:.2f}/kg for "
                    f"{float(lot.quantity_kg):,.0f} kg of {lot.crop_name}, which lands at "
                    f"₹{best.effective.effective_paise_per_kg / 100:.2f}/kg after costs."
                ),
                magnitude=Decimal(best.effective.effective_paise_per_kg),
                unit="paise_per_kg",
                confidence=_confidence_for(best, costs),
                evidence=offer_evidence,
                assumptions=costs.sources(),
                affected=AffectedSet(lot_ids=[lot.id], quantity_kg=lot.quantity_kg),
            )
        )

        reversal = _detect_reversal(scored)
        if reversal is not None:
            findings.append(reversal)

        plan, residual, notes = allocate(lot, scored, storage)
        actions.append(
            ProposedAction(
                key=f"sell.{lot.id}",
                title=f"Sell {float(lot.quantity_kg):,.0f} kg {lot.crop_name} to "
                f"{best.effective.buyer_name}",
                rationale=negotiation_brief(lot, best, runner_up),
                recommendation_type="BUYER_SELECTION",
                target_type="lot",
                target_id=lot.id,
                value_paise=best.effective.effective_paise_per_kg,
                value_unit="paise_per_kg",
                expected_impact={
                    "allocation": plan,
                    "unplaced_kg": float(residual),
                    "notes": notes,
                    "components": best.components,
                    "effective_price_components": best.effective.components,
                },
                risks=notes + best.notes,
                alternatives=[
                    f"{s.effective.buyer_name}: "
                    f"₹{s.effective.effective_paise_per_kg / 100:.2f}/kg effective"
                    for s in scored[1:4]
                ],
                confidence=_confidence_for(best, costs),
                evidence=offer_evidence,
            )
        )

        trend = _price_trend(lot, price_history.get(lot.crop_name, []), inputs.as_of)
        if trend is not None:
            findings.append(trend)

        gap = _realisation_gap(lot, best, price_history.get(lot.crop_name, []))
        if gap is not None:
            findings.append(gap)

    return ModuleOutput(
        module=MODULE,
        version=VERSION,
        findings=findings,
        proposed_actions=actions,
        degraded_inputs=degraded,
    )


#: A crop plan costed at mandi prices is out by more than this much once the deductions
#: are taken. 0.12 rather than any gap at all: freight and handling always cost something,
#: and flagging a 3% gap would make the finding noise.
REALISATION_GAP_THRESHOLD = 0.12


def _realisation_gap(lot: Lot, best: BuyerScore, history: list[PricePoint]) -> Finding | None:
    """What the mandi quotes versus what the FPO actually banks (FR-542).

    This is the finding that keeps a crop plan honest. Farm economics are costed at the
    published modal price, because that is the only price anyone publishes — but nobody
    receives it. Freight, handling, grade loss, payment delay and rejection all come off
    first, and on the Prayagraj data the gap between the two runs to roughly a third.

    A plan showing a healthy margin at mandi prices can be underwater at realised ones, and
    the collective would find that out at settlement. Naming the gap as its own finding is
    what lets the orchestrator override a crop plan on evidence rather than on a hunch.
    """
    if not history:
        return None
    # Sorted here rather than trusted. `price_points` returns the series *ascending* by date,
    # and an earlier version of this function read `history[:30]` as "the most recent 30" —
    # so it compared today's offer against potato prices from two years earlier and reported
    # a 74% realisation gap that did not exist. Cheap to sort; expensive to be wrong.
    recent = [p.modal_paise_per_kg for p in sorted(history, key=lambda p: p.date)[-30:]]
    if not recent:
        return None
    reference = int(statistics.median(recent))
    if reference <= 0:
        return None
    realised = best.effective.effective_paise_per_kg
    gap = (reference - realised) / reference
    if gap < REALISATION_GAP_THRESHOLD:
        return None
    return Finding(
        key=f"price_realisation_gap.{lot.crop_name.lower()}",
        statement=(
            f"{lot.crop_name} realises ₹{realised / 100:.2f}/kg after costs against a mandi "
            f"modal of ₹{reference / 100:.2f}/kg — a {gap:.0%} gap. A plan costed at the "
            f"published price overstates this crop's margin by that much."
        ),
        magnitude=Decimal(str(round(gap, 3))),
        unit="share of mandi price lost to costs",
        confidence=_confidence_for(best, CostModel()),
        evidence=[history[0].evidence],
        assumptions=[
            "Compared against the median of the last 30 reported days, not a single day.",
            "The deductions are itemised in the effective-price breakdown; they are "
            "estimates from the cost model, not invoiced amounts.",
        ],
        affected=AffectedSet(lot_ids=[lot.id], quantity_kg=lot.quantity_kg),
    )


def _confidence_for(best: BuyerScore, costs: CostModel) -> float:
    """Confidence in the recommendation, not in the arithmetic.

    The subtraction is exact; what is uncertain is whether the cost assumptions hold and
    whether the buyer behaves as their history suggests. Unsourced cost defaults cap this,
    because a precise number built on a guessed freight rate is still a guess.
    """
    base = 0.80
    if best.effective.components["logistics"] > 0:
        base -= 0.10  # unsourced freight rate (seed/sources.md M11)
    if not best.fits_quantity:
        base -= 0.10
    if not best.meets_grade:
        base -= 0.20
    if "No settlement history" in " ".join(best.notes):
        base -= 0.05
    return max(0.30, min(0.95, base))


def _detect_reversal(scored: list[BuyerScore]) -> Finding | None:
    """The demo's beat 7: the highest headline price is not the best deal.

    Only reported when it is actually true. Asserting a reversal that did not happen would
    be the same failure as inventing a price.
    """
    eligible = [s for s in scored if s.meets_grade]
    if len(eligible) < 2:
        return None
    best = eligible[0]
    highest_headline = max(eligible, key=lambda s: s.effective.headline_paise_per_kg)
    if highest_headline.effective.buyer_id == best.effective.buyer_id:
        return None

    gap_headline = (
        highest_headline.effective.headline_paise_per_kg - best.effective.headline_paise_per_kg
    )
    gap_effective = (
        best.effective.effective_paise_per_kg - highest_headline.effective.effective_paise_per_kg
    )
    if gap_effective <= 0:
        return None

    return Finding(
        key="effective_price.reversal",
        statement=(
            f"{highest_headline.effective.buyer_name} offers "
            f"₹{gap_headline / 100:.2f}/kg more than {best.effective.buyer_name} on paper, but "
            f"lands ₹{gap_effective / 100:.2f}/kg less once logistics, payment terms and "
            f"rejection risk are counted."
        ),
        magnitude=Decimal(gap_effective),
        unit="paise_per_kg",
        confidence=0.85,
        evidence=[_ref(best), _ref(highest_headline)],
        assumptions=["Assumes the stated payment terms are honoured."],
    )


def _ref(score: BuyerScore) -> EvidenceRef:
    return EvidenceRef(
        kind="domain_row",
        id=score.effective.buyer_id,
        label=f"{score.effective.buyer_name} offer "
        f"₹{score.effective.headline_paise_per_kg / 100:.2f}/kg",
        as_of=dt.datetime.min.replace(tzinfo=dt.UTC),
    )


def _price_trend(lot: Lot, history: list[PricePoint], as_of: dt.datetime) -> Finding | None:
    """Where the market has been, so the recommendation is not read out of context.

    Reports a range and a direction, never a point forecast presented as fact (SAF-05).
    """
    if len(history) < 8:
        return None
    ordered = sorted(history, key=lambda p: p.date)
    recent = ordered[-30:]
    earlier = ordered[-180:-30] or ordered[:-30]
    if not earlier:
        return None

    recent_mean = sum(p.modal_paise_per_kg for p in recent) / len(recent)
    earlier_mean = sum(p.modal_paise_per_kg for p in earlier) / len(earlier)
    if earlier_mean == 0:
        return None
    change = (recent_mean - earlier_mean) / earlier_mean * 100

    lo = min(p.modal_paise_per_kg for p in recent)
    hi = max(p.modal_paise_per_kg for p in recent)
    direction = "risen" if change > 0 else "fallen"

    return Finding(
        key=f"price_trend.{lot.crop_name.lower()}",
        statement=(
            f"{lot.crop_name} modal price has {direction} {abs(change):.0f}% against the "
            f"preceding period; the last {len(recent)} trading days ranged "
            f"₹{lo / 100:.2f} to ₹{hi / 100:.2f}/kg."
        ),
        magnitude=Decimal(str(round(change, 1))),
        unit="pct_change",
        confidence=0.80,
        evidence=[p.evidence for p in recent[-3:]],
        assumptions=[
            "Trend describes the recorded past. It is not a forecast, and the module does "
            "not claim the direction will continue."
        ],
    )
