# ADR-0005 — Observation-centric provenance for volatile facts only

Date: 2026-08-22 · Status: Accepted

## Context

Discovery established provenance as fundamental, not metadata fluff: every consequential value
must answer *what is this, where did it come from, when was it observed, who verified it, how
confident are we, is it stale?* And when sources disagree — farmer says 2 acres, government
record says 1.6, field officer says 1.8 — the system must **show the discrepancy and request
verification**, never silently pick a winner.

The naive implementation attaches `{source, timestamp, confidence, verification}` to every
column of every table. That produces EAV sprawl: unqueryable, unindexable, and unworkable under
a 72-hour clock. The other extreme — provenance on nothing — loses the property the product
depends on.

## Decision

Split by volatility and decision impact.

| Fact kind | Storage | Examples |
|---|---|---|
| **Stable**, low decision impact | plain column on the entity | farmer name, phone, plot registration id |
| **Volatile and consequential** | append-only `Observation` rows with full provenance | crop health, disputed plot area, soil pH, expected yield, water availability, livestock count |
| **External** | `ExternalRecord` (raw payload retained) + derived `Observation` | rainfall, mandi price, scheme text |
| **Derived** | `Prediction` / module output | expected grade distribution |

A `current_observation` materialized view resolves the current value per
`(subject_type, subject_id, attribute)` so ordinary queries stay simple.

Effective confidence combines source trust, verification status and age-based decay:

```
effective = base_trust × verification_multiplier × 0.5 ^ (age_days / half_life_days)
```

Half-lives are per-attribute policy (crop health 7 days, plot area 365 days), stored in
`attribute_policy` rather than hard-coded.

Conflicts beyond a per-attribute tolerance create a `DataDiscrepancy` recording every claimed
value with its source, surfaced at the point of use, penalizing downstream confidence by
`(1 − min(0.4, spread_pct/100))`. Resolution requires a human with verification authority.

## Consequences

**Easier.** Provenance is real where it matters and absent where it would only be noise. The
conflict penalty is applied once, at the resolution layer, so it propagates automatically into
every module and into the packet's overall confidence — no module has to remember to apply it.
Decay makes staleness a first-class, automatic property rather than a manual review.

**Harder.** Two ways to read a value: a column, or the observation view. Developers must know
which attributes are observation-backed. Mitigated by keeping the list in `attribute_policy`
and by repository methods that hide the difference.

**Accepted.** Half-lives are initially judgement calls, not empirically derived. They are
configuration, visible in the admin UI, and refinable as outcome data accumulates.

## Alternatives considered

- **Full EAV provenance on every field.** Rejected: unqueryable and a schedule risk.
- **Provenance as a JSONB sidecar column per table.** Rejected: cannot query history, cannot
  express two competing claims simultaneously, and so cannot represent a discrepancy at all.
- **Bitemporal tables (valid time + transaction time) everywhere.** Correct and more general,
  but a much larger conceptual load; `observed_at` + `recorded_at` on observations gives us the
  bitemporality we actually need, where we need it.
