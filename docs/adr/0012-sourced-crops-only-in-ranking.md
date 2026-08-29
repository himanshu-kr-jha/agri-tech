# ADR-0012 — Only fully-sourced crops enter the Farm ranking

Date: 2026-08-28 · Status: Proposed

## Context

The Farm module ranks crop options by gross margin. Today it ranks five crops whose cost
coefficients are entirely synthetic (`seed/sources.md` §12, E1–E6), so every option in the
comparison is invented and the comparison is at least internally consistent.

Sourcing real cost data breaks that symmetry. Uttar Pradesh has authoritative cost of
production for **exactly 15 crops** under the CACP Comprehensive Scheme — confirmed twice,
from RLBCAU's scheme description and empirically from the DES state × crop dataset. The
other ~20 prominent UP crops have none, and horticulture sits outside the scheme entirely.

Gross margin is a *difference of two numbers*. An invented cost placed next to a surveyed
one does not merely add noise — it can win the ranking on the strength of the invention,
and the winner is then an artifact of provenance rather than agronomy. The failure is
invisible in the output.

There is precedent in the module already: `farm.py` refuses to rank perennials against
annuals, because an orchard's return on annual operating cost is high precisely because the
establishment capital was spent three years earlier. The cost bases are not comparable, so
they are not compared.

## Decision

A crop enters the ranked comparison **only when every cost component carries a `source_ref`.**
Crops without sourced costs are reported in a separate *insufficient cost data* list —
visible, named, and explicitly not ranked.

Among sourced crops there are two tiers:

| Tier | Source | May enter the ranking |
|---|---|---|
| Authoritative | CACP / DES state cost survey | **Yes** |
| Advisory | ICAR / agricultural-university published cost study | **No** — orchestrator may raise it as a suggestion |

The advisory tier exists because a 900-farmer state survey and a single-district journal
study are both *sourced*, but letting sampling method decide a margin ranking is the same
failure one tier up.

## Consequences

Easier: every ranked comparison is between like and like, and "why is this crop not in the
list" has a precise answer rather than a shrug.

Harder: coverage shrinks. UP ranks at most 15 crops, fewer once filtered to a district.

Accepted: guava stays unranked, since horticulture is outside the CACP scheme. This costs
the demo nothing — guava is perennial and was already reported separately.

One code consequence worth stating: `source_ref != None` is **no longer sufficient** to
decide ranking eligibility. The check needs the source's identity, not merely its presence.

## Alternatives considered

**Rank everything, attach a confidence caveat.** Rejected. A caveat annotates a wrong
winner; it does not prevent one. The number still leads the screen.

**Exclude unsourced crops from output entirely.** Rejected. A crop the FPO actually grows
disappearing from the analysis is worse than one shown as un-analysable.

**Scale synthetic components to match the real aggregate.** Rejected. It manufactures false
precision: the total would be right and all six components still invented, while looking
sourced.
