# ADR-0016 — MSP is a price floor, not a buyer offer

Date: 2026-08-28 · Status: Proposed

## Context

The seed prices the government procurement centre as a multiplier on the mandi modal price:

```python
# seed/generator.py:955
"Govt Procurement Centre": (1.05, "MSP-linked"),
```

The comment above that table explains the intent — *"Multipliers, not absolute rupees — so the
seed tracks the real market instead of drifting away from it."* That reasoning is right for
every other buyer in the table and wrong for this one.

A Minimum Support Price is not a function of the market price. It is set administratively by
CACP ahead of the season, published per crop, and its entire purpose is to **hold when the
market falls**. Modelling it as `market × 1.05` inverts that: when the mandi price collapses,
the modelled MSP collapses with it, and the one instrument designed to put a floor under the
farmer disappears exactly when it would matter.

This is not academic here. `PROGRESS.md` records the demo moving off a weather story onto a
price story, because the evidence supported it: the potato harvest lands on the annual price
floor. A price-crash narrative running on a model where the floor falls with the price is
telling the wrong story about how Indian agricultural markets actually work.

Real MSP is now available and current to 2025-26 (`seed/generated/batch1_msp/`), alongside
procurement quantities and farmers benefited (`batch6_procurement/`). Ingesting it forces the
modelling question rather than merely improving a constant.

Three further facts constrain the design:

* **Not every crop has an MSP.** Wheat, paddy, mustard, gram, lentil, barley and the kharif
  list are notified. **Potato and guava are not** — and potato is the demo's headline crop.
* **An announced MSP is not an available price.** It is realisable only where a procurement
  centre is operating, the window is open, the quality specification is met, and quota
  remains. `seed/learning.py:284` already records one such friction: *"the procurement centre
  pays MSP with a 21-day settlement."*
* `effective_price()` already deducts logistics, quality loss, financing, storage and
  rejection per buyer. MSP does not interact with those the way a private offer does.

## Decision

**MSP is modelled as a floor attribute of a crop-season, not as a `Buyer` offer.**

The market module gains four distinct quantities, which the system currently cannot tell
apart and which the product brief explicitly requires be kept apart:

| Quantity | Meaning | Source |
|---|---|---|
| `msp_announced` | CACP's notified price for the crop-season | batch 1, national |
| `procurement_available` | whether a centre is open, in window, with quota | batch 6 |
| `market_price` | mandi modal price | Agmarknet, already ingested |
| `effective_realization` | what the farmer actually nets, after deductions and settlement lag | `effective_price()`, already computed |

Consequences of the split:

* MSP sets a **floor on realisation**, applied only when `procurement_available` holds. An
  announced MSP with no operating centre is a policy fact, not a price, and must never be
  offered to a farmer as though it were bankable.
* **A crop with no MSP is a positive finding**, not a null. "There is no MSP for potato" is
  true, decision-relevant, and the reason an FPO's own marketing decision carries more weight
  for potato than for wheat. The module states it rather than skipping it.
* The `Govt Procurement Centre` buyer keeps its settlement terms, quality specification and
  distance, because those are genuine buyer attributes. What it loses is its price
  multiplier: its price becomes the MSP, from the data.

## Consequences

Easier: the four-way distinction becomes expressible, so the system can answer *"is the
market above or below MSP right now"* — which is the question that decides whether an FPO
should sell to a private buyer or move a lot to a procurement centre.

Easier: MSP stops drifting with the market in the seed, so a price-crash scenario behaves the
way the real instrument behaves.

Harder: `for_market` must gather a national MSP series, a procurement-availability signal and
a mandi series, and reconcile three temporal granularities — MSP is per season, procurement is
per window, prices are daily.

Accepted: procurement availability is thin. Batch 6 is national and one state-wise quarter,
so availability will initially be a coarse or seeded signal. That is acceptable **only if it
is labelled**, because presenting a floor as reachable when no centre is open is precisely the
harm this ADR exists to prevent.

## Alternatives considered

**Keep MSP as a buyer with a corrected multiplier.** Rejected. Any multiplier still ties the
floor to the market. The defect is structural, not a matter of calibration.

**Make MSP a hard floor on the reported price, unconditionally.** Rejected. It would promise
farmers a price that is unreachable wherever procurement is not operating, which is a real
harm of exactly the kind `seed/sources.md` warns about for scheme eligibility.

**Defer until procurement data is richer.** Rejected. The inverted relationship is live in the
seed today and mis-states the demo's central story. A coarse but correctly-shaped floor beats
a precisely-wrong multiplier.
