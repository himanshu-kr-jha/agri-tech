# data.gov.in — cached payloads

Fetched from the **api.data.gov.in** JSON API (the sanctioned programmatic route; the
data.gov.in *website* returns an Akamai block to non-browser clients, which we do not
attempt to work around).

Authored by the **Directorate of Economics & Statistics / CACP**, Ministry of Agriculture
& Farmers Welfare. `data.gov.in` is the *access route*, not the publisher — the source
registry records both separately.

`MANIFEST.json` carries the resource id, record count, field list, temporal coverage and a
**SHA-256** per file, so a later re-fetch can be proved identical to what was seeded.

## What is here

| File | Content | Coverage | Unit |
|---|---|---|---|
| `coc_a2fl.json` | Cost of production (A2+FL), state × crop | 2013-14 → 2017-18 | ₹/quintal |
| `coc_c2.json` | Cost of production (C2), state × crop | 2013-14 → 2017-18 | ₹/quintal |
| `msp_rabi.json` | MSP + cost, rabi crops | 2022-23 → 2025-26 | ₹/quintal |
| `msp_kharif.json` | MSP + cost, kharif crops | 2021-22 → 2024-25 | ₹/quintal |

## Two limitations that matter

**1. These are aggregates, not the itemised breakdown.** `intelligence/farm.py:CROP_ECONOMICS`
needs six per-hectare components (seed / nutrient / protection / labour / irrigation / other),
and `farm.py` states the split is load-bearing: *"a single 'cost of cultivation' number cannot
answer 'what if we are short of cash in October'."* These files therefore **do not retire
E1-E6** in `seed/sources.md` §12. They can *bound* it — a synthetic component set whose total,
divided by yield, lands far from the real A2+FL is provably wrong.

The itemised tables live in the DES *Cost of Cultivation of Principal Crops* reports on
`desagri.gov.in`, which was unreachable when this was fetched (`ECONNREFUSED 164.100.114.118`).
MoSPI 4.12 is the reachable alternative route and has not yet been tried.

**2. The cost-of-production files are stale.** Latest year is 2017-18. The MSP files are
current (2025-26 rabi) and are directly usable.

## Licence

**Not yet verified.** NDSAP / GODL-India is presumed but unconfirmed. Per the agreed rule,
no value from here may have its confidence cap lifted until a named human records the licence
and confirms the transcription.

## Credentials

The API key is read from `DATA_GOV_IN_API_KEY` and is **never committed**. Response payloads
were checked for key echo-back before being added here (`.params` is null in all four).
