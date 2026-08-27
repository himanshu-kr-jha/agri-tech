# Sources Found — India agricultural data discovery

Date: 2026-08-28 · Scope: Uttar Pradesh, anchored on Prayagraj

Machine-readable registry: `seed/source_registry.py`. Fetcher: `seed/fetch_datagovin.py`.
Design decisions: `docs/DATA-SOURCING.md`. Citation register: `seed/sources.md`.

## Verified and cached

All four authored by **DES / CACP, Ministry of Agriculture & Farmers Welfare**, fetched via
the `api.data.gov.in` route. Payloads in `seed/generated/batch1_msp/` and
`seed/generated/batch2_cost_of_cultivation/`, hashes in each `MANIFEST.json`.

| Source | Resource id | Coverage | Unit | Priority | Licence |
|---|---|---|---|---|---|
| Cost of production (A2+FL), state × crop | `a24e6a66…` | 2013-14 → 2017-18, 209 rec | ₹/qtl | P0 | UNKNOWN |
| Cost of production (C2), state × crop | `dc3ba615…` | 2013-14 → 2017-18, 209 rec | ₹/qtl | P0 | UNKNOWN |
| MSP + cost, rabi | `6f655085…` | 2022-23 → **2025-26**, 6 rec | ₹/qtl | P0 | UNKNOWN |
| MSP + cost, kharif | `aa823ea9…` | 2021-22 → **2024-25**, 17 rec | ₹/qtl | P0 | UNKNOWN |

**UP has authoritative cost data for exactly 15 crops** — corroborated independently by
RLBCAU's scheme description (15 principal crops, 900 farmers, 150 villages, 45 districts,
block period 2023-26) and by the DES dataset itself:

> Arhar · Bajra · Barley · Gram · Groundnut · Lentil · Maize · Moong · Paddy · Potato ·
> R & M · Sesamum · Sugarcane · Urad · Wheat

Against the five demo crops: Paddy, Wheat, Potato and Mustard (as "R & M") are covered.
**Guava is not** — horticulture sits outside the CACP scheme. ADR-0012 handles this; guava is
perennial and was already reported separately from the annual ranking.

## Reachable, not yet ingested

| Source | Status | Notes |
|---|---|---|
| `agriculture.up.gov.in` | 200, no `robots.txt` | Plain IIS/HTML. Route to UP state schemes S9–S12. |
| `agridarshan.up.gov.in` | 200, Hindi (`कृषि विभाग, उ०प्र०`) | Angular SPA — plain HTTP returns an empty shell. Find its JSON API; do **not** add browser automation. |
| `mospi.gov.in` | 200 | Publishes 4.12 *Cost of Cultivation of Principal Crops* — the untried route to the itemised tables. |
| `agmarknet.gov.in` | 200 | Already ingested. |
| `pmkisan.gov.in` | 200 | Central scheme, already cited in `sources.md` §14. |

## Unreachable or blocked

| Source | Status | Impact |
|---|---|---|
| `desagri.gov.in` | `ECONNREFUSED 164.100.114.118` / timeout | **Blocks batch 2.** Hosts the itemised cost-of-cultivation tables E1–E6 needs. |
| `data.gov.in` (website) | Akamai *Access Denied* | None — `api.data.gov.in` is the sanctioned route and works. **Not worked around.** |
| `upagriculture.com` | unreachable | UP state portal, retry later |
| `upagripardarshi.gov.in` | unreachable | |
| `diupmsme.upsdc.gov.in` | unreachable | |

## Searched and found absent

`data.gov.in` was searched four ways — `human labour`, `operational cost`, `input cost crop`,
`fertiliser consumption cost`. The catalogue (285,974 datasets) carries **aggregate** cost of
production, MSP and return-over-cost, but **no itemised cost-component dataset**. This is the
finding that reordered the batch plan: `farm.py` needs six per-hectare components and states
the split is load-bearing — *"a single 'cost of cultivation' number cannot answer 'what if we
are short of cash in October'."*

## Not to be used

| Source | Why |
|---|---|
| Any anti-bot-protected endpoint reached by evasion | Prohibited outright — including data.gov.in's website, which has a sanctioned API instead |
| Agricultural blogs / aggregators where a government source exists | P4/P5 must never override P0 |
| Any source carrying personal farmer data | No lawful basis; aggregated/anonymised only |
