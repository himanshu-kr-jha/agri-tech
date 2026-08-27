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

## Batch 3 — UP schemes (Hindi), ingested

| Source | Detail |
|---|---|
| `shasanadesh.up.gov.in/ShowGOforDept.aspx?dept=37` | UP government orders (शासनादेश), Agriculture dept. Hindi, official, public, **no personal data**. ASP.NET GridView, 25 rows/page, paginated by `__doPostBack` with VIEWSTATE. Newest order 24/08/2026. |

Stored verbatim as published — Hindi is canonical, nothing translated on ingest (ADR-0015).
Category facet is the useful filter; `नीतियोँ/योजनाओं संबंधी दिशा-निर्देश` ("guidelines
relating to policies/schemes") is the one that carries scheme text, alongside `अधिसूचना`
(notification) and `वित्‍तीय स्‍वीकृतियॉं` (financial sanctions).

**Licence — the first source that is not `UNKNOWN`.** shasanadesh's own Copyright Policy
permits reproduction for *non-commercial research and private study, with attribution*;
anything else requires department permission. Recorded on the source as
**COMMERCIAL USE NOT CLEARED**, which matters because AgriVardhak is intended as a product.

## Batch 4 — crop varieties, ingested

| Source | Resource id | Coverage | Priority | Licence |
|---|---|---|---|---|
| Field crop varieties and hybrids released and notified | `53cd4900…` | 2008–2012, 255 rows | P2 | UNKNOWN |

Real variety names by crop and year (Wheat 2008 = "Pusa Wheat-111 (HD-2932)"). Two companions
were checked and rejected: `9cac7b14` holds only counts per crop group, and `46f587a9` is 13
rows of mostly `NA` with no guava.

## Batch 5 — crop production, area and yield, ingested

| Source | Resource id | Coverage | Priority | Licence |
|---|---|---|---|---|
| District-wise, season-wise crop production statistics | `35be999b…` | 1997–2014; **33,306 UP rows** of 246,091 national | P0 | UNKNOWN |

The most valuable single source found. District × season × crop × year with **area and
production**, so yield is derivable — which bears directly on `seed/sources.md` **A1–A4**
(base yield: paddy / wheat / potato / mustard, all `TODO`).

Allahabad has 470 rows across 38 crops. District mean yields 2007–14: wheat ~2.3, paddy ~2.4,
potato ~16.3 t/ha, against repo synthetics of 4.0–4.3, 4.2–4.5 and 23–25 respectively. Variety
*potential* legitimately exceeds a district *average*, so this does not make the synthetics
wrong — but it bounds them, which was previously impossible. **2014 is an outlier low year and
must not be read alone.**

**Entity-resolution trap:** `district_name=PRAYAGRAJ` returns **0 rows**; `ALLAHABAD` returns
470. The series predates the 2018 rename, so a join on the current name silently matches
nothing.

## Batch 6 — procurement, ingested

Domain 3 of the original brief, previously unaddressed entirely.

| Source | Resource id | Coverage | Priority | Licence |
|---|---|---|---|---|
| Procurement of wheat & paddy, MSP value, **farmers benefited** | `f8340bd2…` | 2018-19 → 2022-23 | P0 | UNKNOWN |
| State/UT-wise paddy procurement and value at MSP | `e10ca3fd…` | Apr–Jun 2021, 23 states | P0 | UNKNOWN |

## Reachable, not yet ingested

| Source | Status | Notes |
|---|---|---|
| `agriculture.up.gov.in` | 200, no `robots.txt` | Plain IIS/HTML. Route to UP state schemes S9–S12. |
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
| **`agridarshan.up.gov.in/api/` — beneficiary endpoints** | **Found by reading its Angular bundle, and deliberately not used.** Endpoints include `beneficiaryMgt/getBenfById`, `beneficiaryMgt/getRegistration`, `farmerRegister/getVerifier`, `grantWiseBill/getFarmerList`, `onlinebooking/getAllApplicants` — an internal DBT beneficiary administration system holding **personal farmer records**. Technically reachable; out of bounds under INV-9, the DPDP Act, and this project's own rule against collecting personal farmer data. |
| `agriculture.up.gov.in/dbt/Labharti_Shuchi.aspx` | "Beneficiary list" — personal data, same reasoning |
| `agridarshan` reference endpoints — `onlinebooking/getDistrict`, `getBlock`, `administrative/getByCode`, `agency/getAll` | Probed: **all return 403**. Authentication-gated, therefore not public data, and a 403 is an access control we do not work around. Only `cms/getAll` is public, and it *is* used — see batch 3. |
