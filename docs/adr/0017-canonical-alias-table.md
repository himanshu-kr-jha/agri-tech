# ADR-0017 — One canonical alias table, applied at gather, failing loudly

Date: 2026-08-28 · Status: Proposed

## Context

Every external source names the same thing differently, and none of the differences are
derivable:

| Our name | Agmarknet | MSP (batch 1) | Cost & production (batches 2, 5) |
|---|---|---|---|
| Mustard | `Mustard` | `Rapeseed/Mustard` | `R & M` |
| Paddy | `Paddy(Common)` | `Paddy (Common)`, `Paddy (Grade A)` | `Rice` |
| Lentil | — | `Masur (Lentil)` | `Lentil` |

Geography is worse, because the failure is invisible. The district crop-production series
predates the 2018 rename: `district_name=PRAYAGRAJ` returns **zero rows**, `ALLAHABAD` returns
470. A join on the current, correct-looking name silently matches nothing and produces an
empty result that reads as "no data for this district" rather than as an error.

The repository already solved this once, and the reasoning in the code is right:

```python
# orchestrator/gather.py — Our crop names against Agmarknet's commodity names. Kept explicit
# because the mapping is not derivable — "Paddy" is "Paddy(Common)" there, and guessing
# would silently lose a crop.
AGMARKNET_COMMODITY = {...}   # 5 entries
```

But it was solved twice. `seed/generator.py` carries `AGMARKNET_NAME = {"Paddy":
"Paddy(Common)"}` — the same concept, a second home, and **one entry against five**. Two
mappings for one relationship, already disagreeing in completeness, at two sources. Six
sources have since been added.

## Decision

**One canonical alias table, keyed by `(source_key, foreign_name) → canonical`,** covering
crops, districts and any other cross-source identity. It lives beside the source registry, as
a reviewable Python constant in the style of the existing mappings, and the two current
duplicates are folded into it.

Three rules make it worth having:

**Applied at gather, never at ingest.** `ExternalRecord` retains the raw payload precisely so
evidence can be audited (ADR-0013, INV-2). Normalising names on the way in would rewrite the
thing we keep in order to be able to check ourselves. Raw stays raw; translation happens when
the orchestrator assembles `ModuleInput`.

**An unmapped name is an error, not a skip.** This is the whole point. Silently dropping an
unrecognised crop produces a shorter list that looks complete — the same failure class as the
un-paged request that returned a prefix of a dataset, and as `PRAYAGRAJ` matching nothing.
Gather raises; a human adds the alias.

**Aliases are directional and per-source.** `Paddy (Grade A)` and `Paddy (Common)` are
distinct MSP crops with distinct prices, not synonyms to be collapsed. The table maps into our
vocabulary; it never asserts that two foreign names mean each other.

## Consequences

Easier: adding a source means declaring its names once, next to the registry row that declares
the source. "Why did this crop vanish" stops being a debugging exercise.

Easier: the district rename is expressed as data (`ALLAHABAD → Prayagraj`) rather than as a
comment someone has to notice.

Harder: a new source cannot be gathered until its names are mapped. That is the intended
trade — the alternative is gathering it and quietly losing rows.

Accepted: the table is hand-maintained. It is small, it is reviewed in diffs, and it is the
kind of thing that should be argued with rather than inferred.

## Alternatives considered

**Per-source mapping constants beside each gather path.** This is today's pattern, and the
duplicate that already disagrees is the evidence against it. It works at two sources and does
not survive eight.

**Fuzzy or normalised string matching.** Rejected outright. It would map `Paddy (Grade A)` onto
`Paddy (Common)` — different prices — and attach `Other Kharif pulses` to a real crop. Both
fail silently and plausibly, which is the failure mode this decision exists to eliminate.

**Normalise on ingest and store canonical names.** Rejected: it mutates the raw payload that
INV-2 keeps for audit, and it makes a mapping bug unfixable retroactively, since the original
names would no longer be on disk.
