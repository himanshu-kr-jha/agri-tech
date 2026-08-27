# Data Sourcing — agreed design

Date: 2026-08-28 · Status: agreed in design session, **not yet implemented**

The goal is narrow and specific: **retire the `SYNTHETIC` labels in `seed/`** by replacing
invented coefficients with cited ones. It is not an India-wide ingestion fabric. Every
unsourced number in this repository already carries a confidence cap, so "replace synthetic
with real" has an exact operational meaning — **lift the caps** in `seed/sources.md`.

| Debt | Where | Cap today |
|---|---|---|
| P1–P7 crop-protection conditions | `intelligence/crop_health.py` | 0.42 — below the 0.45 orchestrator floor |
| E1–E6 cost of cultivation | `intelligence/farm.py:CROP_ECONOMICS` | 0.62 on the Farm module |
| Scheme eligibility rules | scheme module | 0.55, `rules_verified=False` |

## Settled decisions

**Scope**

1. First target is **cost of cultivation (E1–E6)** — since revised, see §Batch plan.
2. Real corpus is **UP-wide**; the sample FPO stays **Prayagraj** and stays synthetic.
3. Crops ranked by **area under cultivation, descending, no floor** — availability sets the limit.
4. A value that cannot be sourced is **synthetic or dropped**. No middle tier.

**Architecture**

5. Minimal registry: extend the source record with licence, retrieval and recheck fields.
   **No scheduler.** Staleness signalling and a fetch log only.
6. Scrapers by domain — `cost_of_cultivation`, `scheme`, `variety`, `price`, and since the
   re-verification also `production` and `procurement` — each with an
   **opaque JSON cursor** in a `scraper_checkpoint` table. Opaque because the cursor shape
   genuinely differs per type.
7. Fetch stack is **plain Python**: `httpx` + `pdfplumber` + `pandas`. No scraping vendor.
   Access order: official API → official download → structured → CSV/Excel → HTML → PDF.
8. `CropSpec` splits into a UP-wide **`CropReference`** and a separate Prayagraj placement
   map. Tract names are district-specific and must not sit on a state-wide entity.
9. Cost data lands as **`ExternalRecord`** under a new `COST_OF_CULTIVATION` kind, gathered
   by the orchestrator into `ModuleInput.data` — **ADR-0013**.

**Quality and safety**

10. Only fully-sourced crops enter the Farm ranking; authoritative vs advisory tiers — **ADR-0012**.
11. A cap lifts only with a **named verifier** and a licence on record — **ADR-0014**.
12. Hindi source text is **canonical**; translation is derived and versioned — **ADR-0015**.
13. Licence recorded per source, default `UNKNOWN`, and `UNKNOWN` blocks a cap lift.
14. Publisher and access route are recorded **separately**.
15. Retain each source document's URL, **SHA-256** and `retrieved_at`; commit the extracted
    JSON always, the source file only under a size threshold.

**Cadence** (defaults, overridable per source)

| Category | Recheck | Note |
|---|---|---|
| MSP | quarterly | event-driven; the CACP announcement is the event |
| Cost of cultivation | annual | published annually, lags by years |
| Schemes | quarterly | state schemes lapse — `sources.md` §7 drops unconfirmed ones |
| Varieties | annual | |
| Prices | daily | existing agmarknet cadence |

## Legal boundaries

Respect `robots.txt`, terms, licences and rate limits. **Do not bypass** CAPTCHA,
authentication, paywalls or anti-bot protection. `data.gov.in`'s website returns an Akamai
block to non-browser clients; the sanctioned `api.data.gov.in` route is used instead, and the
block is not worked around. Absence of a `robots.txt` is not permission — polite rate limits
still apply. No personal farmer data is collected.

## Batch plan

**Batch 1 — MSP.** Revised from cost of cultivation, because the cost data proved to be
aggregate-only and stale at 2017-18 while MSP came back current to 2025-26. The demo is a
price story, and the system currently cannot express *MSP announced* vs *procurement price*
vs *market price* vs *effective realization* at all. Data is already cached in
`seed/generated/batch1_msp/`.

**Batch 2 — cost of cultivation (E1–E6).** Blocked on the itemised tables. `desagri.gov.in`
was unreachable (`ECONNREFUSED 164.100.114.118`); MoSPI 4.12 is the untried alternative route.
The aggregates already cached cannot retire E1–E6 but can **bound** it: a synthetic component
set whose total, divided by yield, lands far from the real A2+FL is provably wrong.

**Batch 3 — UP state schemes (Hindi). Done.** `shasanadesh.up.gov.in` government orders for
the Agriculture department, scraped incrementally by `seed/fetch_up_schemes.py`. Hindi stored
verbatim (ADR-0015). **`agridarshan.up.gov.in` was investigated and rejected**: its API is a
DBT beneficiary administration system holding personal farmer records, so Q22's option (iii)
applies — skip it. This is the first source with a real licence rather than `UNKNOWN`, and
that licence does **not** cover commercial use.

**Batch 5 — crop production, area and yield. Done.** The district series, scoped to UP by a
server-side filter. Directly addresses A1–A4.

**Batch 6 — procurement. Done.** Closes Domain 3 of the original brief.

**Batch 4 — crop varieties. Done.** Field crop varieties and hybrids, 255 rows, via the
existing data.gov.in fetcher. Advisory-tier university cost studies remain outstanding.

## Open

- Licence for all four cached data.gov.in sources is `UNKNOWN`. Nothing lifts a cap until resolved.
- Itemised cost route unproven.
- Crop-protection P1–P7 deliberately left at 0.42. That cap is doing useful work.
