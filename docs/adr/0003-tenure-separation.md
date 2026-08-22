# ADR-0003 — Separate land ownership, cultivation responsibility and membership

Date: 2026-08-22 · Status: Accepted

## Context

Question Q3 from discovery: can multiple farmers work the same land — husband and wife jointly,
or A owns while B cultivates? The answer was yes, and the session proposed separating land
ownership from cultivation responsibility from FPO membership.

Indian smallholder agriculture makes this the normal case: tenancy, leasing, sharecropping,
undivided family holdings, and land whose record of rights does not match who farms it.

## Decision

Three distinct relationships:

| Relationship | Entity |
|---|---|
| The physical land | `Plot` |
| Who holds it and how | `PlotTenure` (type, share %, validity period, evidence ref) |
| Who runs the operation | `Farm.operator_farmer_id` |
| Organizational tie | `Membership` |

`plot.farmer_id` does not exist.

Active tenure shares on a plot must sum to 100%. When they do not, the system raises a
`DataDiscrepancy` rather than rejecting the write — real records are messy, and refusing the
write destroys information we need.

## Consequences

**Easier.** Three things become possible that a `farmer_id` column makes impossible:
benefit attribution (who receives a subsidy for this plot?), dispute resolution (whose share
of the harvest?), and correct aggregation (a leased plot no longer double-counts across two
farmers). This directly serves the originating pain — *"FPO disputes cause loss to farmers as
their shares get lost."*

**Harder.** Every "who farms this plot?" query becomes a join with a temporal predicate.
Wrapped in a repository method (`current_tenure_holders(plot_id, as_of)`) so it is written once.

**Accepted.** The join cost is small; the modelling error would be permanent.

## Alternatives considered

- **`plot.farmer_id`.** Rejected as above.
- **Ownership on `Plot`, cultivation on `CropCycle`.** Closer, but cannot express joint
  holdings or a tenure that changes mid-season, and gives no place for share percentages.
- **A generic `PartyRole` table over any entity.** Too abstract; unqueryable under time pressure.
