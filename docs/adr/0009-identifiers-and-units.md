# ADR-0009 — UUIDv7 identifiers and integer canonical units

Date: 2026-08-22 · Status: Accepted

## Context

The system computes money (funding allocations, effective prices, value at risk), area (plot
sizes in acres, hectares, bighas and local units), and mass (kg, quintal, tonne). It also joins
across an append-only event log where ordering matters, and it must survive a future where data
is merged across organizations or exported for research.

Two classes of bug are expensive here and effectively unfixable after the fact: floating-point
money errors that quietly compound through a multi-step effective-price calculation, and unit
confusion between acres and hectares in an agronomic formula.

## Decision

**Identifiers: UUIDv7.** Not sequential integers, not natural keys.

**Canonical units, enforced at the type level and named in every column:**

| Concern | Storage | Column naming | Rendered |
|---|---|---|---|
| Money | `BIGINT` paise | `*_paise` | ₹ with lakh/crore grouping in Hindi views |
| Area | `NUMERIC(14,2)` square metres | `*_sqm` | acres (`/4046.8564224`) or hectares |
| Mass | `NUMERIC(14,3)` kilograms | `*_kg` | kg / quintal / tonne |
| Price | `BIGINT` paise per kilogram | `*_paise_per_kg` | ₹/kg or ₹/quintal |
| Water | `NUMERIC` litres | `*_litres` | litres / m³ |
| Time | `TIMESTAMPTZ` UTC | `*_at` | `Asia/Kolkata` |
| Geometry | `geography(Polygon, 4326)` | `boundary` | map |

Conversion happens only at the presentation edge. No float ever holds money.

## Consequences

**Easier.** UUIDv7 is time-ordered, so the event log and every append-only table index well
without a sequence, and `ORDER BY id` is chronological. Ids can be generated client-side, which
matters for offline capture later. Merging data across organizations or exporting a research
dataset needs no id remapping. Integer paise makes money arithmetic exact. Unit suffixes in
column names mean a unit mistake is visible in code review rather than in a wrong recommendation.

**Harder.** UUIDs are 16 bytes rather than 4 or 8, and are unpleasant to type in a debugging
session. Every display of money or area needs an explicit conversion, which is more code than
`{price}`. Square metres is not how anyone talks about Indian farmland, so the seed and the UI
both do conversion work.

**Accepted.** The verbosity is the point: a formula that reads `area_sqm` cannot silently be fed
acres, and a total that reads `_paise` cannot silently be added to rupees.

## Alternatives considered

- **Sequential `BIGSERIAL`.** Smaller and friendlier to debug. Rejected: leaks row counts,
  requires a round trip before insert, and makes cross-organization merges a remapping exercise.
- **UUIDv4.** Random, so index locality on append-only tables is poor — the exact tables that
  grow fastest here.
- **`NUMERIC` rupees for money.** Exact, and more readable than paise. Rejected: `NUMERIC` is
  slower to aggregate, and the discipline of an integer type is what actually prevents a float
  creeping in through an ORM default or a JSON round trip.
- **Acres as the canonical area unit.** Rejected: agronomic coefficients are published per
  hectare, and having two land units in the codebase is how the conversion bug happens.
