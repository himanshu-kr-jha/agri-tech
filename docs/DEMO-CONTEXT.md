# Demo Context — Prayagraj, Uttar Pradesh

Version 1.0 · 2026-08-22 · Resolves open question **O-1**

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
2. **A GI-tagged crop.** Prayagraj guava carries a Geographical Indication ⚠️. The discovery
   session named *"sudden turbulence like GI tags"* as a specific FPO pain — this district lets
   us demo that with a real crop rather than a hypothetical.
3. **Smallholder-dominant.** Eastern UP is overwhelmingly small and marginal farmers ✅, which
   is exactly the underserved population the challenge brief targets.

---

## 2. Geography — the three tracts

Prayagraj sits at the Ganga–Yamuna confluence. The rivers divide it into three tracts with
materially different agriculture ✅:

| Tract | Blocks (indicative ⚠️) | Character | Irrigation | Implication for the demo |
|---|---|---|---|---|
| **Ganga-par** (north / trans-Ganga) | Phulpur, Soraon, Handia, Pratappur, Bahria | Alluvial plain, deep fertile soil | Canal + tubewell, reliable | Paddy–wheat belt. Low weather exposure. |
| **Doab** (central, between the rivers) | Chaka, Kaundhiyara, Karchhana, Shankargarh fringe | Good alluvium, peri-urban market access | Tubewell, generally good | Vegetables, potato, **guava belt**. Best market access. |
| **Yamuna-par** (south / trans-Yamuna, Vindhyan) | Bara, Meja, Koraon, Shankargarh | Rocky, red/lateritic, undulating, shallow soils | Largely rain-fed | Gram, arhar, bajra, mustard. **High rainfall exposure.** |

**This is the demo's backbone.** When the Risk module says *"312 farmers / 740 acres exposed"*,
those farmers should cluster in Yamuna-par — and the drill-down should make that visible on the
map. A uniform farmer population would make the drill-down look like a list; this makes it look
like an insight.

### Agro-climatic classification ⚠️

Prayagraj is generally placed in Uttar Pradesh's **Eastern Plain Zone**, with the trans-Yamuna
southern blocks falling into the **Vindhyan Zone**. This split must be verified against the UP
Department of Agriculture's zone map before it is used to select yield coefficients, because the
two zones carry different base yields.

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
| 5 | **Guava** | Perennial, winter harvest | Doab (Kaundhiyara/Chaka belt ⚠️) | **Quality intelligence + GI** — grade prediction, premium buyers |

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

### 4.2 Crop calendar ⚠️

| Crop | Sowing | Harvest | Notes |
|---|---|---|---|
| Paddy | Jun–Jul (transplant) | Oct–Nov | Nursery ~3–4 weeks prior |
| Wheat | Nov–Dec | Mar–Apr | Heat stress at grain-fill is the key risk |
| Potato | Oct–Nov | Jan–Mar | Cold storage loading Feb–Mar |
| Mustard | Oct | Feb–Mar | Frost risk at flowering |
| Guava | Perennial | **Winter crop Nov–Feb** (quality), rainy crop Aug–Sep (lower grade) | The two-crop split is the quality story |

Exact dates must come from the UP Department of Agriculture crop calendar for the Eastern Plain
Zone before seeding.

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

### 6.1 Mandis ⚠️

Agmarknet publishes arrivals and prices per market for the district. The principal market is the
Prayagraj (Mundera) mandi ⚠️; secondary markets in the district need to be enumerated from
Agmarknet's own market list rather than from memory.

**Before seeding:** pull the actual Agmarknet market list for Prayagraj district, take 24 months
of modal/min/max price and arrival series for paddy, wheat, potato, mustard and guava, and record
each series in `seed/sources.md`. Do not invent market names — a judge from UP will notice.

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
| `seed/sources.md` | Created — citation checklist gating everything above |

---

## 10. Verification checklist before any seeding

Nothing marked ⚠️ may enter `seed/` until it is checked off here.

- [ ] UP agro-climatic zone assignment for Prayagraj, including the trans-Yamuna split
- [ ] Block-to-tract mapping (the block lists in §2 are indicative only)
- [ ] IMD/Open-Meteo rainfall, temperature and humidity normals for the Prayagraj grid
- [ ] Agmarknet market list for Prayagraj district — **actual names**
- [ ] 24 months of price and arrival series for the five crops
- [ ] District landholding distribution and irrigation coverage statistics
- [ ] Crop calendar for the Eastern Plain Zone (sowing/harvest windows)
- [ ] Base yield coefficients per crop per zone
- [ ] Guava GI registration status, registered name(s), and the geographic area covered
- [ ] Current eligibility text for every central and state scheme in §7
- [ ] Cold-storage capacity and rental rates for the district
- [ ] At least one Prayagraj-area FPO or agronomist contact to sanity-check the profile (**O-2**)

The last item is the highest-value one. A single conversation with someone who actually farms in
Prayagraj will catch more errors than every other item on this list combined.
