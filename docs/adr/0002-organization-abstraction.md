# ADR-0002 — Generic `Organization` rather than `FPO` as the core entity

Date: 2026-08-22 · Status: Accepted

## Context

Discovery answered "which collectives?" with **FPOs, PACS and SHGs**. These differ in legal
form, governance and money flow. They do not differ in what the intelligence layer needs:
members, land, crops, production, risk, buyers, schemes, resources.

Open question Q1 from the session: generic `Organization`, or `FPO` as the core?

## Decision

A generic **`Organization`** with `type ∈ {FPO, PACS, SHG, FPC, COOPERATIVE}`. Every
intelligence module, every query and every prompt operates on `Organization`. Type-specific
governance lives in a `GovernanceProfile` value object, not in branching logic.

## Consequences

**Easier.** Supporting PACS post-hackathon is `organization.type = 'PACS'` plus a governance
profile — not a schema migration across every table that references the collective. Aggregations
and drill-downs are written once.

**Harder.** A small amount of vocabulary friction: the UI says "FPO" while the code says
`Organization`. This is handled by a display-name mapping, and the glossary makes the rule explicit.

**Accepted.** One enum column today buys the multi-form story the brief asked for.

## Alternatives considered

- **`FPO` as the concrete core, generalize later.** Rejected: "generalize later" across an
  entity referenced by every other table is the migration nobody performs. The cost of doing it
  now is one column.
- **Separate FPO / PACS / SHG tables with a shared interface.** Rejected: triples the schema
  and forces polymorphic joins everywhere, for differences the intelligence layer never reads.
