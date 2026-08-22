# Demo Context — Prayagraj, Uttar Pradesh

Version 1.2 · 2026-08-22 · Resolves open question **O-1**

> **v1.1** applies a first verification pass against primary sources. It corrected the
> agro-climatic zone, replaced a partly invented block list with the district
> administration's own, and moved the guava belt from the doab to Ganga-par. See
> `seed/sources.md` §10 for what was checked and what is still open.
>
> **v1.2** unblocks the mandi list: five real Agmarknet markets for Prayagraj, plus a
> working fetch path for price and arrival series (§6.1).

The demo organization is anchored to **Prayagraj district, Uttar Pradesh**. This document
specifies the district profile that the seed generator, the agronomic coefficients, the mandi
data, the scheme set and the demo narrative all derive from.

**Confidence markers used throughout:**

| Marker | Meaning |
|---|---|
| ✅ | Established fact, but still requires a citation in `seed/sources.md` before it enters the seed |
| ⚠️ | Believed correct, **must be verified** before it enters the seed or the pitch |
| 🔧 | Synthetic — invented for the demo, must carry the `DEMO DATA` marker in the UI (C-2, UI-04) |

Nothing in this file goes into `seed/` until its marker is ✅ *and* it has a source row.

---

## 1. Why this district is a good choice

Three properties make Prayagraj a better demo anchor than a generic "Indian district":

1. **Genuine internal heterogeneity.** The district is split by the Ganga and the Yamuna into
   three agriculturally distinct tracts (§2). One FPO can therefore contain irrigated
   paddy–wheat farmers *and* rain-fed Vindhyan farmers — so the Risk module has something real
   to differentiate, and the drill-down shows a meaningful pattern rather than noise.
2. **A GI-tagged crop, verified.** *Allahabad Surkha Guava* holds GI application no. 50 ✅,
   and two of its named production blocks — Kaurihar and Phulpur — are in Prayagraj. The
   discovery session named *"sudden turbulence like GI tags"* as a specific FPO pain; this
   district lets us demo it with a real registration and a real compliance question (§4.2).
3. **Smallholder-dominant.** Eastern UP is overwhelmingly small and marginal farmers ✅, which
   is exactly the underserved population the challenge brief targets.

---

## 2. Geography — the three tracts

Prayagraj sits at the Ganga–Yamuna confluence. The rivers divide it into three tracts with
materially different agriculture ✅:

The district administration lists **8 tehsils and 23 development blocks** ✅ — verified against
`prayagraj.nic.in`, retrieved 2026-08-22:

| Tehsil | Development blocks |
|---|---|
| Sadar | *(none listed separately)* |
| Soraon | Kaurihar, Holagarh, Mauaima, Soraon, Shringverpur Dham, Bhagwatpur |
| Phulpur | Bahariya, Phulpur, Bahadurpur, Sahson |
| Handia | Pratappur, Saidabad, Dhanupur, Handia |
| Karchhana | Chaka, Karchhana, Kaundhiyara |
| Bara | Jasra, Shankargarh |
| Meja | Uruwa, Meja, Manda |
| Koraon | Koraon |

Grouped into the three tracts:

| Tract | Tehsils | Character | Irrigation | Implication for the demo |
|---|---|---|---|---|
| **Ganga-par** (north / trans-Ganga) | Soraon, Phulpur, Handia | Alluvial plain, deep fertile soil | Canal + tubewell, reliable | Paddy–wheat belt. Low weather exposure. **Contains the district's GI guava blocks** (§4.2). |
| **Doab** (central, between the rivers) | Sadar, Karchhana | Good alluvium, peri-urban market access | Tubewell, generally good | Vegetables and potato. Best market access. |
| **Yamuna-par** (south / trans-Yamuna, Vindhyan) | Bara, Meja, Koraon | Rocky, red/lateritic, undulating, shallow soils | Largely rain-fed | Gram, arhar, bajra, mustard. **High rainfall exposure.** |

⚠️ The **tehsil→tract grouping above is still a judgement call.** The block names are now
authoritative, but which side of which river each block sits on must be confirmed against the
district map before the seed places farmers geographically — Sadar and Karchhana in particular
straddle the doab and the Yamuna's south bank.

**This is the demo's backbone.** When the Risk module says *"312 farmers / 740 acres exposed"*,
those farmers should cluster in Yamuna-par — and the drill-down should make that visible on the
map. A uniform farmer population would make the drill-down look like a list; this makes it look
like an insight.

### Agro-climatic classification — **corrected**

Uttar Pradesh is divided into **9 agro-climatic zones**. Prayagraj falls in the
**Central Plain Zone** (with Kanpur, Lucknow, Unnao, Raebareilly, Fatehpur, Kaushambi and
others), and its southern trans-Yamuna portion falls in the **Vindhyachal Zone** (with Mirzapur
and Sonbhadra) ⚠️.

> **This corrects an earlier assumption in this document**, which placed Prayagraj in the
> *Eastern Plain Zone*. It does not. Base yield coefficients must be drawn for **Central Plain**
> and **Vindhyachal**, not Eastern Plain — the two carry different numbers, and a whole demo
> built on the wrong zone's yields would be quietly wrong in every production figure.

The zone assignment is corroborated across several secondary sources but has **not** yet been
confirmed against the UP Department of Agriculture's own zone map. Confirm before the yield
coefficients are seeded (`seed/sources.md` G1).

---

## 3. Climate ⚠️

| Parameter | Approximate value | Use |
|---|---|---|
| Annual rainfall | ~900–1,000 mm | Water-balance inputs |
| Monsoon share | ~85% in Jun–Sep (SW monsoon) | Kharif risk window |
| Summer max | Can exceed 45 °C in May–Jun | Zaid stress modelling |
| Winter min | Can approach 4–6 °C in Dec–Jan | **Frost/cold-wave risk** for gram, mustard, potato |
| Key hazards | Monsoon deficit/excess; **unseasonal rain and hail in Feb–Mar**; cold wave/frost in Dec–Jan; heat stress at wheat grain-fill in Mar | Risk register seeding |

Every figure here is indicative and must be replaced with actual IMD/Open-Meteo history for the
Prayagraj grid before the seed is built. The **Feb–Mar unseasonal rain and hail** hazard is the
one the demo leans on — it is a recurrent, well-documented UP event ✅ and it lands exactly in
the potato and wheat harvest window.

---

## 4. Crop portfolio for the demo FPO

Five core crops, chosen so that each one carries a *different* part of the product story:

| # | Crop | Season | Tract | What it demonstrates |
|---|---|---|---|---|
| 1 | **Paddy** | Kharif (Jun–Nov) | Ganga-par, doab | Baseline scale; aggregate production forecasting |
| 2 | **Wheat** | Rabi (Nov–Apr) | All tracts | Baseline scale; MSP/procurement contrast with open market |
| 3 | **Potato** | Rabi (Oct–Mar) | Doab | **The hero crop** — storage decisions, price crash risk, late blight |
| 4 | **Mustard** | Rabi (Oct–Mar) | Yamuna-par | Rain-fed exposure; the low-input/low-risk alternative |
| 5 | **Guava** | Perennial, winter harvest | **Ganga-par — Kaurihar and Phulpur blocks** ✅ | **Quality intelligence + GI** — grade prediction, premium buyers (§4.2) |

Optional sixth for contrast: **tomato** 🔧 — a perishable with *no* storage option, used to
show the urgency case against potato's hold-or-sell choice.

### 4.1 Recommendation: make potato the hero crop, not tomato

`MVP-SCOPE.md` and `ARCHITECTURE.md` currently use **tomato** in the override moment and the
buyer-allocation beat. **Potato is the stronger choice for a Prayagraj demo**, for four reasons:

1. **Storage is real.** UP has an extensive potato cold-storage network ✅. The demo beat
   *"500 t → Buyer A, 220 t → storage"* only makes sense for a crop that can actually be stored.
   With tomato, the storage option is fiction. The sell-now-vs-hold analysis (FR-547) and its
   break-even holding period become genuinely meaningful.
2. **Price crashes are documented.** UP potato glut price collapses are recurrent and well
   reported ✅ — so the Market module's oversupply warning is grounded in a real pattern a judge
   may already know about, rather than an invented 22% demand drop.
3. **Late blight is the perfect crop-health demo.** It is weather-driven (cool + humid), it
   **spreads geographically** — which exercises outbreak clustering (FR-525) — it has real IPM
   options before chemicals, and it is **visually confusable with early blight**, which is
   exactly the case the diagnostic-humility gate (FR-524) exists for. Tomato disease is a
   commodity classifier demo; potato late blight across 300 farms is an organizational risk demo.
4. **The harvest window collides with the hazard.** Potato harvest (Jan–Mar) sits inside the
   Feb–Mar unseasonal rain/hail window ✅ — so the Risk module's climate finding and the Market
   module's timing finding act on the same crop at the same moment. That is what makes the
   cross-domain override (FR-802) look inevitable rather than staged.

**Action:** switch the hero crop in the demo script and the override example. Tomato is retained
as the perishable contrast. *(Applied — see §9.)*

### 4.2 The guava GI — verified from the primary source ✅

Retrieved from the **Geographical Indications Journal No. 19, October 2007** (GI Registry,
Chennai) via the UP Directorate of Horticulture & Food Processing, 2026-08-22.

| Field | Value |
|---|---|
| GI name | **Allahabad Surkha Guava** |
| Application no. | **50** |
| Class / goods | 31 / Guava fruits |
| Applicant | Allahabadi Surkha Amrood Utpadak Welfare Association — Allahabad |
| Applicant address | Bankarabad, Bamroli Janpath, Allahabad |
| Advertised | Accepted under s.13(1), GI Act 1999; Journal 19, Oct 2007 |
| Origin | Chance seedling in village **Abubakkarpur**; a 4-year seedling spotted at village **Sulemsarai** |

**Registered quality specification** — real numbers, usable directly by the Quality module:

| Parameter | Value |
|---|---|
| Average fruit weight | 200 g |
| Size | 7.20 cm |
| Seeds per fruit | 280 |
| Yield in 6th year | 120 kg/tree |
| TSS | 13.75 % |
| Acidity | 0.40 |
| pH | 3.5 |
| Total sugar | 10.2 % |
| Vitamin C | 150 mg/100 g |
| Fruit | Large, slightly depressed at both ends; skin thin, uniform pink; flesh thick, whitish sometimes pink; sweet |

**Geographical area of production**, as stated in the application:

> Villages of **Chail, Muratganj, Newada, Manjhanpur** blocks of Allahabad District

with area tables naming:

| Block | Villages | Area (ha) | Avg. production (qtl/yr) |
|---|---|---:|---:|
| **Kaurihar II** (Chail area) | Bakarbad, Begambazar, Bamraulli, Makanpur, Janka | 25.5 | 4,190 |
| **Phulpur** | Korapur, others | 3.5 | 445 |
| *(Kaushambi section)* | Sudwar, Vihika, Koylaha, Fatehpur, Puramufti | 25.0 | 4,155 |
| **Muratganj** | Mahgaon, Sayad, Gauspur, Bhitti, Pattinarwar, Shrohi | 19.0 | 3,158 |

#### Two corrections this forces

1. **The guava belt is not in the doab.** The two blocks inside present-day Prayagraj —
   **Kaurihar** and **Phulpur** — are both in the **Ganga-par** tract. An earlier draft of this
   document placed the guava belt in Kaundhiyara/Chaka in the doab. That was wrong, and would
   have put the demo's guava growers on the wrong side of the Ganga.

2. **The GI area straddles a district boundary.** Chail, Muratganj, Newada and Manjhanpur are
   named as *Allahabad District* in the 2007 application, but **Kaushambi district was carved
   out of Allahabad in 1997** and those blocks sit in Kaushambi today. So the registered
   "Allahabad Surkha" area now spans two districts.

   This is not a problem — it is the best policy story in the whole demo, and it is *real*.
   A Prayagraj FPO with growers in Kaurihar and Phulpur has a legitimate claim to the GI; the
   compliance question of who may use the mark, and on what evidence, is exactly the
   *"sudden turbulence like GI tags"* pain the discovery session named. Build the policy event
   on this, not on an invented notification.

3. **The documented area is small.** The application's own tables total roughly **73 ha**.
   Secondary sources claiming ~1,000 ha under Surkha guava are describing something broader.
   The demo FPO's guava area should be modest — a premium sliver, not a major crop by acreage.

### 4.3 Crop calendar ⚠️

| Crop | Sowing | Harvest | Notes |
|---|---|---|---|
| Paddy | Jun–Jul (transplant) | Oct–Nov | Nursery ~3–4 weeks prior |
| Wheat | Nov–Dec | Mar–Apr | Heat stress at grain-fill is the key risk |
| Potato | Oct–Nov | Jan–Mar | Cold storage loading Feb–Mar |
| Mustard | Oct | Feb–Mar | Frost risk at flowering |
| Guava | Perennial | **Winter crop Nov–Feb** (quality), rainy crop Aug–Sep (lower grade) | The two-crop split is the quality story |

Exact dates must come from the UP Department of Agriculture crop calendar for the **Central
Plain Zone** before seeding.

---

## 5. Demo organization profile 🔧

**Prayagraj Kisan Producer Company Limited** — synthetic, `type = FPO`.

| Attribute | Value |
|---|---|
| Members | 1,000 |
| Total operated area | ~2,412 acres (976 ha) |
| Mean holding | ~0.98 ha (2.41 acres) |
| Blocks covered | 6, spanning all three tracts |
| Registered | 🔧 2021 (gives two closed seasons of outcome history) |

### 5.1 Landholding distribution

Skewed toward marginal holdings, consistent with eastern UP ✅. Targets the 2,412-acre total:

| Class | Farmers | Mean holding | Area (ha) | Area (acres) |
|---|---:|---:|---:|---:|
| Marginal (<1 ha) | 640 | 0.55 ha | 352.0 | 870 |
| Small (1–2 ha) | 260 | 1.32 ha | 343.2 | 848 |
| Semi-medium (2–4 ha) | 88 | 2.60 ha | 228.8 | 565 |
| Medium (4–10 ha) | 12 | 4.35 ha | 52.2 | 129 |
| **Total** | **1,000** | **0.98 ha** | **976.2** | **2,412** |

The seed generator draws from a log-normal fitted to these class means, then normalizes to hit
2,412 acres exactly so the demo number is reproducible (DR-09).

### 5.2 Tract allocation

| Tract | Farmers | Share of area | Irrigation coverage 🔧 |
|---|---:|---:|---:|
| Ganga-par | 420 | ~44% | 85% |
| Doab | 330 | ~34% | 78% |
| Yamuna-par | 250 | ~22% | 31% |

The Yamuna-par irrigation gap is what makes the risk clustering real. It must be verified ⚠️
against district irrigation statistics before it is presented as fact rather than as demo data.

### 5.3 Tenure mix 🔧

Exercises `PlotTenure` (ADR-0003) rather than leaving it theoretical:

| Tenure type | Share of plots |
|---|---:|
| OWNED | 72% |
| LEASED | 14% |
| SHARECROPPED (batai) | 9% |
| JOINT (undivided family) | 5% |

At least **12 plots** are seeded with tenure shares that do not sum to 100%, so the
`DataDiscrepancy` path has real data to surface in the demo (beat 5).

---

## 6. Markets

### 6.1 Mandis — verified ✅

Agmarknet lists **five markets** in Prayagraj district (district_id 646, state_id 34), retrieved
2026-08-22 from `api.agmarknet.gov.in/v1/market-district-state`:

| market_id | Market name | Category | Location note |
|---:|---|---|---|
| **298** | **Prayagraj APMC** | Principal Market Yard | The main yard. Carries the widest commodity range. |
| 1724 | Ajuha APMC | Principal Market Yard | |
| 1749 | Sirsa APMC | Principal Market Yard | Tehsil **Meja** — i.e. a real mandi in the rain-fed Yamuna-par tract |
| 1764 | Jasra APMC | Principal Market Yard | Jasra is also a block of Bara tehsil |
| 4389 | Lediyari APMC | Other | |

> **"Mundera Mandi" is not an Agmarknet market name.** It is the local name for the Prayagraj
> yard site; Agmarknet's key is **Prayagraj APMC**. Seeding "Mundera" as a market would have been
> exactly the kind of plausible-sounding fabrication the source register exists to prevent.

That **Sirsa APMC sits in Meja** is a gift for the demo: the rain-fed southern tract has its own
mandi, so the Market module can compare a local Yamuna-par outlet against the main Prayagraj yard
using real market identities rather than invented ones.

#### What the real data shows (14-day sample, 8–21 Aug 2026, 341 rows)

| Commodity | Market | Arrivals (MT) | Modal ₹/qtl |
|---|---|---:|---:|
| **Potato** | Prayagraj APMC | 3,063 | 700 (flat) |
| Wheat | Prayagraj APMC | 1,290 | 2,383 |
| Tomato | Prayagraj APMC | 1,287 | 2,049 |
| Onion | Prayagraj APMC | 1,077 | 906 |
| Paddy (Common) | Prayagraj APMC | 730 | 2,061 |

Three things this tells us:

1. **Potato is the largest agricultural arrival by volume** — the hero-crop choice (D-25) is now
   backed by real district data, not just reasoning.
2. **The August potato price is flat at ₹700/qtl.** August is out of season; the crop is sitting
   in cold storage. That is precisely the hold-vs-sell situation the Market module exists to
   reason about, and it is visible in the real series.
3. **Mustard and guava do not appear in an August sample**, which is seasonally correct — mustard
   is harvested Feb–Mar, guava Nov–Feb. The 24-month backfill is required before either crop has
   a real price basis.

**Before seeding:** run `python seed/fetch_agmarknet.py --from <24mo ago> --to <today>`. The
script caches one JSON payload per date and flattens to CSV. Keep the payloads — the offline demo
requirement (NFR-303) depends on them, not on the API being up on the day.

### 6.2 Buyers 🔧

Eight synthetic buyers, shaped so that **effective price reverses the headline ranking** (demo
beat 7):

| # | Type | Crop focus | Distance | Payment terms | Role in the demo |
|---|---|---|---|---:|---|
| B1 | Cold storage aggregator | Potato | 22 km | 15 days | The nearby, reliable option |
| B2 | Distant wholesaler | Potato | 180 km | 60 days | Highest headline price, worst effective price |
| B3 | Processor (chips/flakes) | Potato | 95 km | 30 days | Grade-A only; quality intelligence matters |
| B4 | Rice miller | Paddy | 18 km | 7 days | High reliability, modest price |
| B5 | Government procurement | Wheat | — | 21 days | MSP contrast |
| B6 | Oil mill | Mustard | 40 km | 20 days | Yamuna-par outlet |
| B7 | Premium fruit trader | Guava | 30 km | 10 days | Pays a GI/grade premium |
| B8 | Institutional/e-commerce | Guava, vegetables | 140 km | 45 days | Strict grade, high rejection risk |

The B1-vs-B2 pair is the demo's effective-price moment: **B2 offers more per kg and lands less
in the farmer's hand** once logistics, storage, financing on a 60-day delay and rejection risk
are netted out.

---

## 7. Government schemes

Central schemes almost certainly applicable ✅ (each still needs a `seed/sources.md` row with
its current eligibility text):

PM-KISAN · PMFBY (crop insurance) · Kisan Credit Card · Soil Health Card · PM-KUSUM (solar
pumps) · Agriculture Infrastructure Fund · SFAC 10,000 FPO scheme · NABARD FPO equity grant and
credit guarantee.

State/UP schemes ⚠️ — **verify current status and eligibility before use**, as state schemes
change and lapse frequently. Candidates to check: Mukhyamantri Krishak Durghatna Kalyan Yojana,
UP Kisan Kalyan Mission, state tubewell/solar-pump subsidies, and UP horticulture-mission
support for guava.

**Rule:** a scheme enters the seed only with (a) its source URL, (b) the retrieval date, and
(c) eligibility rules transcribed into the machine-evaluable JSON form (ARCHITECTURE §4.6). A
scheme whose rules we cannot transcribe faithfully is dropped, not approximated — presenting a
farmer as eligible for something they are not is a real harm, not a demo blemish.

---

## 8. Seeded external events 🔧

Twenty news/policy events, of which four are load-bearing for the demo:

| Event | Domain | Causal chain it drives |
|---|---|---|
| Diesel price raised | SUPPLY_CHAIN | logistics cost ↑ → distant buyer effective price ↓ → nearby buyer overtakes → revisit allocation |
| Unseasonal rain + hail forecast, Feb window | CLIMATE | harvest-window risk ↑ on potato and wheat → exposure quantified by tract → advance-harvest / storage decision |
| Potato arrivals surge across UP mandis | MARKET | oversupply → price band falls → hold-vs-sell analysis, cold-storage capacity constraint |
| GI-related quality/labelling notification for guava | POLICY | grade compliance requirement → which growers meet it → premium buyer access |

The GI event is the one to invest in ⚠️ — it directly answers the user's own "sudden turbulence
like GI tags" pain, and it is the most memorable item in the risk feed. It must be built from
the **actual** GI registration and any real notification, not invented, or it becomes the weakest
point in the pitch instead of the strongest.

---

## 9. Changes applied to other documents

| Document | Change |
|---|---|
| `context.md` | O-1 resolved; decision D-24 recorded |
| `docs/MVP-SCOPE.md` | Demo script: hero crop tomato → **potato**; beats 4, 6, 7 rewritten for Prayagraj |
| `docs/ARCHITECTURE.md` | Cross-domain override example rewritten for potato + Feb hail window |
| `seed/sources.md` | Created — citation checklist gating everything above; §10 records the 2026-08-22 verification pass |

---

## 10. Verification checklist before any seeding

Nothing marked ⚠️ may enter `seed/` until it is checked off here.

- [x] ~~UP agro-climatic zone assignment~~ → **Central Plain + Vindhyachal** (2026-08-22); still
      confirm against the official UP Dept. of Agriculture zone map before seeding yields
- [x] ~~Block list~~ → **verified** against `prayagraj.nic.in` (2026-08-22): 8 tehsils, 23 blocks
- [ ] Block-to-**tract** mapping — which side of which river each block sits on
- [ ] IMD/Open-Meteo rainfall, temperature and humidity normals for the Prayagraj grid
- [x] ~~Agmarknet market list~~ → **verified** (2026-08-22): 5 markets, §6.1. The API route is
      documented in `seed/sources.md` §10 and wrapped by `seed/fetch_agmarknet.py`.
- [ ] 24 months of price and arrival series — **path proven**, backfill not yet run
      (mustard and guava need it; they are out of season in the sample)
- [ ] District landholding distribution and irrigation coverage statistics
- [ ] Crop calendar for the **Central Plain Zone** (sowing/harvest windows)
- [ ] Base yield coefficients per crop per zone
- [x] ~~Guava GI registration, name, area~~ → **verified** from GI Journal 19 (2026-08-22);
      see §4.2. Quality spec now usable directly by the Quality module.
- [ ] Current eligibility text for every central and state scheme in §7
- [ ] Cold-storage capacity and rental rates for the district
- [ ] At least one Prayagraj-area FPO or agronomist contact to sanity-check the profile (**O-2**)

The last item is the highest-value one. A single conversation with someone who actually farms in
Prayagraj will catch more errors than every other item on this list combined.
