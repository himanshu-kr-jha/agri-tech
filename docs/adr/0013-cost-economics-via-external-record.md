# ADR-0013 — Cost economics as ExternalRecord, gathered by the orchestrator

Date: 2026-08-28 · Status: Proposed

## Context

`CROP_ECONOMICS` is a module-level dict in `intelligence/farm.py`, and `orchestrator/gather.py`
imports it directly (`farm.CROP_ECONOMICS[crop_name]`, lines 564 and 859). The module docstring
claims *"Replacing one with a cited figure is a one-line change to `CROP_ECONOMICS`."*

That claim holds only while the data is five hardcoded crops. It fails once costs are real,
UP-wide, versioned by year and revisable, because two repository rules apply:

- Intelligence modules are pure functions — no DB, no network, no clock (`CLAUDE.md` §6).
- `ModuleInput` is documented as *"Everything a module gets. Gathered by the orchestrator,
  never fetched by the module."*

So real cost data cannot simply replace the dict in place. And `gather.py` reaching into
another module's constants is already the wrong direction of dependency.

## Decision

Real cost data lands as **`ExternalRecord` rows under a new `COST_OF_CULTIVATION` kind.**
The orchestrator resolves them and passes them in `ModuleInput.data`. `CROP_ECONOMICS` is
demoted from source-of-truth to a **labelled synthetic fallback** for crops with no sourced
costs, which ADR-0012 keeps out of the ranking anyway.

This follows the precedent `ingestion/agmarknet.py` already set, and its reasoning transfers
verbatim: *"a mandi price is not about any of our subjects; it is a fact about the world that
our claims cite."* A state cost-of-cultivation figure is the same kind of fact.

## Consequences

Easier: module purity is preserved, so replay against a stored `EvidenceSnapshot` still
reproduces the confidence it produced on the day (INV-2). Raw payloads are retained for
evidence for free, because that is what `ExternalRecord` is for.

Harder: `gather.py` must resolve economics per crop per year, and handle the case where a
crop has sourced costs for some years and not others.

Accepted: one more gather step on a path that is already the orchestrator's job.

## Alternatives considered

**A typed `crop_economics` table.** Rejected — it duplicates what `ExternalRecord` does,
and loses the retained raw payload that makes a historical figure auditable when the source
later revises it.

**Regenerate the Python constant from fetched data at seed time.** Rejected. It bakes the
fetch date into source code, and a cost figure's validity is a function of *when it was
retrieved*, which a constant cannot carry.
