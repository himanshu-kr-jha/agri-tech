# ADR-0004 — Freeze an immutable evidence snapshot on every recommendation

Date: 2026-08-22 · Status: Accepted

## Context

Question Q6 from discovery: should a recommendation preserve the exact evidence used when it
was generated? The scenario given was precise — the AI recommends Buyer A; three days later
market prices change; we still need to answer *"why did the AI recommend Buyer A on 22 August?"*

The alternative is recomputing the historical recommendation from live data, which produces a
different answer than the one that was actually given.

## Decision

At generation time, every recommendation persists an **immutable, content-hashed
`EvidenceSnapshot`** containing every input used: module outputs, the observations with their
provenance as of that instant, referenced external records, organization state, prompt version,
model id and module versions. SHA-256 over canonical JSON. UPDATE and DELETE are revoked on the
table at the grant level.

Historical recommendations are explained **only** from the snapshot. Recomputation is prohibited.

## Consequences

**Easier.** Every past decision is permanently explainable — the audit property the whole
product rests on, and the basis of the demo's "audit moment". Prediction error can be measured
against the inputs the model actually saw. Module purity plus a stored snapshot gives a replay
test that proves the architecture holds. Tamper-evidence without a blockchain, which is exactly
the "very strong audit trail, not necessarily blockchain" the session asked for.

**Harder.** Storage: roughly 20–80 KB per recommendation, under 2 GB per season at 1,000
farmers × 20 recommendations. Snapshot assembly adds latency to generation. Schema evolution
must tolerate old snapshot shapes — handled by versioning the payload.

**Accepted.** Storage is cheap; an unexplainable decision is not.

## Alternatives considered

- **Store only input ids and re-fetch.** Rejected: observations are append-only but *current
  values* change, and external prices change hourly. Re-fetching reconstructs a different world.
- **Store a rendered explanation string.** Rejected: prose cannot be re-validated, replayed or
  diffed, and cannot support prediction-error measurement.
- **Event sourcing the entire system.** Would give point-in-time reconstruction for free, but is
  a far larger commitment than 72 hours allows, and the snapshot gets us the property we need.
