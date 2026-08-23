"""Market Intelligence tests — FR-541…548.

The headline case is demo beat 7: a nearby buyer offering less per kg beats a distant one
offering more, once the cost of actually realising the price is counted.

These are pure-function tests. No database, no network — which is the point of the module
contract, and what makes the replay property possible.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest

from agrivardhak.intelligence import market
from agrivardhak.intelligence.contracts import EvidenceRef, ModuleInput

NOW = dt.datetime(2026, 8, 22, 6, 0, tzinfo=dt.UTC)
ORG = uuid.uuid4()


def _ref(label: str = "offer") -> EvidenceRef:
    return EvidenceRef(kind="domain_row", id=uuid.uuid4(), label=label, as_of=NOW)


def _lot(qty: float = 200_000, grade: str | None = "A", **kw) -> market.Lot:
    return market.Lot(
        id=kw.pop("id", uuid.uuid4()),
        crop_name=kw.pop("crop_name", "Potato"),
        quantity_kg=Decimal(str(qty)),
        grade=grade,
        ready_date=kw.pop("ready_date", dt.date(2026, 9, 1)),
        **kw,
    )


def _offer(
    name: str, price_rupees_per_kg: float, distance_km: float, terms: int, **kw
) -> market.Offer:
    return market.Offer(
        buyer_id=kw.pop("buyer_id", uuid.uuid4()),
        buyer_name=name,
        price_paise_per_kg=int(price_rupees_per_kg * 100),
        quantity_kg=Decimal(str(kw.pop("quantity_kg", 300_000))),
        grade_required=kw.pop("grade_required", "A"),
        distance_km=distance_km,
        payment_terms_days=terms,
        reliability=kw.pop("reliability", 0.9),
        rejection_rate=kw.pop("rejection_rate", 0.03),
        min_quantity_kg=kw.pop("min_quantity_kg", None),
        max_quantity_kg=kw.pop("max_quantity_kg", None),
        evidence=kw.pop("evidence", None) or _ref(name),
        **kw,
    )


# --------------------------------------------------------------------------- the reversal


def test_nearby_cheaper_buyer_beats_distant_dearer_one() -> None:
    """FR-542, demo beat 7.

    ₹34/kg at 180 km on 60-day terms with an 11% rejection rate, against ₹30/kg at 22 km on
    15-day terms with 3%. The headline ranking reverses once the cost of realising the price
    is subtracted.

    The ₹4/kg gap is deliberate. An earlier draft used ₹35 vs ₹30 and the reversal did not
    happen: freight over 180 km is only ~₹0.81/kg, nowhere near enough to close a ₹5 gap.
    See ``test_rejection_risk_dominates_the_deduction`` for what actually closes it.
    """
    lot = _lot(qty=200_000)
    near = _offer(
        "Ganga Cold Store", 30.0, distance_km=22, terms=15, reliability=0.92, rejection_rate=0.03
    )
    far = _offer(
        "Kanpur Wholesale", 34.0, distance_km=180, terms=60, reliability=0.68, rejection_rate=0.11
    )

    near_ep = market.effective_price(lot, near, market.CostModel())
    far_ep = market.effective_price(lot, far, market.CostModel())

    assert far_ep.headline_paise_per_kg > near_ep.headline_paise_per_kg
    assert near_ep.effective_paise_per_kg > far_ep.effective_paise_per_kg, (
        "the whole product thesis is that price is not value"
    )


def test_every_deduction_is_itemised() -> None:
    """FR-543: a score an FPO cannot decompose is a score they should not act on."""
    ep = market.effective_price(_lot(), _offer("B", 30.0, 100, 30), market.CostModel())
    for term in (
        "headline",
        "logistics",
        "handling",
        "quality_loss",
        "transaction",
        "financing",
        "rejection",
        "effective",
        # Reported but NOT part of the sum below — see the sunk-cost test that follows.
        "storage_already_sunk",
    ):
        assert term in ep.components, f"missing component: {term}"
    total = sum(
        ep.components[k]
        for k in (
            "logistics",
            "handling",
            "quality_loss",
            "transaction",
            "financing",
            "rejection",
        )
    )
    assert ep.components["headline"] - total == ep.components["effective"], (
        "the itemised deductions must actually sum to the difference"
    )


def test_storage_already_paid_does_not_reduce_what_a_buyer_is_worth() -> None:
    """Sunk cost must not enter the buyer comparison, and this one nearly did.

    A potato lot held 292 days had accrued 292 paise/kg of storage. Deducting it turned a
    ₹7.05/kg offer into ₹3.23/kg effective — a number that would talk an FPO out of a fair
    sale and into paying rent on the same potatoes for another season. The cost is real and
    it is gone; it is identical whichever buyer is chosen, so it cannot discriminate between
    them. It is reported, not subtracted.
    """
    fresh = market.effective_price(
        _lot(days_held=0), _offer("B", 30.0, 100, 30), market.CostModel()
    )
    held = market.effective_price(
        _lot(days_held=292), _offer("B", 30.0, 100, 30), market.CostModel()
    )

    assert held.effective_paise_per_kg == fresh.effective_paise_per_kg, (
        "months in store must not change what this buyer's offer is worth today"
    )
    assert held.components["storage_already_sunk"] > 0, "but the CEO must still be told it"
    assert held.components["days_held"] == 292


def test_reversal_is_reported_as_a_finding() -> None:
    lot = _lot(qty=200_000)
    offers = [
        _offer("Ganga Cold Store", 30.0, 22, 15),
        _offer("Kanpur Wholesale", 34.0, 180, 60, reliability=0.68, rejection_rate=0.11),
    ]
    scored = market.score_offers(lot, offers, market.CostModel(), market.AttractivenessWeights())
    finding = market._detect_reversal(scored)
    assert finding is not None
    assert "on paper" in finding.statement
    assert finding.evidence, "a claim without evidence must not exist"


def test_no_reversal_claimed_when_there_is_none() -> None:
    """Asserting a reversal that did not happen is the same failure as inventing a price."""
    lot = _lot()
    offers = [
        _offer("Near and dear", 35.0, 20, 10),
        _offer("Far and cheap", 28.0, 200, 60),
    ]
    scored = market.score_offers(lot, offers, market.CostModel(), market.AttractivenessWeights())
    assert market._detect_reversal(scored) is None


# --------------------------------------------------------------------------- cost terms


def test_freight_per_kg_falls_as_the_load_grows() -> None:
    """Why aggregation is the FPO's advantage — the module has to model it."""
    costs = market.CostModel()
    small = market.logistics_paise_per_kg(100, Decimal("1000"), costs)
    large = market.logistics_paise_per_kg(100, Decimal("100000"), costs)
    assert small == large, "freight is charged per tonne-km, so per-kg cost is load-independent"

    near = market.logistics_paise_per_kg(20, Decimal("50000"), costs)
    far = market.logistics_paise_per_kg(200, Decimal("50000"), costs)
    assert far > near * 5


def test_rejection_risk_dominates_the_deduction() -> None:
    """The demo's real insight: it is not the distance that kills the distant buyer.

    Freight over 180 km costs ~₹0.81/kg. An 11% rejection rate on ₹34/kg costs ₹3.74/kg —
    more than four times as much. Produce a buyer rejects is produce the farmer is not paid
    for, so it belongs in the subtraction, not only in a risk score.
    """
    lot = _lot(qty=200_000)
    far = _offer("Kanpur Wholesale", 34.0, 180, 60, reliability=0.68, rejection_rate=0.11)
    components = market.effective_price(lot, far, market.CostModel()).components

    assert components["rejection"] > components["logistics"] * 4
    assert components["rejection"] > components["financing"] * 4
    assert components["rejection"] == max(
        components[k]
        for k in (
            "logistics",
            "handling",
            "quality_loss",
            "transaction",
            "financing",
            "rejection",
        )
    )


def test_unknown_rejection_rate_is_not_priced_as_a_deduction() -> None:
    """We do not fabricate a deduction we have no basis for.

    The uncertainty is carried in the score and the confidence instead — inventing a
    rejection rate for a buyer with no history would be inventing a price.
    """
    lot = _lot()
    unknown = _offer("New entrant", 30.0, 50, 20, rejection_rate=None)
    assert market.effective_price(lot, unknown, market.CostModel()).components["rejection"] == 0


def test_payment_delay_has_a_price() -> None:
    """₹35/kg in 90 days is not ₹35/kg."""
    costs = market.CostModel()
    immediate = market.financing_paise_per_kg(3500, 0, costs)
    delayed = market.financing_paise_per_kg(3500, 90, costs)
    assert immediate == 0
    assert delayed > 100  # more than ₹1/kg at 14% over 90 days


def test_grade_shortfall_costs_but_grade_surplus_earns_nothing() -> None:
    costs = market.CostModel()
    shortfall = market.quality_loss_paise_per_kg("C", "A", 3000, 1, False, costs)
    exact = market.quality_loss_paise_per_kg("A", "A", 3000, 1, False, costs)
    surplus = market.quality_loss_paise_per_kg("A", "C", 3000, 1, False, costs)
    assert shortfall > 0
    assert exact == 0
    assert surplus == 0, "a buyer pays their stated price; a better grade earns no bonus here"


def test_perishables_lose_value_in_transit() -> None:
    costs = market.CostModel()
    storable = market.quality_loss_paise_per_kg("A", "A", 3000, 4, False, costs)
    perishable = market.quality_loss_paise_per_kg("A", "A", 3000, 4, True, costs)
    assert perishable > storable == 0


# --------------------------------------------------------------------------- scoring


def test_unknown_reliability_is_neutral_not_zero() -> None:
    """An absent record is not evidence of unreliability.

    Scoring a new buyer as untrustworthy would quietly lock them out of the FPO's market.
    """
    lot = _lot()
    known = _offer("Known", 30.0, 50, 20, reliability=0.9, rejection_rate=0.05)
    unknown = _offer("New entrant", 30.0, 50, 20, reliability=None, rejection_rate=None)
    scored = market.score_offers(
        lot, [known, unknown], market.CostModel(), market.AttractivenessWeights()
    )
    new_score = next(s for s in scored if s.effective.buyer_name == "New entrant")
    assert new_score.components["reliability"] == 0.5
    assert any("neutral" in n or "unknown" in n.lower() for n in new_score.notes), (
        "the assumption must be stated"
    )


def test_ineligible_buyers_sort_last_regardless_of_price() -> None:
    """A high score on an offer the lot cannot fill is worse than useless."""
    lot = _lot(qty=5_000, grade="C")
    generous_but_impossible = _offer("Premium processor", 40.0, 30, 10, grade_required="A")
    modest_but_workable = _offer("Local trader", 25.0, 20, 7, grade_required="C")
    scored = market.score_offers(
        lot,
        [generous_but_impossible, modest_but_workable],
        market.CostModel(),
        market.AttractivenessWeights(),
    )
    assert scored[0].effective.buyer_name == "Local trader"
    assert scored[-1].meets_grade is False


def test_weights_are_exposed_with_the_score() -> None:
    scored = market.score_offers(
        _lot(), [_offer("B", 30.0, 50, 20)], market.CostModel(), market.AttractivenessWeights()
    )
    assert "weights" in scored[0].components
    assert sum(scored[0].components["weights"].values()) == pytest.approx(1.0)


# --------------------------------------------------------------------------- allocation


def test_allocation_reports_what_it_could_not_place() -> None:
    """FR-545. Silent truncation reads as 'covered everything' when it did not."""
    lot = _lot(qty=500_000)
    offers = [_offer("Small buyer", 30.0, 20, 15, quantity_kg=100_000)]
    scored = market.score_offers(lot, offers, market.CostModel(), market.AttractivenessWeights())
    _plan, residual, notes = market.allocate(lot, scored, storage=None)

    assert residual > 0
    assert notes, "unplaced quantity must be stated, not dropped"
    assert "unknown" in " ".join(notes).lower()


def test_unknown_storage_capacity_is_not_treated_as_zero() -> None:
    """FR-103: planning as if a store does not exist silently drops a real option."""
    lot = _lot(qty=500_000)
    offers = [_offer("Small buyer", 30.0, 20, 15, quantity_kg=100_000)]
    scored = market.score_offers(lot, offers, market.CostModel(), market.AttractivenessWeights())

    unknown = market.StorageOption(capacity_kg=None, cost_paise_per_kg_per_day=2)
    _, _, notes = market.allocate(lot, scored, storage=unknown)
    assert any("human decision" in n for n in notes)

    known = market.StorageOption(capacity_kg=Decimal("400000"), cost_paise_per_kg_per_day=2)
    plan, residual, _ = market.allocate(lot, scored, storage=known)
    assert any(row["buyer_name"] == "Storage" for row in plan)
    assert residual == 0


# --------------------------------------------------------------------------- module contract


def test_run_produces_findings_and_actions_with_evidence() -> None:
    lot = _lot(qty=200_000)
    inputs = ModuleInput(
        organization_id=ORG,
        as_of=NOW,
        data={
            "lots": [lot],
            "offers_by_crop": {
                "Potato": [
                    _offer("Ganga Cold Store", 30.0, 22, 15),
                    _offer(
                        "Kanpur Wholesale", 34.0, 180, 60, reliability=0.68, rejection_rate=0.11
                    ),
                ]
            },
            "storage": market.StorageOption(Decimal("400000"), 2),
        },
    )
    out = market.run(inputs)

    assert out.module == market.MODULE
    assert out.version == market.VERSION
    assert out.findings and out.proposed_actions
    for finding in out.findings:
        assert finding.evidence, f"unevidenced finding: {finding.key}"
    action = out.proposed_actions[0]
    assert action.recommendation_type == "BUYER_SELECTION"
    assert action.alternatives, "FR-544 requires alternatives, not just a winner"
    assert "effective" in action.rationale.lower()


def test_run_degrades_rather_than_failing_when_inputs_are_missing() -> None:
    """NFR-301: a dead source lowers one module's confidence, it does not fail the request."""
    out = market.run(ModuleInput(organization_id=ORG, as_of=NOW, data={}))
    assert out.findings == []
    assert out.degraded_inputs, "the degradation must be reported, not silent"
    assert out.confidence == 0.0


def test_module_is_pure_and_replayable() -> None:
    """ARCHITECTURE §9: same input, byte-identical output. This is what makes replay work."""
    lot = _lot(qty=200_000, id=uuid.UUID(int=1))
    buyer_a, buyer_b = uuid.UUID(int=2), uuid.UUID(int=3)
    data = {
        "lots": [lot],
        "offers_by_crop": {
            "Potato": [
                _offer(
                    "A",
                    30.0,
                    22,
                    15,
                    buyer_id=buyer_a,
                    evidence=EvidenceRef(kind="domain_row", id=buyer_a, label="a", as_of=NOW),
                ),
                _offer(
                    "B",
                    35.0,
                    180,
                    60,
                    buyer_id=buyer_b,
                    evidence=EvidenceRef(kind="domain_row", id=buyer_b, label="b", as_of=NOW),
                ),
            ]
        },
    }
    first = market.run(ModuleInput(organization_id=ORG, as_of=NOW, data=data))
    second = market.run(ModuleInput(organization_id=ORG, as_of=NOW, data=data))
    assert first.model_dump_json() == second.model_dump_json()


def test_price_trend_states_a_range_never_a_forecast() -> None:
    """SAF-05: price guidance is a range with a direction, not a point prediction."""
    history = [
        market.PricePoint(
            date=dt.date(2026, 1, 1) + dt.timedelta(days=i),
            modal_paise_per_kg=2000 - i * 5,
            arrivals_kg=Decimal("1000"),
            market_name="Prayagraj APMC",
            evidence=_ref("agmarknet"),
        )
        for i in range(200)
    ]
    finding = market._price_trend(_lot(), history, NOW)
    assert finding is not None
    assert "ranged" in finding.statement
    assert any("not a forecast" in a for a in finding.assumptions)
