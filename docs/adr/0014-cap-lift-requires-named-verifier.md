# ADR-0014 — Lifting a confidence cap requires a named verifier

Date: 2026-08-28 · Status: Proposed

## Context

Unsourced values in this repository are not merely labelled — they are *capped*, and the caps
are load-bearing:

| Debt | Cap | Effect |
|---|---|---|
| Crop-protection conditions (`sources.md` §13, P1–P7) | **0.42** | Below the orchestrator's 0.45 floor, so an unsourced diagnosis is structurally incapable of driving a recommendation |
| Cost of cultivation (§12, E1–E6) | **0.62** | Caps the whole Farm module |
| Scheme eligibility rules (§14) | **0.55** | Carried as `rules_verified=False` |

Lifting a cap is therefore not a bookkeeping act. It is the moment a previously inert number
starts influencing advice a farmer may act on. `seed/sources.md` states the stake plainly:
*"telling a farmer they qualify for a benefit they do not is a real harm."*

The tempting automation is to lift a cap as soon as a `source_ref` is present. But the thing
being asserted is *"this transcription faithfully represents the published text"* — and a
fetch cannot assert that. A mis-parsed PDF table, a column misaligned by one, or a fluent
mistranslation would all promote themselves into a benefits claim.

## Decision

A confidence cap lifts **only** when a human sets `verified_by`, and the corresponding
`seed/sources.md` row exists and carries a licence.

This mirrors INV-1 structurally rather than by convention: no code path writes `EXECUTED`
without an `Approval` row signed by a human; no code path lifts a cap without a verifier.

## Consequences

Easier: an audit can answer "who decided this number was trustworthy, and when" — which is
currently unanswerable.

Harder: sourcing throughput is bounded by human review, not by fetch speed. Filling 50 `TODO`
rows in `sources.md` is now explicitly a review exercise with a fetch attached, not a scrape.

Accepted: that bound is the point. The alternative is a system whose confidence rises whenever
a parser runs.

## Alternatives considered

**Automatic on `source_ref` presence.** Rejected — see above; it makes parser bugs
indistinguishable from verified facts.

**Automatic above a trust threshold.** Rejected. Source authority says nothing about whether
*our extraction of it* was correct, and extraction is where the error actually occurs.
