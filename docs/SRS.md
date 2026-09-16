# Software Requirements Specification — AgriVardhak

**AI Decision & Orchestration Platform for Farmer Collectives**

| | |
|---|---|
| Version | 1.0 |
| Date | 2026-08-22 |
| Status | Baselined — approved for implementation |
| Basis | `docs/discovery-transcript.md`, decisions D-01…D-23 and T-01…T-06 in `context.md` |
| Audience | Implementation team (3–5), hackathon judges, future maintainers |

Requirement IDs are **stable**. Never renumber; deprecate with `(WITHDRAWN)` instead.

---

## Table of contents

1. [Introduction](#1-introduction)
2. [Overall description](#2-overall-description)
3. [External interface requirements](#3-external-interface-requirements)
4. [Functional requirements](#4-functional-requirements)
5. [Data requirements](#5-data-requirements)
6. [Non-functional requirements](#6-non-functional-requirements)
7. [Trust, safety and ethics requirements](#7-trust-safety-and-ethics-requirements)
8. [Acceptance criteria](#8-acceptance-criteria)
9. [Traceability](#9-traceability)

---

## 1. Introduction

### 1.1 Purpose

This SRS specifies the requirements for **AgriVardhak**, a platform that gives Indian farmer
collectives (FPOs, PACS, SHGs) an AI decision and orchestration layer over their farmer
network. It is written to be implementable in a 48–72 hour build by a team of 3–5, while
describing the full product so that post-hackathon work has a spine.

### 1.2 Scope

**In scope.** Farmer/farm/plot/crop-cycle digital record; observation capture with
provenance; six deterministic intelligence modules; an LLM orchestrator producing auditable
**Decision Packets**; a human approval lifecycle; a unified calendar; drill-down from
organization aggregate to individual plot; farmer and FPO assistants with a hard information
boundary; government-scheme eligibility screening; buyer matching by effective price;
news/policy causal-impact reasoning; and an outcome/attribution learning loop.

**Out of scope for v1.0.** Marketplace/transaction execution, payment rails, a real financial
allocation optimizer, trained computer-vision models, satellite/IoT ingestion, the researcher
dataset marketplace, logistics booking, offline-first sync.

### 1.3 Definitions

See `docs/GLOSSARY.md` for the full ubiquitous language. Terms used throughout:

- **Decision Packet** — the canonical structured answer the orchestrator produces: Situation,
  Impact, Recommendation, Expected outcome, Confidence, Evidence, Actions, Schedule, Drill-down.
- **Effective Price** — buyer price net of every cost and risk of actually realizing it.
- **Provenance** — source, observation time, recording time, confidence, verification status
  attached to a value.
- **Attribution** — the assessment of how much of an observed outcome is plausibly explained
  by a followed recommendation versus external conditions.
- **FPO** — Farmer Producer Organization. **PACS** — Primary Agricultural Credit Society.
  **SHG** — Self-Help Group. **IPM** — Integrated Pest Management. **MSP** — Minimum Support Price.

### 1.4 References

- `context.md` — product context and decision log
- `docs/DATA-MODEL.md` — entities, events, provenance
- `docs/ARCHITECTURE.md` — layers and module contracts
- `docs/MVP-SCOPE.md` — 72-hour plan and cut list
- `docs/adr/` — architecture decision records

---

## 2. Overall description

### 2.1 Product perspective

AgriVardhak sits between three worlds that currently do not talk to each other:

```
   Farmer-level reality              External intelligence           Organizational decisions
   ────────────────────              ─────────────────────           ───────────────────────
   plots, crops, health,             weather, mandi prices,          who to sell to, what to
   inputs, livestock,        ──▶     demand, policy, schemes,  ──▶   procure, which farms need
   harvest, income                   news, fuel, global events       intervention, which schemes
                                                                     to pursue, what to fund
                                    ▲                                          │
                                    └──────── outcomes & attribution ──────────┘
```

The product's differentiator is **not** any single model. It is the **connective tissue**:
one data model that makes farmer-level facts, external signals, AI predictions, human
approvals and realized outcomes queryable together, with provenance, in a way that produces
auditable decisions.

### 2.2 Product functions (summary)

| # | Function |
|---|---|
| F1 | Maintain a digital record of the collective: members, farms, plots, crop cycles, integrated-farming resources |
| F2 | Capture observations with provenance from multiple sources and surface conflicts |
| F3 | Ingest external intelligence: weather, market, policy/scheme, news, supply-chain |
| F4 | Produce predictions (yield, quality, harvest window, risk) with confidence |
| F5 | Produce recommendations with frozen evidence, alternatives and expected impact |
| F6 | Route recommendations through a human approval lifecycle and execute approved actions |
| F7 | Answer the FPO CEO's and the farmer's natural-language questions as Decision Packets |
| F8 | Maintain a risk register and proactive morning briefing |
| F9 | Screen scheme eligibility across the membership and track document readiness |
| F10 | Match produce lots to buyers on effective price and transaction attractiveness |
| F11 | Maintain a unified, individually scoped calendar with approval gates |
| F12 | Capture outcomes, adherence and attribution; feed the learning loop |
| F13 | Enforce the farmer↔FPO information boundary and consent |
| F14 | Report public-good impact metrics |

### 2.3 User classes

| Class | Technical skill | Connectivity | Language | Frequency |
|---|---|---|---|---|
| **Platform Admin** | High | Good | English | Rare, administrative |
| **FPO CEO / Manager** | Medium | Good (laptop + smartphone) | Hindi + English | Daily |
| **Farmer** | Low; may be functionally non-literate | Intermittent, low-bandwidth | Hindi (regional post-MVP) | Weekly, or on prompt |
| *(POST-MVP)* Field Officer | Medium | Intermittent, field | Hindi | Daily, mobile |
| *(POST-MVP)* Researcher | High | Good | English | Occasional, API |

### 2.4 Operating environment

- Web: evergreen Chrome/Edge/Firefox/Safari, and Android Chrome on 360px-wide screens.
- Server: Linux, Docker Compose for local/demo; single VPS or container host for the demo.
- Farmer channels: web (primary), WhatsApp Cloud API (notification + simple Q&A),
  browser voice input (demo-grade Hindi ASR).

### 2.5 Constraints

| ID | Constraint |
|---|---|
| C-1 | 48–72 hours of build time, 3–5 people. |
| C-2 | No real FPO data. All demo data is synthetic and must be labelled as such in the UI. The demo is anchored to **Prayagraj district, Uttar Pradesh** (D-24); district facts must be sourced via `seed/sources.md` or marked synthetic. |
| C-3 | No trained ML models in MVP; intelligence modules are deterministic (ADR-0006). |
| C-4 | No autonomous consequential action by AI, ever (INV-1). |
| C-5 | No exact chemical product + dosage advice without a cited authoritative source (INV-8). |
| C-6 | Farmer-facing text must be available in Hindi and English. |

### 2.6 Assumptions and dependencies

| ID | Assumption |
|---|---|
| A-1 | The FPO operator has a smartphone or laptop with reasonable connectivity. |
| A-2 | Farmer data is entered primarily by the FPO/field officer, not by farmers themselves. |
| A-3 | Government/agricultural record integration is POST-MVP; MVP uses manual + self-reported + AI-inferred data. |
| A-4 | Buyers provide quantity, price, quality requirement, delivery date, location and payment terms. |
| A-5 | Open-Meteo (weather), Agmarknet (mandi prices) and myScheme (scheme text) are reachable for the Prayagraj district / Central Plain Zone; each has a cited-shape fixture fallback. |
| A-6 | Anthropic API access is available for the orchestrator and assistants. |

---

## 3. External interface requirements

### 3.1 User interfaces

| ID | Requirement | Priority |
|---|---|---|
| UI-01 | The FPO console SHALL present a 10-card organizational dashboard: total farmers, total acreage, crop mix, expected production, expected sales value, market opportunities, risk alerts, fund requirement, scheme opportunity, pending actions/approvals. | MUST |
| UI-02 | Every AI-derived number SHALL render with a **confidence chip** and a **provenance popover** (source, observed date, verification status). | MUST |
| UI-03 | Every Decision Packet SHALL render its nine sections in fixed order and SHALL expose a one-click **Drill-down** to the affected farmers → plots → crop cycles. | MUST |
| UI-04 | Any value derived from synthetic seed data SHALL carry a visible `DEMO DATA` marker. | MUST |
| UI-05 | The farmer portal SHALL be usable at 360px width, at ≤3 taps to the day's actions, with a Hindi/English toggle persisted per user. | MUST |
| UI-06 | The farmer portal SHALL accept voice input for its primary question field (browser ASR, Hindi + English). | SHOULD |
| UI-07 | Approval controls SHALL be disabled, with an explanatory tooltip, for users whose role lacks approval authority. | MUST |
| UI-08 | The risk register SHALL render as a sortable table: risk, probability, impact, farmers affected, recommended action, status. | MUST |
| UI-09 | The calendar SHALL visually distinguish MANUAL / AUTO_GENERATED / AI_RECOMMENDED / OFFICIAL_DEADLINE events, and SHALL show pending-approval events in a distinct state. | MUST |
| UI-10 | Data discrepancies SHALL be shown inline at the point of use, never hidden in an admin screen. | MUST |
| UI-11 | Every screen — sign-in, farmer portal and FPO console — SHALL carry one Hindi/English switch at the top right. Switching SHALL translate all visible text on the page, including API-derived content and content rendered after load, without changing layout, routing or interactions. Static interface text SHALL come from a stored dictionary; everything else SHALL be translated on demand through Sarvam and kept in a translation memory so the same string is never paid for twice (ADR-0023). Personal names, identifiers, numbers and code SHALL NOT be translated. Domain terms (FPO, the collective, units such as acres, crop names) SHALL always render with the single Hindi/English equivalent recorded in the translation glossary, never a model's choice (ADR-0023 §9). | MUST |

### 3.2 API interfaces

| ID | Requirement | Priority |
|---|---|---|
| API-01 | The backend SHALL expose a versioned REST API under `/api/v1` with an OpenAPI 3.1 document generated from Pydantic models. | MUST |
| API-02 | TypeScript client types SHALL be generated from the OpenAPI document into `packages/contracts`; hand-written duplicates are prohibited. | MUST |
| API-03 | All endpoints SHALL require a JWT bearer token carrying `sub`, `org_id`, `roles[]`; authorization SHALL be enforced server-side per row, not by hiding UI. | MUST |
| API-04 | The API SHALL return RFC 9457 problem-details for errors. | SHOULD |
| API-05 | Assistant endpoints SHALL stream Decision Packet sections via SSE as they are produced. | SHOULD |

### 3.3 External data interfaces

| ID | Source | Data | Cadence | Fallback |
|---|---|---|---|---|
| EXT-01 | Open-Meteo / IMD | Daily forecast + historical: rainfall, temp, humidity, wind, per plot centroid | 6-hourly | Fixture per district |
| EXT-02 | Agmarknet | Mandi arrivals & modal/min/max prices per commodity/market | Daily | 24-month fixture |
| EXT-03 | myScheme / state portals | Scheme name, description, eligibility text, documents, deadlines | On demand, cached | Curated fixture of 12 schemes |
| EXT-04 | Agri news RSS/API | Headlines + body for policy, export, fuel, commodity events | Hourly | Curated fixture of 20 events |
| EXT-05 | Anthropic Messages API | Orchestrator + assistant reasoning, tool use | Per request | None — required |
| EXT-06 | WhatsApp Cloud API | Outbound farmer notifications, inbound simple queries | Event-driven | In-app notification only |

Every external record ingested SHALL be stored with its `DataSource`, fetch timestamp and
raw payload, so that an `EvidenceSnapshot` can cite it (INV-2, INV-3).

---

## 4. Functional requirements

Priority: **MUST** (in the 72-hour build) · **SHOULD** (build if ahead of schedule) ·
**POST-MVP** (designed for, not built).

### 4.1 Organization & membership (FR-1xx)

| ID | Requirement | Priority |
|---|---|---|
| FR-101 | The system SHALL model a generic `Organization` with `type ∈ {FPO, PACS, SHG}`; all intelligence SHALL operate on `Organization`, not on an FPO-specific type. | MUST |
| FR-102 | The system SHALL support a farmer belonging to **multiple** organizations via a `Membership` entity carrying role, join date, status and share/patronage where applicable. | MUST |
| FR-103 | The system SHALL record organization resources — working capital, warehouses, cold storage, machinery, vehicles, processing units, input inventory — as constraints available to the orchestrator. Absent resources SHALL be represented as *unknown*, not as zero. | MUST |
| FR-104 | The system SHALL support a person holding multiple roles; permissions SHALL be evaluated as the union of role grants. | MUST |
| FR-105 | The system SHALL record organization announcements with an explicit `visibility ∈ {INTERNAL, SHARED_WITH_MEMBERS, PUBLIC}`; only `SHARED_WITH_MEMBERS`/`PUBLIC` cross the information boundary. | MUST |

### 4.2 Farmer, land and crop record (FR-2xx)

| ID | Requirement | Priority |
|---|---|---|
| FR-201 | The system SHALL maintain a farmer profile: identity, contact, language preference, location, household, memberships, land access, livestock, assets, water access, historical production, funding, schemes, sales, income outcomes. | MUST |
| FR-202 | The system SHALL model `Farm` (an operational grouping) containing one or more `Plot`s (the atomic cultivation unit) with area and, where available, a PostGIS boundary polygon. | MUST |
| FR-203 | The system SHALL separate **land ownership**, **cultivation responsibility** and **organization membership** as three distinct relationships, via a `PlotTenure` entity (`OWNED / LEASED / SHARECROPPED / JOINT / OTHER`, share %, validity period). | MUST |
| FR-204 | The system SHALL support multiple parties holding tenure on one plot simultaneously (joint/family/tenancy), with shares summing to 100% or flagged as a discrepancy. | MUST |
| FR-205 | The system SHALL model `CropCycle` as the central temporal entity: plot, crop, variety, season, sowing/transplant date, expected & actual harvest date, acreage, farming method, expected & actual yield, expected & actual quality, status. | MUST |
| FR-206 | A plot SHALL support many crop cycles over time; two cycles on one plot MAY overlap only when explicitly flagged as intercropping. | MUST |
| FR-207 | The system SHALL model integrated farming as `FarmResource` with `type ∈ {CROP, LIVESTOCK, POULTRY, FISHERY, COMPOST, MANURE, AGROFORESTRY, WATER, EQUIPMENT}` and directional `ResourceFlow` links between resources (e.g. livestock → manure → crop → residue → livestock). | MUST |
| FR-208 | The system SHALL support reasoning over `ResourceFlow` to propose on-farm substitution (e.g. available manure offsetting purchased fertilizer within the recommended nutrient plan). | POST-MVP |
| FR-209 | The system SHALL record crop-cycle inputs (seed, nutrient, crop protection, water, labour, energy) with quantity, cost in paise and source. | MUST |

### 4.3 Observations & provenance (FR-3xx)

| ID | Requirement | Priority |
|---|---|---|
| FR-301 | Every consequential value SHALL be stored as an append-only `Observation` carrying: subject, attribute, value, unit, `source_type ∈ {FIELD_OFFICER, FARMER_SELF_REPORT, AI_INFERENCE, EXTERNAL_SOURCE, ORG_RECORD}`, source reference, `observed_at`, `recorded_at`, `confidence ∈ [0,1]`, `verification_status ∈ {UNVERIFIED, VERIFIED, DISPUTED, SUPERSEDED}`. | MUST |
| FR-302 | The system SHALL compute a **current value** per (subject, attribute) as the highest-trust, freshest non-superseded observation, and SHALL expose the full observation history. | MUST |
| FR-303 | Observation confidence SHALL decay with age using a per-attribute half-life (e.g. crop health 7 days, plot area 365 days); the decayed value is the confidence used by intelligence modules. | MUST |
| FR-304 | When two observations of the same (subject, attribute) differ beyond a per-attribute tolerance, the system SHALL create a `DataDiscrepancy` recording every claimed value with its source, SHALL surface it at the point of use, SHALL lower the effective confidence, and SHALL raise a verification task. It SHALL NOT silently pick a winner. | MUST |
| FR-305 | Resolving a discrepancy SHALL require a human with verification authority and SHALL be recorded with actor, timestamp and rationale. | MUST |
| FR-306 | The system SHALL mark an observation `STALE` (a UI state, not a value change) when its age exceeds the attribute's staleness threshold, and SHALL exclude stale observations from high-confidence claims. | MUST |
| FR-307 | Every value rendered in the UI or cited in a Decision Packet SHALL be traceable to its observations in one navigation step. | MUST |

### 4.4 External intelligence ingestion (FR-4xx)

| ID | Requirement | Priority |
|---|---|---|
| FR-401 | The system SHALL ingest weather forecast and history per plot/district and store it as external observations. | MUST |
| FR-402 | The system SHALL ingest mandi price and arrival data per commodity and market, retaining at least 24 months of history for trend and volatility computation. | MUST |
| FR-403 | The system SHALL ingest government scheme definitions with eligibility criteria expressed as machine-evaluable rules plus the original text, and SHALL embed the text for retrieval. | MUST |
| FR-404 | The system SHALL ingest agricultural news/policy events and classify them by domain (POLICY, CLIMATE, MARKET, SUPPLY_CHAIN, GLOBAL, INPUT_PRICE). Satisfied by the UP शासनादेश stream (ADR-0018): classification is deterministic, and the event's *magnitude* is out of scope because the order listing carries a subject line, not the order text. | MUST |
| FR-405 | The system SHALL retain the raw payload and fetch timestamp of every external record for evidence citation. | MUST |
| FR-406 | Where a live source is unavailable, the system SHALL fall back to a fixture and SHALL mark all derived values as `FIXTURE` provenance, visible in the UI. | MUST |

### 4.5 Intelligence modules (FR-5xx)

Common contract — see `docs/ARCHITECTURE.md#module-contract`:

| ID | Requirement | Priority |
|---|---|---|
| FR-500 | Each intelligence module SHALL be a **pure function** `(ModuleInput) → ModuleOutput`, performing no I/O, and SHALL return findings each carrying `confidence`, `evidence[]` and `assumptions[]`. | MUST |

**Farm Intelligence**

| ID | Requirement | Priority |
|---|---|---|
| FR-511 | SHALL summarize per-plot crop status, stage, and resource constraints (land, water, capital, labour). | MUST |
| FR-512 | SHALL compute expected farm income per unit of land, water and capital, and rank crop-cycle options by that measure rather than by yield. | MUST |
| FR-513 | SHALL propose farm-level composition (e.g. 2 ac wheat + 0.5 ac vegetables + 0.5 ac fodder + livestock integration) rather than a single crop. | SHOULD |

**Crop Health Intelligence**

| ID | Requirement | Priority |
|---|---|---|
| FR-521 | SHALL accept a crop-health observation (field-officer score, symptom checklist, or farmer photo) and produce a health assessment with severity and spread risk conditioned on weather. | MUST |
| FR-522 | SHALL produce an **action plan**, not a label: immediate action → farm-management change → biological/IPM option → chemical option (class + label caution) → monitoring interval. | MUST |
| FR-523 | SHALL rank protection options by effectiveness, cost, environmental impact and resistance risk, defaulting to preventive/biological and escalating to chemical only where severity and spread risk justify it. | MUST |
| FR-524 | When top-candidate probabilities are within a configured margin (default 15 points), the system SHALL NOT assert a diagnosis; it SHALL request a better photo or additional symptoms, give the conservative action that is safe under all candidates, and recommend expert consultation. | MUST |
| FR-525 | SHALL detect geographic/temporal clustering of similar symptoms across the membership and raise an outbreak signal to the FPO with affected plots and area. | SHOULD |
| FR-526 | Image-based classification SHALL be an explicitly labelled assistive signal, never the sole basis for a chemical recommendation. | MUST |

**Quality Intelligence**

| ID | Requirement | Priority |
|---|---|---|
| FR-531 | SHALL predict, before harvest, expected quantity, expected quality grade distribution and harvest window per crop cycle, with confidence. | MUST |
| FR-532 | SHALL aggregate predictions to the organization level (e.g. "Rice: Grade A 850 t, Grade B 420 t, Grade C 130 t, window 10–25 Nov"). | MUST |
| FR-533 | SHALL identify crop cycles at risk of falling a grade and the intervention that could prevent it, before harvest. | MUST |
| FR-534 | SHALL record predicted vs actual quantity and grade at harvest as a learning signal, and SHALL expose prediction error per model version. | MUST |

**Market Intelligence**

| ID | Requirement | Priority |
|---|---|---|
| FR-541 | SHALL maintain buyer records: required quantity, price offered, quality requirement, delivery window, location, payment terms, historical reliability. | MUST |
| FR-542 | SHALL compute **Effective Price** = buyer price − logistics − handling − expected quality loss − other transaction costs − storage − financing cost, per buyer per lot. | MUST |
| FR-543 | SHALL compute a **Transaction Attractiveness Score** combining effective price, payment-delay cost, rejection probability, minimum-quantity fit, distance and buyer reliability, and SHALL show the component breakdown. | MUST |
| FR-544 | SHALL recommend a primary buyer **plus ranked alternatives** and a **negotiation brief** stating the asking price and the evidence supporting it. | MUST |
| FR-545 | SHALL propose lot-level allocation across buyers and storage subject to quantity, quality and capacity constraints (e.g. 500 t → Buyer A, 220 t → storage). | MUST |
| FR-546 | Buyer matching results SHALL be visible to both the FPO and the farmers whose lots are involved. | MUST |
| FR-547 | SHALL compare expected price for selling now vs. holding, including storage and financing cost, and state the break-even holding period. | SHOULD |
| FR-548 | SHALL detect aggregate supply/demand mismatch for the coming season and quantify the gap (e.g. expected 1,300 t vs demand 800 t → ~500 t oversupply). | SHOULD |

**Risk Intelligence**

| ID | Requirement | Priority |
|---|---|---|
| FR-551 | SHALL evaluate risk across seven domains: climate, weather, crop health, market, policy, supply chain, global. | MUST |
| FR-552 | SHALL maintain an organization **Risk Register**: risk, domain, probability, impact, farmers affected, area affected, recommended action, owner, status, review date. | MUST |
| FR-553 | SHALL, for a news/policy event, produce an explicit **causal chain** to organization-specific impact and a recommended action — e.g. *fuel price ↑ → logistics cost ↑ → distant buyer effective price ↓ → nearby buyer becomes competitive → revisit buyer allocation*. | MUST |
| FR-554 | SHALL quantify exposure for each event (tonnes, farmers, acres, ₹ at risk) rather than reporting the event alone. | MUST |
| FR-555 | SHALL express recommendations as **risk-adjusted** outcomes, presenting at least two strategies with their expected value and risk, and SHALL prefer the higher risk-adjusted option when risk is not manageable. | MUST |
| FR-556 | SHALL provide a monitoring watchlist of external indicators the FPO should track, with thresholds. | SHOULD |

**Scheme Intelligence**

| ID | Requirement | Priority |
|---|---|---|
| FR-561 | SHALL evaluate every member against every active scheme's eligibility rules and produce an `EligibilityAssessment` with status `{ELIGIBLE, LIKELY_ELIGIBLE, INSUFFICIENT_DATA, NOT_ELIGIBLE}`, the rules that passed/failed, and confidence. | MUST |
| FR-562 | SHALL aggregate to the organization level and quantify the opportunity — e.g. "₹18.4 lakh of accessible benefits currently unclaimed; 320 potentially eligible, 210 missing documents, 65 incomplete, 45 approved". | MUST |
| FR-563 | SHALL drill down from any aggregate to the identified farmers in that segment. | MUST |
| FR-564 | SHALL produce a per-farmer document-readiness checklist and track application status: DISCOVERED → ELIGIBLE → DOCUMENTS_PENDING → APPLIED → UNDER_REVIEW → APPROVED / REJECTED. | MUST |
| FR-565 | SHALL treat expected scheme benefit as an input to funding recommendations, reducing the required FPO contribution accordingly (e.g. ₹40,000 need = ₹10,000 subsidy + ₹30,000 FPO). | MUST |
| FR-566 | Sensitive eligibility attributes (caste/category, income, gender, disability) SHALL be optional, consent-gated, and used only for eligibility evaluation — never for prioritization, scoring or ranking of farmers. | MUST |
| FR-567 | The system SHALL NOT auto-submit any government application. | MUST |

### 4.6 Funding recommendation (FR-6xx)

| ID | Requirement | Priority |
|---|---|---|
| FR-601 | The system SHALL compute a per-farmer, per-crop-cycle **funding requirement** from the input plan, expected yield, expected revenue and expected scheme benefit, and SHALL show the arithmetic. | MUST |
| FR-602 | Allocation factors SHALL be limited to: land area, crop, crop health, historical farmer performance, water availability and soil condition, plus expected scheme benefit. Other factors require an explicit decision recorded in `context.md`. | MUST |
| FR-603 | The system SHALL present **Expected Farmer ROI** = expected incremental income ÷ FPO investment, with its inputs and confidence. | MUST |
| FR-604 | The system SHALL support Model C funding — inputs-in-kind plus working capital — as the default representation of an allocation. | MUST |
| FR-605 | The system SHALL NOT phrase any recommendation as withholding support from a named farmer. Where capital is constrained it SHALL express **sequencing and de-risking** (e.g. "fund in two tranches after a field verification") and SHALL state what would change the recommendation. | MUST |
| FR-606 | Every funding recommendation SHALL be labelled with its data sufficiency; where financial history is absent, the system SHALL say so rather than implying a credit assessment. | MUST |
| FR-607 | Portfolio-level capital optimization across the whole membership. | POST-MVP |

### 4.7 Prediction, recommendation and approval lifecycle (FR-7xx)

| ID | Requirement | Priority |
|---|---|---|
| FR-701 | `Prediction` and `Recommendation` SHALL be distinct entities with distinct lifecycles. A prediction is a claim about reality; a recommendation is a proposed action. | MUST |
| FR-702 | Every prediction SHALL record model/module identifier, version, inputs reference, value, unit, confidence, prediction horizon, and later the realized actual and error. | MUST |
| FR-703 | Every recommendation SHALL record: generator, target, type, reasoning, evidence, confidence, expected impact, risks, alternatives, status and approval chain. | MUST |
| FR-704 | Every recommendation SHALL, at generation time, persist an **immutable EvidenceSnapshot** of all inputs used (market, weather, demand, buyer, farmer/crop data, module outputs) with a SHA-256 content hash. Historical recommendations SHALL be explained from the snapshot, never recomputed from live data. | MUST |
| FR-705 | Recommendation status SHALL follow `SUGGESTED → REVIEWED → APPROVED → EXECUTED → OUTCOME_RECORDED`, with `REJECTED` and `SUPERSEDED` as terminal branches. Transitions SHALL be recorded with actor, timestamp, and rationale where the actor modified the recommendation. | MUST |
| FR-706 | An approver SHALL be able to approve, reject, or **approve with modification** (e.g. AI suggested ₹35,000; CEO approves ₹32,000); the modification SHALL be recorded as a distinct field, not by overwriting the recommendation. | MUST |
| FR-707 | No code path SHALL transition a recommendation to `EXECUTED` without a persisted `Approval` by a user holding approval authority for that recommendation type. | MUST |
| FR-708 | When new material data would change an approved recommendation, the system SHALL emit `RecommendationSuperseded`, create a new recommendation, and flag the prior decision for review. It SHALL NOT mutate the approved record. | MUST |
| FR-709 | The system SHALL maintain an immutable `AuditRecord` for every consequential event: who, what, when, on what evidence, with what authority. | MUST |
| FR-710 | The system SHALL be able to render, for any past decision, the exact state it was based on ("Why did the AI recommend Buyer A on 22 August?"). | MUST |

### 4.8 Orchestrator & assistants (FR-8xx)

| ID | Requirement | Priority |
|---|---|---|
| FR-801 | The orchestrator SHALL gather module outputs, reconcile them, and emit a **Decision Packet** with exactly nine sections in fixed order: Situation, Impact, Recommendation, Expected outcome, Confidence, Evidence, Actions, Schedule, Drill-down. | MUST |
| FR-802 | The orchestrator SHALL be able to override a single module's finding when cross-domain evidence materially changes the decision, and SHALL state the override and its reason explicitly in the packet. | MUST |
| FR-803 | The Decision Packet SHALL be produced as structured JSON via tool use against a fixed schema; free-text parsing is prohibited. | MUST |
| FR-804 | Every claim in a Decision Packet SHALL carry at least one `EvidenceRef` resolvable to an observation, external record or module output. Claims without evidence SHALL be dropped, not rendered. | MUST |
| FR-805 | The **Actions** section SHALL name a role, a task and a due date for each action. | MUST |
| FR-806 | The **Drill-down** section SHALL resolve to concrete farmer/plot/crop-cycle/buyer identifiers, navigable in the UI. | MUST |
| FR-807 | The **FPO Assistant** SHALL answer organization-scoped questions and SHALL support drill-down to individual farmers. | MUST |
| FR-808 | The **Farmer Assistant** SHALL answer only within that farmer's own data plus information officially shared by the organization. | MUST |
| FR-809 | The information boundary SHALL be enforced in the data-access layer by context scope, not by prompt instruction. A prompt-level leak SHALL be impossible because the data never enters the context. | MUST |
| FR-810 | The Farmer Assistant SHALL surface organization decisions that are officially shared and relevant (e.g. "your FPO has secured fertilizer at a collective price; your recommended requirement is X"). | MUST |
| FR-811 | The system SHALL produce a proactive **morning briefing** for the FPO CEO: the N items requiring attention, each with quantified impact, plus a recommended priority order. | MUST |
| FR-812 | Assistants SHALL respond in the user's selected language (Hindi or English) without loss of numeric precision or units. | MUST |
| FR-813 | When the orchestrator's confidence is below a configured floor, it SHALL say so and recommend what data would raise it, rather than producing a confident-sounding answer. | MUST |
| FR-814 | An assistant question SHALL be classified into one of four response shapes — `DECISION`, `LOOKUP`, `EXPLAIN`, `REFUSE` — and answered in that shape. Only `DECISION` freezes an `EvidenceSnapshot` and writes `Recommendation` rows; a question that asks what is true SHALL NOT produce either. | MUST |
| FR-815 | `LOOKUP` and `EXPLAIN` answers SHALL be composed of the same evidenced `Claim` type as a Decision Packet, so FR-804 applies unchanged to every response shape. | MUST |
| FR-816 | Question classification SHALL draw only from a closed vocabulary of named lookups and registered modules, filtered by the asker's audience. A classification outside that vocabulary SHALL be rejected and the deterministic keyword planner used instead — the information boundary SHALL NOT depend on model behaviour (INV-5). | MUST |
| FR-817 | Before rendering, an answer SHALL be checked deterministically: every magnitude and evidence reference SHALL resolve to the result that produced it, or the reviewed output SHALL be discarded in favour of the unreviewed one. | MUST |
| FR-818 | A relevance pass MAY select and order the sections of an answer. It SHALL NOT rewrite or delete content, and SHALL NOT drop the situation, recommendation, evidence, confidence or override sections (FR-802, INV-8). | MUST |
| FR-819 | A follow-up question about a previous answer SHALL be answered from that answer's frozen `EvidenceSnapshot`, never by re-running the orchestrator (INV-2). | MUST |
| FR-820 | Every assistant turn SHALL be recorded — question, classification, shape and outcome — whatever shape it took, not only those producing a Decision Packet (FR-709). | MUST |
| FR-821 | With no language model reachable, the assistant SHALL remain functional: keyword routing, unfiltered rendering, and every response shape except model-classified ones still available (NFR-303). | MUST |

### 4.9 Calendar & tasks (FR-9xx)

| ID | Requirement | Priority |
|---|---|---|
| FR-901 | The system SHALL maintain a unified `CalendarEvent` store scoped per subject (farmer, plot, crop cycle, organization) with `origin ∈ {MANUAL, AUTO_GENERATED, AI_RECOMMENDED, OFFICIAL_DEADLINE}`. | MUST |
| FR-902 | Any user with a legitimate relationship to the subject (farmer, FPO staff) SHALL be able to add a manual event. | MUST |
| FR-903 | The system SHALL auto-generate an agronomic schedule from a crop cycle (e.g. rice transplanted 15 Jul → irrigation check 18 Jul → health inspection 25 Jul → preventive action 30 Jul → nutrient assessment 8 Aug). | MUST |
| FR-904 | Auto-generated and AI-recommended consequential events SHALL be `PENDING_APPROVAL` until approved by the responsible human (field officer role, held by the FPO CEO in MVP). | MUST |
| FR-905 | The calendar SHALL merge farm, organization, scheme-deadline, risk-window and market-window events into the viewer's scoped view. | MUST |
| FR-906 | Approved events SHALL generate `Task`s with an assignee role and SHALL feed the intervention record when completed. | MUST |

### 4.10 Outcome, attribution & learning (FR-10xx)

| ID | Requirement | Priority |
|---|---|---|
| FR-1001 | The system SHALL record an `Intervention` for each executed action: what was done, when, by whom, cost, and its originating recommendation. | MUST |
| FR-1002 | Each intervention SHALL record **adherence**: `followed ∈ {YES, PARTIAL, NO, UNKNOWN}`, `fidelity ∈ [0,1]`, deviation notes and delay in days. | MUST |
| FR-1003 | The system SHALL record an `Outcome` with baseline, observed result, timestamp and the external conditions prevailing over the period. | MUST |
| FR-1004 | The system SHALL compute an `Attribution` with strength `{HIGH, MODERATE, UNCERTAIN, CONFOUNDED}` and an explicit list of confounders; attribution SHALL NOT be computed when adherence is `UNKNOWN`. | MUST |
| FR-1005 | The system SHALL surface per-module prediction accuracy and per-recommendation-type outcome statistics over time. | SHOULD |
| FR-1006 | Model/module retraining or coefficient adjustment from accumulated outcomes. | POST-MVP |

### 4.11 Consent, privacy and data governance (FR-11xx)

| ID | Requirement | Priority |
|---|---|---|
| FR-1101 | Farmers SHALL own their data. Consent SHALL be captured per purpose (`SERVICE_DELIVERY`, `ORG_ANALYTICS`, `MODEL_IMPROVEMENT`, `ANONYMIZED_RESEARCH`), be revocable, and be recorded with timestamp and version of the consent text. | MUST |
| FR-1102 | Revoking a consent SHALL stop the corresponding processing prospectively and SHALL be reflected in dataset generation. | MUST |
| FR-1103 | Research datasets SHALL be anonymized and aggregated, with k-anonymity ≥ 5 on any released cut, and SHALL exclude any farmer who has not consented to `ANONYMIZED_RESEARCH`. | SHOULD |
| FR-1104 | Revenue derived from data SHALL be routed to an ecosystem fund benefiting participating farmers and organizations (Model C); the platform SHALL NOT retain it as pure margin. | POST-MVP (policy fixed now) |
| FR-1105 | Sensitive attributes SHALL be encrypted at rest and access-logged. | SHOULD |
| FR-1106 | The system SHALL support export of a farmer's own data on request. | SHOULD |

### 4.12 Impact reporting (FR-12xx)

| ID | Requirement | Priority |
|---|---|---|
| FR-1201 | The system SHALL report five public-good impact metrics: farmer income, employment, government-benefit access, food production, supply-chain efficiency. | MUST |
| FR-1202 | Each metric SHALL declare whether it is **measured**, **estimated** or a **proxy**, and SHALL show its formula. Estimates SHALL never be presented as measurements. | MUST |
| FR-1203 | Impact SHALL be reported against a stated baseline and period. | MUST |

---

## 5. Data requirements

Full specification in `docs/DATA-MODEL.md`. Requirements-level constraints:

| ID | Requirement |
|---|---|
| DR-01 | Primary keys are UUIDv7. No sequential integers, no natural keys. |
| DR-02 | Money is `BIGINT` paise. Area is `NUMERIC` square metres. Mass is `NUMERIC` kilograms. Price is paise per kilogram. Never floats for money. |
| DR-03 | All timestamps are `TIMESTAMPTZ` in UTC; the UI renders `Asia/Kolkata`. |
| DR-04 | `Observation`, `Prediction`, `Recommendation`, `EvidenceSnapshot`, `AuditRecord`, `DomainEvent` are **append-only**. Correction is a new row plus supersession, never an UPDATE or DELETE. |
| DR-05 | Every domain-state change writes a `DomainEvent` to a transactional outbox in the same transaction. |
| DR-06 | Plot boundaries use PostGIS `geography(Polygon, 4326)`; centroids are indexed for weather join. |
| DR-07 | Scheme and news text is embedded with pgvector for retrieval; the raw text is retained. Retrieval is hybrid — pgvector plus Postgres full-text, fused by rank — and degrades to lexical-only when no encoder is installed, so NFR-303 still holds (ADR-0018). |
| DR-08 | Retention: raw external payloads 12 months; observations, decisions and audit records indefinitely. |
| DR-09 | Seed data SHALL be deterministic given a fixed random seed, so that the demo is reproducible. |

---

## 6. Non-functional requirements

### 6.1 Performance

| ID | Requirement |
|---|---|
| NFR-101 | The FPO dashboard SHALL render for a 1,000-farmer organization in ≤2 s (p95) on a warm cache. |
| NFR-102 | A Decision Packet SHALL begin streaming within 5 s and complete within 30 s (p95). |
| NFR-103 | Drill-down from an aggregate to the affected farmer list SHALL complete in ≤1 s for ≤2,000 rows. |
| NFR-104 | Nightly recomputation of eligibility and risk across 1,000 farmers SHALL complete in ≤10 minutes. |

### 6.2 Scalability

| ID | Requirement |
|---|---|
| NFR-201 | The design SHALL support 30 organizations × 2,000 farmers × 5 seasons without schema change. |
| NFR-202 | Intelligence modules SHALL be independently invocable and horizontally scalable (pure functions, no shared state). |

### 6.3 Reliability & availability

| ID | Requirement |
|---|---|
| NFR-301 | Failure of any single external source SHALL degrade the affected module's confidence and state the degradation — never fail the whole Decision Packet. |
| NFR-302 | LLM call failures SHALL be retried with backoff; on exhaustion the system SHALL return the deterministic module outputs without narrative synthesis rather than an error page. |
| NFR-303 | The demo path SHALL be reproducible from `make seed && make dev` with no network access, using fixtures. |
| NFR-304 | A translation failure (no key, provider error, timeout) SHALL leave the affected text in its source language — never blank, never an error page. Anonymous callers SHALL be served from the translation memory only and SHALL NOT spend provider calls (ADR-0023). |

### 6.4 Security

| ID | Requirement |
|---|---|
| NFR-401 | Authorization SHALL be enforced server-side on every request against the actor's roles and organization scope. |
| NFR-402 | Row-level scoping SHALL be applied in the repository layer; no endpoint may accept a client-supplied `org_id` as the authorization basis. |
| NFR-403 | Secrets SHALL come from the environment; none in the repository. |
| NFR-404 | All sensitive-attribute reads SHALL be access-logged with actor and purpose. |
| NFR-405 | Farmer-supplied text and images SHALL be treated as untrusted input to the LLM; prompt-injection defences SHALL prevent farmer-supplied content from altering orchestrator instructions or crossing the information boundary. |

### 6.5 Usability & accessibility

| ID | Requirement |
|---|---|
| NFR-501 | Farmer-facing screens SHALL meet WCAG 2.1 AA contrast and target sizes. |
| NFR-502 | Farmer-facing content SHALL be available in Hindi and English; no untranslated English fragments in the Hindi view. |
| NFR-503 | Farmer-facing pages SHALL be usable on a 3G connection: initial payload ≤200 KB gzipped for the daily-actions view. |
| NFR-504 | Numbers SHALL be formatted in the Indian numbering system (lakh/crore) in Hindi views. |
| NFR-505 | Switching back to a language already shown on the page SHALL NOT make a network call, and a string translated once SHALL be served from memory thereafter (UI-11). |

### 6.6 Maintainability & observability

| ID | Requirement |
|---|---|
| NFR-601 | `domain/` and `intelligence/` SHALL pass `mypy --strict`. |
| NFR-602 | Every intelligence module SHALL have golden-file tests over the seeded scenarios. |
| NFR-603 | Every LLM call SHALL be logged with prompt version, model id, token usage, latency and the resulting packet id. |
| NFR-604 | Prompts SHALL be versioned files, and the version SHALL be recorded on every recommendation. |

---

## 7. Trust, safety and ethics requirements

| ID | Requirement |
|---|---|
| SAF-01 | **No autonomous consequential action.** AI recommends; a human approves; the system executes. (INV-1) |
| SAF-02 | **Diagnostic humility.** When candidate diagnoses are within the confidence margin, the system asks for more information and gives the action that is safe under all candidates. It does not guess. (FR-524) |
| SAF-03 | **Chemical guidance floor.** Crop protection is IPM-first. Chemical output is a class/option with an explicit instruction to follow the product label and consult a local agronomist. Exact product + dosage is given only where a cited authoritative source supports it, and is always shown with its citation. (INV-8) |
| SAF-04 | **No harmful framing about people.** The system never recommends withholding support from a named farmer, never ranks farmers by a "worth investing in" score, and never uses sensitive attributes for prioritization. (FR-605, FR-566) |
| SAF-05 | **Market predictions are ranges.** Price guidance is a range with confidence, historical trend and a downside scenario — never a point forecast presented as fact. |
| SAF-06 | **Uncertainty is stated, not hidden.** Low-confidence answers say what data would improve them. (FR-813) |
| SAF-07 | **Synthetic data is labelled** everywhere it appears, including in exported reports and screenshots. (UI-04) |
| SAF-08 | **Consent is real.** Per-purpose, revocable, versioned, and enforced in dataset generation. (FR-1101) |
| SAF-09 | **Value flows back.** Data-derived revenue goes to an ecosystem fund, not to platform margin. (FR-1104) |
| SAF-10 | **Auditability is a farmer protection.** The decision trail exists so a farmer can contest an FPO decision that affected them, not only so the FPO can defend itself. (FR-709) |
| SAF-11 | **No government application is auto-submitted.** (FR-567) |
| SAF-12 | **Attribution honesty.** The system does not claim credit for outcomes it cannot attribute; `CONFOUNDED` is a valid and expected result. (FR-1004) |

---

## 8. Acceptance criteria

### 8.1 Demo acceptance — the killer moment

The build is accepted when this sequence runs end to end on seeded data:

1. FPO CEO opens the console and sees the 10-card dashboard for a 1,000-farmer organization,
   with a morning briefing listing N items needing attention in priority order. *(UI-01, FR-811)*
2. CEO asks, in Hindi or English: **"What should we do this season to maximize sustainable
   farmer income?"** *(FR-807, FR-812)*
3. The system returns a Decision Packet with all nine sections, every claim evidence-backed:
   *(FR-801, FR-804)*
   - **Situation** — 1,000 farmers, 2,412 acres, 5 crops, expected production by grade and window
   - **Opportunity** — demand for Crop X up 18%, with the source cited
   - **Risk** — weather creating elevated risk for Crop Y
   - **Impact** — 312 farmers / 740 acres exposed, ₹ at risk quantified
   - **Recommendation** — secure Buyer A for X; prioritize intervention on the exposed farms;
     redirect procurement toward X inputs; revisit Y's selling strategy
   - **Expected outcome**, **Confidence: 82%**, **Evidence: 7 verified datasets + 3 external sources**
   - **Actions** — role-assigned with due dates
   - **Schedule** — calendar events, pending approval
4. At least one **cross-domain override** is visible and explained (the crop module's preference
   overridden by market + weather evidence). *(FR-802)*
5. CEO clicks **"Show affected farmers"** and drills 312 farmers → 740 acres → individual plots
   → crop health → interventions → schedules. *(FR-806, NFR-103)*
6. CEO **approves with modification** (changes one allocation figure); the modification is
   recorded distinctly and the original recommendation is unchanged. *(FR-706)*
7. Approved actions generate tasks and calendar events; the affected farmers see **only** the
   information officially shared with them in the farmer portal. *(FR-906, FR-808, FR-809)*
8. A farmer opens the portal in Hindi, asks by voice what to do this week, and receives their
   own scoped plan. *(UI-05, UI-06, FR-808)*
9. An outcome is recorded for a past recommendation with adherence, and an attribution is
   computed showing `MODERATE` strength with named confounders. *(FR-1002, FR-1004)*
10. The judge asks *"why did it say that?"* — the frozen EvidenceSnapshot renders the exact
    inputs as of generation time. *(FR-704, FR-710)*

### 8.2 Invariant acceptance tests

| Test | Asserts |
|---|---|
| `test_no_execution_without_approval` | Attempting `EXECUTED` without an `Approval` raises and writes nothing. (INV-1) |
| `test_evidence_snapshot_immutable` | Snapshot hash is stable; UPDATE on the table is rejected. (INV-2) |
| `test_module_rejects_unprovenanced_value` | A value without provenance cannot enter a module. (INV-3) |
| `test_conflicting_sources_create_discrepancy` | Two divergent observations produce a `DataDiscrepancy` and lower confidence; neither is silently chosen. (INV-4) |
| `test_farmer_context_excludes_org_internal` | The farmer assistant's retrieved context contains zero rows marked `INTERNAL`, and zero rows belonging to another farmer. (INV-5) |
| `test_prediction_and_recommendation_separate` | A prediction cannot be approved; a recommendation cannot be scored for accuracy. (INV-6) |
| `test_attribution_requires_adherence` | Attribution with `adherence=UNKNOWN` is refused. (INV-7) |
| `test_chemical_recommendation_has_citation_or_caution` | Any chemical option carries a citation or the label-and-agronomist caution. (INV-8) |
| `test_superseded_not_mutated` | New data creates a new recommendation; the approved row is byte-identical. (INV-10) |

---

## 9. Traceability

### 9.1 Discovery decision → requirement

| Decision (context.md) | Requirements |
|---|---|
| D-01 FPO-centric | FR-101, FR-807, UI-01 |
| D-02 FPO + PACS + SHG | FR-101, FR-102 |
| D-03 Market + Risk are the heroes | FR-541…FR-548, FR-551…FR-556 |
| D-04 Individual-level data, aggregate view | FR-205, FR-532, FR-806 |
| D-05 Advisory, not coordinated production | FR-703, FR-805, SAF-01 |
| D-06 ROI objective | FR-603 |
| D-07 Risk-adjusted | FR-555 |
| D-08 Recommend + explain, human approves | FR-703, FR-705, FR-707 |
| D-09 Never "don't invest in this farmer" | FR-605, SAF-04 |
| D-10 Audit trail | FR-709, FR-710, SAF-10 |
| D-11 Effective price | FR-542 |
| D-12 Alternatives + negotiation brief | FR-544 |
| D-13 News causal chain | FR-553, FR-554 |
| D-14 IPM-first | FR-522, FR-523, SAF-03 |
| D-15 Integrated farming first-class | FR-207, FR-208, FR-512, FR-513 |
| D-16 Quality predicted pre-harvest | FR-531…FR-534 |
| D-17 Lot matching visible to both | FR-546 |
| D-18 Provenance everywhere | FR-301…FR-307 |
| D-19 Show discrepancy, don't resolve silently | FR-304, FR-305 |
| D-20 Unified scoped calendar with approval | FR-901…FR-906 |
| D-21 Shallow finance for MVP | FR-601…FR-606, FR-607 |
| D-22 Ecosystem fund | FR-1104, SAF-09 |
| D-23 Five impact metrics | FR-1201…FR-1203 |

### 9.2 Invariant → requirement

| Invariant | Requirements |
|---|---|
| INV-1 human-in-the-loop | FR-705, FR-707, FR-904, SAF-01 |
| INV-2 frozen evidence | FR-704, FR-710 |
| INV-3 provenance | FR-301…FR-307, FR-500 |
| INV-4 conflicts surface | FR-304, FR-305, UI-10 |
| INV-5 information boundary | FR-105, FR-808, FR-809 |
| INV-6 prediction ≠ recommendation | FR-701, FR-702 |
| INV-7 adherence recorded | FR-1002, FR-1004 |
| INV-8 chemical safety floor | FR-522…FR-526, SAF-03 |
| INV-9 farmer owns data | FR-1101…FR-1106, SAF-08 |
| INV-10 reversible & re-evaluated | FR-708 |
