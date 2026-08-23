# AgriVardhak — Product Context & Decision Log

Status: **product direction locked**, data model resolved, implementation not started.
Last updated: 2026-08-22.

This document is the memory of *why* the system is shaped the way it is. `CLAUDE.md` holds
the rules; this holds the reasoning. Source material: `docs/discovery-transcript.md` — a
21-turn product-discovery session that deliberately refused to write code until the product
was pinned down.

---

## 1. Where this came from

The starting brief was a hackathon problem statement:

> **AI for Public Good** — Theme: *Inclusive AI, Social Impact and Empowerment of
> Underserved Communities.* Build an AI-powered solution addressing a real-world problem
> for an underserved or marginalized community in India, improving access to information,
> decision-making, livelihoods, safety, essential services or economic opportunity.
> Solutions should account for local languages, digital accessibility and limited connectivity.

The initial idea was a **farmer-facing app**: crop recommendation + disease detection +
government schemes + a data flywheel selling datasets to researchers.

That was rejected as a *feature list, not a product*, for three reasons:

1. A disease classifier is a commodity hackathon feature; the interesting product is the
   **decision system around the classifier**.
2. "Collect data from poor farmers → sell intelligence to wealthy companies" would
   undermine the public-good premise.
3. Individual-farmer advisory apps already exist and do not fix the structural problem.

**The pivot:** make it **FPO-centric**. The unit of intelligence moves from
`Farmer → AI advice` to `Organization → understands its farmer network → aggregates
demand/supply/risk → makes better decisions → improves farmer economics`.

---

## 2. Product thesis (locked)

> **AgriVardhak is an AI decision & orchestration ecosystem for farmer collectives.**
> It converts fragmented farmer-level data and external agricultural intelligence into
> **auditable, human-approved organization-level actions** that improve farmer income.

Optimization target, agreed verbatim:

> maximize **sustainable farmer income + FPO financial health**, subject to risk,
> available capital, demand, crop suitability, water/land constraints, operational
> constraints, integrated farming, appropriate pesticide/fungicide levels, and optimal
> farming techniques.

Explicitly **not** "maximize FPO profit" — an FPO can maximize its own margin by hurting
farmers, which contradicts the entire premise.

### The economic leakage we attack

The originating pain, in the user's own words:

> *"FPO doesn't know three months beforehand that 400 tonnes of tomato will be available,
> so it cannot secure buyers/storage/logistics."*

Plus: FPO disputes causing farmers to lose their share; sudden policy turbulence (GI tags,
fuel prices, scheme changes); lack of basic crop inputs.

### The two CEO questions that define the product

1. *"How much fund should we allocate to each farmer to invest in their respective land?"*
2. *"How do we maximize FPO profits this season using crop status, demand forecasting,
   allocated funds, government schemes and agricultural news?"*

These are far stronger than "what crop should I grow?" — they are **organizational
capital-allocation and market-strategy questions**, and no existing product answers them.

---

## 3. The core loop (locked)

```
Observe → Understand → Recommend → Human approve → Execute → Measure → Attribute → Learn
```

and for every consequential recommendation:

```
Recommendation → Intervention → Outcome → Attribution
```

The attribution step is what makes this a learning system rather than a chatbot: it records
whether the advice was actually followed, how faithfully, and what external conditions
co-occurred — so the model does not learn "my advice failed" from advice never implemented.

---

## 4. Roles (locked at three for MVP)

| Role | Sees / does |
|---|---|
| **Platform Admin** | Manages the ecosystem, organizations, data sources, model config. |
| **FPO CEO** | Organization-wide view, asks the assistant strategic questions, reviews and approves recommendations, drills down to individual farmers/plots. |
| **Farmer** | Own profile, farms, plots, crop cycles, recommendations, calendar, funding, schemes, sales — plus FPO information *officially shared* with them. |

Deferred to POST-MVP but designed for: Field Officer, Procurement/Market Officer,
Finance Officer, Researcher. Permissions are **role-based**, not hard-coded to job titles,
because one person routinely holds several of these roles in a real FPO.

**Information boundary (INV-5):** a farmer never automatically sees other farmers, FPO
internal strategy, buyer negotiations, FPO finances, or other farmers' risk scores. Only
information marked *official / explicitly shared* crosses the boundary.

---

## 5. The two assistants

| | Farmer Assistant | FPO Assistant |
|---|---|---|
| Question | *"What should I do on my farm today?"* | *"What should our organization do?"* |
| Context | Farmer → Farm → Plot → CropCycle → Health → Intervention → Calendar → Outcome | Organization → Farmers → Farms → Crops → Production → Quality → Risks → Demand → Buyers → Resources → Schemes → Actions |
| Drill-down | none (own data only) | full, down to plot level |

Same orchestrator, two **context scopes** enforced in the data-access layer.

---

## 6. Six intelligence modules + an orchestrator

Not one giant prompt. Six specialized, deterministic modules whose outputs an LLM
orchestrator reconciles:

1. **Farm Intelligence** — crop status, farming practices, integrated farming, resource constraints.
2. **Crop Health Intelligence** — disease/pest, prevention, treatment, intervention effectiveness.
3. **Quality Intelligence** — crop health → expected quality → expected quantity → harvest window.
4. **Market Intelligence** — demand, buyers, effective price, transaction attractiveness, alternatives.
5. **Risk Intelligence** — climate, weather, crop health, market, policy, supply chain, global events.
6. **Scheme Intelligence** — eligibility, affected farmers, documents, deadlines, status.

The **Orchestrator may override a single module** when cross-domain evidence changes the
decision. Canonical example agreed in the session:

> Crop module says *grow tomato*. Market module says *tomato demand collapsing*. Risk module
> says *extreme rainfall expected*. The orchestrator must **not** blindly follow the crop
> module; it proposes an alternative crop with a better expected sustainable outcome.

---

## 7. Key product decisions (with the reasoning)

| # | Decision | Why |
|---|---|---|
| D-01 | **FPO-centric, not farmer-centric** | Organizational leverage; the aggregation problem is the real unsolved one. |
| D-02 | Support **FPO + PACS + SHG** via a generic `Organization` abstraction | All three exist in the field; abstraction now avoids a rewrite later. FPO is the hackathon implementation. |
| D-03 | Hero capabilities: **Market/Selling Intelligence + Risk Intelligence** | Chosen explicitly over crop planning / production forecasting / scheme access as the two to build deeply. |
| D-04 | Crop recommendation happens at the **individual farmer level**; the FPO gets the aggregate | "Data collected at individual level helps" — aggregation is a view, not a separate pipeline. |
| D-05 | **Advisory intelligence**, not coordinated production planning | The FPO recommends; farmers stay independent. Determines the entire authority model. |
| D-06 | Objective = **ROI** (expected incremental income ÷ FPO investment), not revenue or yield | ₹80k on ₹20k beats ₹100k on ₹80k. |
| D-07 | **Risk-adjusted** profit, not raw maximum | Strategy C (₹18.5L, moderate risk) beats Strategy A (₹20L, high risk) *when risk is manageable*. |
| D-08 | AI **recommends + explains**; a human approves | Accountability stays with the FPO decision-maker. |
| D-09 | The AI never says **"don't invest in this farmer"** | Explicit product requirement. Framing is always constructive: reprioritize, phase, de-risk — never exclude a farmer by name. |
| D-10 | **Full audit trail** on every consequential decision | Directly addresses the "FPO disputes cause farmers to lose their share" pain. Strong audit trail, not blockchain. |
| D-11 | **Effective price**, not headline price | `buyer price − logistics − handling − quality loss − transaction costs − storage − financing − rejection risk`. Implemented in M7; the arithmetic showed **rejection risk is the largest term**, several times freight, so it is priced into the subtraction rather than only scored as risk. See `docs/DEMO-CONTEXT.md` §6.2. |
| D-12 | Buyer recommendation ships with **alternatives + a negotiation brief** | "Recommend buyer + prepare negotiation brief also provide alternatives." |
| D-13 | **News → causal chain → FPO impact → recommended action** | Not a news feed. Petrol ↑ → logistics cost ↑ → distant buyer less attractive → nearby buyer more competitive → recommendation changes. |
| D-14 | **IPM-first crop protection** | Natural/preventive methods by default; chemicals only in dire need; ranked by effectiveness + cost + sustainability + resistance risk. |
| D-15 | **Integrated farming is first-class** | Crop, livestock, poultry, fishery, compost/manure, agroforestry modelled as `FarmResource` with `ResourceFlow` between them. Objective is *max sustainable farm income per unit of land/water/capital*, not max yield of one crop. |
| D-16 | **Quality predicted before harvest** | crop health → expected quality → expected quantity → buyer matching. Prediction vs actual becomes a learning signal. |
| D-17 | Buyer matching is visible to **both** farmer and FPO, at lot/farmer level | Explicitly requested. |
| D-18 | **Provenance on every consequential value** | An AI decision from stale self-reported data must not carry the same confidence as a field-verified observation. |
| D-19 | Source conflicts → **show discrepancy + request verification + confidence scoring** | Never silently pick a value. |
| D-20 | **Unified but individual-scoped calendar** | Manual entry by farmer/FPO/whoever it concerns, plus automatic feeds. Every auto-generated consequential schedule needs field-officer approval. |
| D-21 | Financial optimization is **deliberately shallow for MVP** | "We should provide the farmer the money that is meant for him." Deep financial modelling needs data and a finance team; keep it simple to win. |
| D-22 | Data-revenue model: **ecosystem fund (Model C)** | Not kept by the platform. Deferred as a business-model concern, but the ethical position is fixed. |
| D-23 | Public-good impact metrics: **farmer income, employment, government-benefit access, food production, supply-chain efficiency** | Instrumented, and proxy metrics clearly labelled as estimates. |
| D-24 | Demo anchored to **Prayagraj district, Uttar Pradesh** (2026-08-22) | Three agriculturally distinct tracts split by the Ganga and Yamuna give one FPO genuine internal heterogeneity, so risk clustering and drill-down show a pattern rather than a list. Smallholder-dominant, matching the brief's target population. Guava carries a GI tag, which lets us demo the "sudden turbulence like GI tags" pain with a real crop. Full profile in `docs/DEMO-CONTEXT.md`. |
| D-25 | **Potato is the hero crop**, not tomato | Consequence of D-24. Cold storage genuinely exists in UP, so the hold-vs-sell and storage-allocation beats stop being fiction; UP potato price crashes are a documented recurrent pattern; late blight is weather-driven, geographically clustering, and visually confusable with early blight — exercising outbreak detection and the diagnostic-humility gate; and the Jan–Mar harvest window collides with the Feb–Mar unseasonal-rain hazard, so the market and climate findings land on the same crop and the cross-domain override looks inevitable rather than staged. Tomato is retained as the no-storage perishable contrast. |

---

## 8. Technical decisions taken after the discovery session

The session ended with 8 open data-model questions. All 8 are now resolved — full
reasoning in `docs/DATA-MODEL.md`, summary here:

| Q | Question | Resolution |
|---|---|---|
| 1 | Generic `Organization` or `FPO` as core entity? | **Generic `Organization` with `type` enum** (ADR-0002). |
| 2 | Can a farmer belong to multiple organizations? | **Yes** — `Membership` join entity from day one; MVP UI shows a primary org. |
| 3 | Separate land ownership from cultivation? | **Yes** — `Plot` (physical) + `PlotTenure` (who holds it, how, what share) + `Membership` (org relationship) are three separate things (ADR-0003). |
| 4 | Multiple crop cycles per plot over time? | **Yes** — `CropCycle` is the central temporal entity; a plot has many, overlapping only when explicitly intercropped. |
| 5 | Should AI reason over the integrated-farming resource graph? | **Model it now, reason POST-MVP.** `FarmResource` + `ResourceFlow` are stored and displayed in MVP; substitution reasoning ("use livestock manure instead of buying fertilizer") is a stretch goal. |
| 6 | Freeze the evidence snapshot on each recommendation? | **Yes, mandatory** — immutable JSONB + content hash (ADR-0004). |
| 7 | Separate `Prediction` from `Recommendation`? | **Yes** — different lifecycles and different evaluation (prediction vs actual; recommendation vs adherence vs outcome). |
| 8 | Record whether the farmer followed the recommendation? | **Yes** — `Intervention.adherence` (followed, fidelity, deviation) is required before an `Attribution` can be computed. |

Additional engineering decisions:

| # | Decision | ADR |
|---|---|---|
| T-01 | Next.js 15 + FastAPI + PostgreSQL 16 (PostGIS + pgvector) | ADR-0001 |
| T-02 | **Observation-centric append-only model** for volatile facts; plain columns for stable ones — avoids EAV sprawl while keeping full provenance | ADR-0005 |
| T-03 | LLM orchestrator over **deterministic** intelligence modules (no trained models in MVP) | ADR-0006 |
| T-04 | Postgres transactional-outbox `DomainEvent` log instead of a message broker | ADR-0007 |
| T-05 | Multi-channel farmer access: **Web (Hi/En) is complete; WhatsApp and Voice are demo-depth only** | ADR-0008 |
| T-06 | UUIDv7 ids; money in paise; area in m²; mass in kg | ADR-0009 |
| T-07 | **Aggregate confidence is a tonnage-weighted mean, not the minimum** | Weakest-link is right for a single claim — a chain built on one stale reading is only as good as that reading. It is wrong for a rollup: a 1,900 t forecast from 1,282 independently observed cycles is not made worthless by one plot nobody visited. Using min() reported 0.00 on the whole forecast, which was both wrong and useless. Weak evidence is now surfaced as its own finding instead, naming the cycles a field visit would help most. Found building M6. |
| T-08 | **Crop-health half-life 14 days, not 7** | 7 days conflated how fast a *crop* changes with how fast our *information about it* decays. A week-old field-officer reading is still worth a great deal. At 7 days every aggregate forecast collapsed to ~0 confidence. |
| T-09 | **Design system cloned from the Krishi·OS FPO console reference** — paper ground, hairlines instead of shadows, Fraunces on every number, gold accent once per screen, light-only | ADR-0010 |

---

## 9. Constraints

- **48–72 hours, 3–5 people.** This is the single largest constraint and it is why
  `docs/MVP-SCOPE.md` has an explicit cut list.
- Farmers have limited connectivity and limited literacy; Hindi + English are required,
  and the FPO/field-officer operator is the primary digital interface.
- No real FPO data is available. The demo runs on a **synthetic but agronomically plausible**
  1,000-farmer FPO in `seed/`, anchored to **Prayagraj district, Uttar Pradesh** (D-24), and
  every synthetic number is labelled as such in the UI. Nothing enters `seed/` without a row in
  `seed/sources.md`.
- Real external data where feasible (IMD/Open-Meteo weather, Agmarknet mandi prices,
  myScheme scheme text); mocked with cited-shape fixtures where an API is unavailable in time.

---

## 10. What is deliberately NOT in scope

Marketplace / transaction execution · payments & disbursement rails · a real financial
allocation optimizer · trained CV disease models · satellite/IoT ingestion · researcher
dataset marketplace and paid tier · logistics booking · blockchain · offline-first sync ·
multi-tenant billing.

Each of these was discussed and consciously deferred. See `docs/MVP-SCOPE.md#cut-list`.

---

## 11. Open questions still needing a human answer

| # | Question | Blocks |
|---|---|---|
| ~~O-1~~ | ~~Which state/district anchors the demo FPO?~~ → **Answered 2026-08-22: Prayagraj, Uttar Pradesh.** See D-24 and `docs/DEMO-CONTEXT.md`. | — |
| O-2 | Is there a real FPO contact or agronomist in the Prayagraj area who can sanity-check the profile? | Judge credibility — this is now the highest-value open item; one conversation catches more errors than the entire `seed/sources.md` checklist |
| O-3 | Is WhatsApp Business API sandbox access already provisioned? | ADR-0008 depth; go/no-go at build hour 24 |
| O-4 | Team skill split (frontend / backend / ML / data) | Task assignment in MVP-SCOPE §5 |
| O-5 | Run the 24-month Agmarknet backfill (`seed/fetch_agmarknet.py`) — mustard and guava have no price basis without it | Market module realism; commit the payloads as the offline fixture bundle |

Answer these in this file rather than in chat, so the decision survives the session.
