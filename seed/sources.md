# Seed Data Sources — Citation Register

Every non-synthetic value used in `seed/` must have a row in this file **before** it is seeded.
This is the enforcement mechanism for `CLAUDE.md` §8 rule 4: *never fabricate agronomy*.

Anything without a row here is synthetic and must be flagged `synthetic = true` in the data and
rendered with the `DEMO DATA` marker in the UI (UI-04, C-2).

Demo anchor: **Prayagraj district, Uttar Pradesh** — see `docs/DEMO-CONTEXT.md`.

---

## How to use this file

1. Find the value you need in the checklist below.
2. Retrieve it from a primary source — a government portal, a state agriculture department
   publication, IMD, Agmarknet, ICAR, or a peer-reviewed paper. Not a blog, not an aggregator,
   not a model's recollection.
3. Fill the row: what, value, source URL, retrieved-on date, confidence.
4. Only then use it in the seed generator.

If a value cannot be sourced, choose one of two paths — never a third:

- **Mark it synthetic** and let the UI say so. This is honest and costs nothing.
- **Drop the feature** that needed it.

Do not approximate an unsourced number into the seed and let it render as fact. For scheme
eligibility this is not merely sloppy: telling a farmer they qualify for a benefit they do not
is a real harm.

---

## Status legend

`TODO` not yet retrieved · `OK` sourced and recorded · `SYNTHETIC` deliberately invented,
UI-labelled · `DROPPED` could not source, feature removed

---

## 1. Geography & agro-climatic zone

| # | What | Value | Source | Retrieved | Status |
|---|---|---|---|---|---|
| G1 | UP agro-climatic zone containing Prayagraj | **Central Plain Zone** (not Eastern Plain — earlier assumption was wrong) | Multiple secondary sources, consistent; UP Dept. of Agriculture map still to confirm | 2026-08-22 | PARTIAL — confirm against the official zone map before seeding yields |
| G2 | Trans-Yamuna zone split within the district | **Vindhyachal Zone** (Mirzapur, Sonbhadra, southern Allahabad/Prayagraj) | as G1 | 2026-08-22 | PARTIAL |
| G3 | Block list | **8 tehsils, 23 development blocks** — full list in `docs/DEMO-CONTEXT.md` §2 | https://prayagraj.nic.in/administrative-setup/ | 2026-08-22 | OK |
| G3b | Block→tract (Ganga-par / doab / Yamuna-par) mapping | Tehsil-level grouping proposed; block-level assignment unconfirmed | District map needed | | TODO |
| G4 | Block boundary geometries (for PostGIS plots) | | Survey of India / district GIS / OSM | | TODO |
| G5 | Predominant soil types per tract | | ICAR / NBSS&LUP soil survey | | TODO |

## 2. Climate

| # | What | Value | Source | Retrieved | Status |
|---|---|---|---|---|---|
| C1 | Annual rainfall normal, Prayagraj | | IMD | | TODO |
| C2 | Monthly rainfall distribution | | IMD / Open-Meteo historical | | TODO |
| C3 | Monthly temperature normals (min/max) | | IMD / Open-Meteo | | TODO |
| C4 | Humidity normals | | Open-Meteo | | TODO |
| C5 | Frost/cold-wave frequency, Dec–Jan | | IMD | | TODO |
| C6 | Unseasonal rain / hail frequency, Feb–Mar | | IMD | | TODO |
| C7 | 24 months of daily observed weather for the seed period | | Open-Meteo archive API | | TODO |

## 3. Land & farmers

| # | What | Value | Source | Retrieved | Status |
|---|---|---|---|---|---|
| L1 | District landholding size distribution | | Agriculture Census | | TODO |
| L2 | Net/gross sown area, Prayagraj | | District statistical handbook | | TODO |
| L3 | Irrigation coverage by source and by block | | Minor Irrigation Census / district handbook | | TODO |
| L4 | Tenancy/sharecropping prevalence in eastern UP | | NSSO land & livestock holding survey | | SYNTHETIC unless sourced |

## 4. Crops & agronomy

Coefficients feeding the Quality and Farm modules. **These drive every yield number in the
demo** — they are the highest-risk items in this register.

| # | What | Value | Source | Retrieved | Status |
|---|---|---|---|---|---|
| A1 | Base yield — paddy, **Central Plain Zone** (and Vindhyachal for the trans-Yamuna tract) | | UP Dept. of Agriculture / ICAR | | TODO |
| A2 | Base yield — wheat | | | | TODO |
| A3 | Base yield — potato | | | | TODO |
| A4 | Base yield — mustard | | | | TODO |
| A5 | Base yield — guava (per tree / per ha) | | ICAR-CISH Lucknow | | TODO |
| A6 | Crop calendar — sowing & harvest windows, all five crops | | UP Dept. of Agriculture, **Central Plain Zone** | | TODO |
| A7 | Crop duration by variety | | Variety release notifications | | TODO |
| A8 | Water requirement per crop | | ICAR / FAO CROPWAT | | TODO |
| A9 | Nutrient recommendation (NPK) per crop | | UP soil-health recommendations | | TODO |
| A10 | Input cost norms per ha per crop | | CACP cost-of-cultivation data | | TODO |
| A11 | Grade parameters — potato | | AGMARK grade standards | | TODO |
| A12 | Grade parameters — guava | | AGMARK / APEDA | | TODO |
| A13 | Common varieties grown in the district | | | | TODO |

## 5. Crop protection

Gated by INV-8. **A chemical option may not be seeded without a row here.**

| # | What | Value | Source | Retrieved | Status |
|---|---|---|---|---|---|
| P1 | Late blight — symptoms, favourable conditions, spread behaviour | | ICAR-CPRI | | TODO |
| P2 | Late blight — IPM/cultural/biological measures | | ICAR-CPRI | | TODO |
| P3 | Late blight — approved chemical classes for Indian potato | | CIB&RC registered label claims | | TODO |
| P4 | Early blight — differential diagnosis vs late blight | | ICAR-CPRI | | TODO |
| P5 | Paddy — major pests/diseases in eastern UP | | ICAR-IIRR | | TODO |
| P6 | Wheat — rust and other major diseases | | ICAR-IIWBR | | TODO |
| P7 | Guava — wilt and fruit fly management | | ICAR-CISH | | TODO |

**Rule:** every chemical entry stores the CIB&RC label reference. Where no label reference is
available, the module emits IPM steps only and states that a local agronomist must be consulted.
No exception. See `docs/ARCHITECTURE.md` §4.2.

## 6. Markets

| # | What | Value | Source | Retrieved | Status |
|---|---|---|---|---|---|
| M1 | Agmarknet market list for Prayagraj district | **5 markets, verified.** `298 Prayagraj APMC`, `1724 Ajuha APMC`, `1749 Sirsa APMC`, `1764 Jasra APMC` (all *Principal Market Yard*), `4389 Lediyari APMC` (*Other*). district_id 646, state_id 34. **Note: "Mundera Mandi" is not an Agmarknet market name** — the Agmarknet key for that site is *Prayagraj APMC*. | `GET https://api.agmarknet.gov.in/v1/market-district-state` | 2026-08-22 | OK |
| M2 | 24 months price series  | **Done.** Paddy(Common) id 2 — 974 rows / 470 days, modal mean ₹2,208/qtl, 328,980 MT. | `seed/fetch_agmarknet.py`, 2024-08-22..2026-08-22 | 2026-08-22 | OK |
| M3 | 24 months price series  | **Done.** Wheat id 1 — 1,878 rows / 613 days, modal mean ₹2,495/qtl, 212,500 MT. | `seed/fetch_agmarknet.py`, 2024-08-22..2026-08-22 | 2026-08-22 | OK |
| M4 | 24 months price series  | **Done.** Potato id 24 — 1,596 rows / 707 days, modal mean ₹1,219/qtl (range 400–2,930), 185,510 MT. Shows a 79% fall from Aug-2024 to Apr-2026. | `seed/fetch_agmarknet.py`, 2024-08-22..2026-08-22 | 2026-08-22 | OK |
| M5 | 24 months price series  | **Done.** Mustard id 12 — 163 rows / 139 days, modal mean ₹6,193/qtl. Thin market, seasonally correct. | `seed/fetch_agmarknet.py`, 2024-08-22..2026-08-22 | 2026-08-22 | OK |
| M6 | 24 months price series  | **Done.** Guava id 156 — 93 rows / 93 days, modal mean ₹2,320/qtl, 2,952 MT. Thin market. | `seed/fetch_agmarknet.py`, 2024-08-22..2026-08-22 | 2026-08-22 | OK |
| M7 | Arrivals series for the same | **Done.** Arrivals in Metric Tonnes arrive on the same rows as price. | as M2–M6 | 2026-08-22 | OK |
| M8 | MSP — paddy & wheat, current season | | CACP / FCI | | TODO |
| M9 | Cold-storage capacity, Prayagraj district | | UP Horticulture Dept. / NHB | | TODO |
| M10 | Cold-storage rental rates | | | | TODO |
| M11 | Road freight rate per tonne-km | | | | TODO |
| M12 | Diesel price series | | OMC published prices | | TODO |

**Do not invent mandi names.** A judge from UP will recognize a fabricated market immediately,
and it discredits every other number on the screen. The five names above are the real ones —
and note that the obvious guess, *Mundera Mandi*, is **not** among them.

## 7. Government schemes

Each scheme needs its eligibility text transcribed into machine-evaluable JSON
(`docs/ARCHITECTURE.md` §4.6), with the original text retained alongside.

| # | Scheme | Source | Retrieved | Rules transcribed | Status |
|---|---|---|---|---|---|
| S1 | PM-KISAN | pmkisan.gov.in | | ☐ | TODO |
| S2 | PMFBY | pmfby.gov.in | | ☐ | TODO |
| S3 | Kisan Credit Card | | | ☐ | TODO |
| S4 | Soil Health Card | | | ☐ | TODO |
| S5 | PM-KUSUM | | | ☐ | TODO |
| S6 | Agriculture Infrastructure Fund | | | ☐ | TODO |
| S7 | SFAC 10,000 FPO scheme | | | ☐ | TODO |
| S8 | NABARD FPO equity grant / credit guarantee | | | ☐ | TODO |
| S9 | UP state scheme 1 — **verify current status** | | | ☐ | TODO |
| S10 | UP state scheme 2 — **verify current status** | | | ☐ | TODO |
| S11 | UP horticulture mission support for guava | | | ☐ | TODO |
| S12 | Mukhyamantri Krishak Durghatna Kalyan Yojana | | | ☐ | TODO |

State schemes lapse and change more often than central ones. A scheme whose current status
cannot be confirmed is **dropped**, not carried forward on the assumption that it still runs.

## 8. GI / quality

| # | What | Value | Source | Retrieved | Status |
|---|---|---|---|---|---|
| Q1 | Guava GI registration | **Allahabad Surkha Guava**, GI application no. **50**, Class 31 (guava fruits). Applicant: Allahabadi Surkha Amrood Utpadak Welfare Association — Allahabad, Bankarabad, Bamroli Janpath. Advertised as accepted under s.13(1) of the GI Act 1999. | GI Journal No. 19, Oct 2007 / Jyaistha-11, Saka 1929 — https://www.upkrishivipran.in/GI/images/AllahabadSurkha/AllahabadSurkha.pdf | 2026-08-22 | OK |
| Q2 | Geographic area covered by the GI | "Villages of **Chail, Muratganj, Newada, Manjhanpur** blocks of Allahabad District", with area tables for **Kaurihar II (Chail area)** 25.5 ha / 4,190 qtl, **Phulpur** 3.5 ha / 445 qtl, a Kaushambi section 25.0 ha / 4,155 qtl, and **Muratganj** 19.0 ha / 3,158 qtl. **Note:** Chail/Muratganj/Newada/Manjhanpur are in **Kaushambi district today** (carved out of Allahabad in 1997); the Prayagraj blocks are **Kaurihar and Phulpur**. Total documented area ≈ **73 ha**. | as Q1 | 2026-08-22 | OK |
| Q3 | Quality specification in the GI application | Avg weight 200 g · size 7.20 cm · 280 seeds/fruit · yield 120 kg/tree in 6th year · TSS 13.75% · acidity 0.40 · pH 3.5 · total sugar 10.2% · vitamin C 150 mg/100 g. Fruit: large, slightly depressed both ends, thin skin, uniform pink, thick whitish-to-pink flesh, sweet. | as Q1 | 2026-08-22 | OK |
| Q4 | Any recent notification affecting GI produce labelling | Not found. **Do not invent one.** Build the policy event on the real cross-district compliance question (`DEMO-CONTEXT.md` §4.2) instead. | | 2026-08-22 | DROPPED as a "recent notification"; reframed |

This underwrites the demo's policy-event beat. If Q1–Q3 cannot be sourced, the GI event becomes
synthetic and must be relabelled — it should not be presented as a real regulatory change.

## 9. Synthetic by design

Deliberately invented, always `DEMO DATA` labelled. Listed here so the boundary between sourced
and invented is explicit rather than implied.

| # | What | Why synthetic |
|---|---|---|
| X1 | The organization "Prayagraj Kisan Producer Company Limited" | No real FPO's data is being used (C-2) |
| X2 | All 1,000 farmer identities, names, contacts | Privacy — no real people |
| X3 | Plot boundaries and locations | Derived from block geometry with jitter; no real plots |
| X4 | The 8 buyers and their terms | Shaped to make the effective-price reversal demonstrable |
| X5 | Two seasons of outcome history | Needed for the learning-loop beat |
| X6 | Tenure share conflicts (12 plots) | Needed for the discrepancy beat |
| X7 | Organization resources — capital, warehouse, cold-store allocation | No real FPO balance sheet |
| X8 | The 20 news/policy events | Shaped from real event *types*; the specific instances are constructed |

X8 carries the most risk of over-claiming. Each event's *mechanism* should be real; only the
instance is constructed — and the UI must not present a constructed event as a real headline.


---

## 10. Verification pass — 2026-08-22

A first pass against primary sources. Results and what they changed:

| Item | Outcome |
|---|---|
| **Guava GI** | **Fully verified** from the GI Journal itself. Yielded the registered quality spec as usable numbers, and corrected the production area — the belt is in **Kaurihar and Phulpur (Ganga-par)**, not the doab. |
| **Blocks** | **Verified** against the district administration: 8 tehsils, 23 blocks. The earlier block list in `DEMO-CONTEXT.md` was partly invented and has been replaced. |
| **Agro-climatic zone** | **Corrected.** Prayagraj is **Central Plain**, not Eastern Plain. Yield coefficients must be drawn for Central Plain + Vindhyachal. |
| **Mandi names** | **Still blocked.** Neither the data.gov.in API nor the Agmarknet portal was reachable from this environment. |

### The mandi blocker is cleared

**Resolved 2026-08-22.** Agmarknet has been rebuilt as *Agmarknet 2.0*, a React SPA — which is
why the old `SearchCmmMkt.aspx` GET no longer renders and why `data.gov.in`'s legacy resource
proxy returns 500. The SPA is backed by a JSON API at **`https://api.agmarknet.gov.in/v1`**
that needs **no authentication**. Endpoints in use:

| Endpoint | Method | Gives |
|---|---|---|
| `/market-district-state` | GET | Full market → district → state master (~4,600 markets) |
| `/dashboard-market-filter` | GET | Market category, address, API-integration flag |
| `/location/state?page_size=100` | GET | States with nested districts and codes |
| `/daily-price-arrival/filters` | GET | Commodity, variety, grade and group ids |
| `/prices-and-arrivals/market-report/daily` | POST | Daily arrivals + min/max/modal price |

Daily-report payload: `{"date": "YYYY-MM-DD", "marketIds": [...], "stateIds": [...],
"includeExcel": false}`. Response nests `states → markets → commodities → data`.

`seed/fetch_agmarknet.py` wraps all of this, caches one JSON file per date and flattens to CSV.

> **Caveat — this is not a documented public API.** It was found by reading the published
> front-end bundle. It may change or start rate-limiting without notice. So: **keep the fetched
> payloads**. `seed/generated/agmarknet/daily/*.json` is the durable artifact, and the offline
> demo requirement (NFR-303) depends on it, not on the API being up on the day.

### Backfill complete

**2026-08-22.** 731 days requested, 721 with data, **23,460 rows**. All five demo crops have a
real series; mustard (139 days) and guava (93 days) trade thinly, which is seasonally correct.

Coverage note: all five Prayagraj markets report `api_allowed_market: false` — they do not push
through the state API integration — yet the series is dense for the main commodities at Prayagraj
APMC. The thin ones are thin because the commodity trades rarely, not because the feed is broken.

The payloads under `seed/generated/agmarknet/daily/` are the durable artifact and must be
committed as the offline fixture bundle before the demo (NFR-303).

---

## 11. Hazard climatology — added 2026-08-23

The Risk module needs to answer *how likely is unseasonal rain during the potato harvest
window?* Nothing in this register gives a half-month hazard frequency for Prayagraj, and
CLAUDE.md rule 5 forbids inventing one. So it is **derived from a real record** instead of
asserted.

| id | Value | Source | Status |
|---|---|---|---|
| **C8** | Half-month hazard frequencies (heavy rain, very heavy rain, frost, heat stress) at three tract points, 1995–2024 | ERA5 reanalysis via Open-Meteo archive API, `seed/fetch_climatology.py` | ✅ derived from a cited source |
| **C9** | Hazard thresholds: heavy rain ≥15 mm/day, very heavy ≥40 mm/day, frost min ≤4 °C, heat stress max ≥40 °C | Judgement, stated in `seed/fetch_climatology.py` | ⚠️ documented judgement, not a standard |

"Unseasonal rain probability 0.167" here means something checkable: *in 30 years of record,
17% of them saw a heavy-rain day somewhere in that half-month at that point*. It is a
frequency, not a forecast, and every finding built on it says so.

### What the record actually showed, including where it contradicted us

**The architecture sketch used an illustrative 0.71 for the February potato window. The real
figure is 0.167.** Building on the invented number would have made a better story and a false
one. The correction is recorded in `docs/ARCHITECTURE.md` §5.2 rather than quietly patched,
because "a fabricated 0.7 is indistinguishable from a measured 0.7 once it is on a screen" is
the whole reason this register exists.

Three further things the 30-year record settled:

| Finding | Consequence |
|---|---|
| **Frost is p = 0.00 in every window.** ERA5 tmin never reaches ≤4 °C at these grid points. | The weather module's cold-wave detection is chasing a hazard this dataset does not show. Kept — a coarse reanalysis grid smooths extremes and a real gauge may differ — but it must not be presented as a demonstrated risk. |
| **Heat stress in late April is p = 0.967, and p = 1.00 over a multi-week window.** | That is not a hazard, it is the climate. A probability of 1.0 carries no decision information, and ranked naively it beat a 1,868-tonne price exposure to the top of the packet. `HAZARD_IS_CLIMATE_ABOVE = 0.90` now demotes these to standing conditions. |
| **The real Kharif hazard is October rain on standing paddy** — p = 0.367 heavy, 0.167 very heavy in the first half of October. | This, not February, is where the district's harvest exposure actually sits. |

## 12. Cost of cultivation & farm economics — OPEN

Everything in this section is **SYNTHETIC — DEMO ONLY** and is labelled as such in the data,
in `ModuleOutput.degraded_inputs`, and on every screen that renders a figure derived from it.
The Farm module's confidence is capped at 0.62 because of it.

| id | Value | Where | Status |
|---|---|---|---|
| **E1–E6** | Per-hectare seed / nutrient / protection / labour / irrigation / other cost, five crops | `intelligence/farm.py:CROP_ECONOMICS` | ❌ TODO — needs a cited cost-of-cultivation survey |
| **A14** | Damage ratio if a weather hazard lands (15% of exposed value) | `intelligence/risk.py` | ❌ TODO |
| **A15** | Manure nitrogen and fodder demand per head per year | `orchestrator/gather.py:LIVESTOCK_COEFFICIENTS` | ❌ TODO |
| **A16** | Yield lost per missing irrigation (12%) | `intelligence/farm.py` | ❌ TODO |
| **G4** | Irrigations a tract's water supports per season | `orchestrator/gather.py:IRRIGATIONS_AVAILABLE` | ⚠️ scaled from the irrigation-coverage figures in DEMO-CONTEXT §2, not a water budget |

A correction worth recording: an earlier version of **G4** excluded paddy from Ganga-par,
which is simply false — irrigated paddy is what that tract grows. A constraint tuned until it
produced an interesting result produced an interesting *wrong* result. The current numbers
exclude paddy only from Yamuna-par, where 31% irrigation coverage makes that true.

A second one: guava's per-hectare cost was copied from the annual crops, which gave an
orchard a return of **eleven rupees per rupee** — a number that should stop a reviewer rather
than excite them. Picking and packing 30 t of fruit by hand is the dominant cost of an
orchard, and establishment capital has to be amortised or a perennial looks free to plant.
Perennials are now reported separately and never ranked against annual crops, because an
orchard's return on *annual operating cost* is high precisely because the capital was spent
three years ago.

## 13. Crop protection knowledge base — OPEN, and gating

| id | Value | Where | Status |
|---|---|---|---|
| **P1–P7** | Symptom→condition associations, favourable conditions, spread rates for six conditions across five crops | `intelligence/crop_health.py:CONDITIONS` | ❌ TODO — unverified against any authority |

Until these are cited, every diagnosis this module emits carries the `SYNTHETIC — DEMO ONLY`
marker and is **capped at 0.42 confidence** — deliberately below the orchestrator's 0.45
floor, so an unsourced diagnosis is structurally incapable of driving a recommendation on its
own. Filling in a citation lifts the cap for that entry alone.

Regardless of citation status, INV-8 holds absolutely: crop-protection output is a chemical
*class* plus "read the label and consult a local agronomist", never a product and a dose.
That is not a limitation waiting to be lifted — it is the safety floor.

## 14. Government schemes — real, rules simplified

| id | Value | Source | Status |
|---|---|---|---|
| **S1** | PM-KISAN — ₹6,000/year income support | https://pmkisan.gov.in/ | ✅ scheme and benefit real; exclusion rules simplified |
| **S2** | PMFBY — crop insurance, farmer premium capped at 2% Kharif / 1.5% Rabi / 5% commercial | https://pmfby.gov.in/ | ✅ scheme and premium caps real; **cut-off dates are notified per state and season and are NOT encoded** |
| **S3** | Kisan Credit Card | https://www.myscheme.gov.in/schemes/kcc | ✅ real; limits and rates set by the lending bank |
| **S4** | Soil Health Card | https://soilhealth.dac.gov.in/ | ✅ real; benefit is indirect and not estimated |
| **S5** | Formation & Promotion of 10,000 FPOs | https://sfacindia.com/FPOS.aspx | ⚠️ real; membership norms differ plains vs hill/NE and the grant structure has been revised — threshold is indicative |
| **S6** | Agriculture Infrastructure Fund | https://agriinfra.dac.gov.in/ | ✅ real; subvention rate and ceiling are in the operational guidelines |
| **S7** | Sub-Mission on Agricultural Mechanization | https://agrimachinery.nic.in/ | ✅ real; subsidy rates vary by machine, category and state |
| **S8** | PMKSY — Per Drop More Crop | https://pmksy.gov.in/ | ✅ real; rates set by state, holding-class differential is real |

Every assessment carries `rules_verified=False` and is capped at 0.55 confidence. **No
application is ever auto-submitted** (FR-567 / SAF-11) — the module prepares the paperwork and
names the portal; a human files it.

One exemption is deliberate: the *gap* findings ("one unrecorded fact blocks 812 assessments")
sit **above** the cap. That is a count of our own data and is true whatever the scheme rules
turn out to say, so capping it at the rules' confidence would understate something we know.

---

## 15. The retrieved knowledge base — real text, mostly uncleared

Added 2026-08-29 (ADR-0018). These are not seeded *values*; they are published text the
system retrieves and cites. They earn a row here for the same reason everything else does —
nothing enters the system without a citation and a status.

| id | Source | What it carries | Licence | Status |
|---|---|---|---|---|
| **K1** | `shasanadesh.up.gov.in` — UP Dept. of Agriculture शासनादेश | 75 government-order listing rows to 24/08/2026: number, date, section, category, subject | Non-commercial research and private study, with attribution. **COMMERCIAL USE NOT CLEARED** | ✅ real, cited, retrievable. Drives the POLICY findings |
| **K2** | `agridarshan.up.gov.in/api/cms/getAll` | 125 CMS records; 24 bilingual FAQs carry real agronomic guidance, the rest are largely circulars and notices | `UNKNOWN` | ⚠️ retrievable as **context only** — capped at 0.40, below the orchestrator's floor |

Three constraints a reader should not have to discover by experiment:

- **The listing is not the order.** K1 gives a subject line, never the document. Eligibility
  criteria, amounts and deadlines live in PDFs there is no fetch path for. Any structured
  field extracted from a subject is a *proposal* under ADR-0014, stored `UNVERIFIED`.
- **Hindi is canonical, stored byte-for-byte** (ADR-0015), zero-width joiners included. The
  matching layer normalises a copy; nothing rewrites the stored text.
- **An unconfirmed licence is a hard cap, not a warning.** K2 cannot reach a recommendation
  at all. Confirming these licences is still the cheapest unblock in the repository, and
  ADR-0014 requires a named human to do it.

Not in the register, deliberately: **no news source exists.** `NewsDomain` and the 20 events
in X8 remain synthetic. K1 fills the policy half of FR-404; market, global and input-price
news from a press source is unsourced and stays that way.
