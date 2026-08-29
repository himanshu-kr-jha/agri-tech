# Architecture — AgriVardhak

Version 1.0 · 2026-08-22

---

## 1. The eight layers

The layer model was agreed during discovery and is the system's organizing principle.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ L1  INGESTION                                                            │
│  FPO staff entry · farmer self-report · WhatsApp · voice · field forms    │
│  external adapters: weather · mandi · scheme · news · buyer demand        │
└───────────────────────────────┬──────────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ L2  PROVENANCE & RECONCILIATION                                          │
│  Observation write · trust weighting · confidence decay                  │
│  discrepancy detection · staleness · current-value resolution            │
└───────────────────────────────┬──────────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ L3  DOMAIN MODEL  (the collective's digital twin)                        │
│  Organization → Membership → Farmer → Farm → Plot → CropCycle            │
│  FarmResource ⇄ ResourceFlow · Lot · Buyer · Scheme · Calendar           │
└───────────────────────────────┬──────────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ L4  INTELLIGENCE MODULES   (deterministic, pure functions)               │
│  Farm · Crop Health · Quality · Market · Risk · Scheme  [ · Funding ]    │
└───────────────────────────────┬──────────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ L5  ORCHESTRATOR   (LLM)                                                 │
│  reconcile · cross-domain override · prioritize · synthesize             │
│  → DecisionPacket (structured, evidence-bound)                           │
└───────────────────────────────┬──────────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ L6  DECISION & APPROVAL                                                  │
│  SUGGESTED → REVIEWED → APPROVED → EXECUTED    · EvidenceSnapshot frozen │
└───────────────────────────────┬──────────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ L7  EXECUTION                                                            │
│  tasks · calendar events · farmer notifications · procurement records    │
│  negotiation briefs · scheme application packets                         │
└───────────────────────────────┬──────────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ L8  OUTCOME & LEARNING                                                   │
│  intervention adherence · outcome · attribution · prediction error       │
│  (POST-MVP) anonymized research datasets                                 │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │
                                └──────────▶ feeds back into L2/L4
```

**The load-bearing idea:** L4 is deterministic and L5 is the only place an LLM makes a
judgement. Modules compute; the LLM reconciles and narrates. That is what makes every number
in a Decision Packet reproducible and every recommendation defensible.

---

## 2. Deployment topology

```
                    ┌───────────────────────┐
  Browser ─────────▶│  Next.js 16 (node)    │  SSR, RSC, auth session
  (FPO / farmer)    │  :3000                │
                    └───────────┬───────────┘
                                │ REST + SSE, JWT bearer
                    ┌───────────▼───────────┐
  WhatsApp webhook ▶│  FastAPI  :8000       │  routers · orchestrator · modules
                    │  APScheduler workers  │  ingestion · nightly recompute · outbox
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐        ┌──────────────────┐
                    │ PostgreSQL 16         │        │ Anthropic API    │
                    │ + PostGIS + pgvector  │        │ (orchestrator,   │
                    │ relational · geo ·    │        │  assistants)     │
                    │ embeddings · outbox   │        └──────────────────┘
                    └───────────────────────┘
```

The web tier never touches the database. All reads and writes go through the FastAPI API so
that authorization, provenance and the information boundary have exactly one enforcement point.

### Hosted (pilot)

The diagram above is the process topology; it says nothing about hosts, and for a pilot the two
diverge. Each tier is hosted separately, and the arrow from the browser to the database is still
absent — deliberately, even though the managed Postgres would make it trivial (ADR-0018).

```
  Browser ──HTTPS──▶ Vercel            apps/web, Next.js 16
                     (session cookie set by its own route handler)
             │
             └──HTTPS, Bearer JWT──▶ Render           FastAPI, Docker, built from the REPO ROOT
                                     Singapore        ships seed/generated/ — ingestion reads it
                                        │             at runtime via parents[4]
                                        │
                                        └──Postgres wire, Supavisor session pooler :5432──▶
                                           Supabase   Postgres + PostGIS + pgvector
                                           Singapore  schema owned by Alembic, not the dashboard
```

Three things about this arrangement are load-bearing rather than incidental:

- **No Supabase key ever reaches Vercel.** The managed database offers direct browser access; taking
  it would move the INV-5 information boundary into RLS policies and client code. FastAPI stays the
  only tier with a connection string (ADR-0001).
- **Extensions and `uuid_generate_v7()` come from a base migration**, not from
  `infra/initdb/01-extensions.sql`, which only ever runs under Docker. `alembic upgrade head` is
  sufficient on any empty Postgres. Because the managed host installs extensions into an
  `extensions` schema and Docker leaves them in `public`, both the runtime engine and Alembic
  connect with `search_path = public, extensions` from one constant — as a libpq connection option,
  never as a `SET` statement (`db/base.py:SEARCH_PATH_OPTION` records why).
- **Deploy migrates, it never seeds.** Render's pre-deploy command is `alembic upgrade head`.
  `make seed` is a one-time hand-run bootstrap and `make seed-reset` truncates every table, so
  neither belongs in a deploy hook.

Render and Supabase share a region because the orchestrator makes many database round trips per
decision packet against a browser's one. Full runbook:
`docs/superpowers/specs/2026-08-29-supabase-vercel-render-deployment-design.md`.

---

## 3. The module contract {#module-contract}

Every intelligence module is a pure function. No I/O, no clock, no network, no DB.

```python
class EvidenceRef(BaseModel):
    kind: Literal["observation", "external_record", "prediction", "domain_row"]
    id: UUID
    label: str                     # human-readable, rendered in the Evidence section
    as_of: datetime

class Finding(BaseModel):
    key: str                       # stable identifier, e.g. "oversupply_risk.potato"
    statement: str                 # one sentence, no hedging, no narrative
    magnitude: Decimal | None
    unit: str | None
    confidence: float              # 0..1, already provenance-adjusted
    evidence: list[EvidenceRef]    # non-empty, always
    assumptions: list[str]
    affected: AffectedSet          # farmer_ids, plot_ids, crop_cycle_ids, area_sqm, value_paise

class ModuleOutput(BaseModel):
    module: str
    version: str                   # bumped on any formula change; recorded on recommendations
    findings: list[Finding]
    proposed_actions: list[ProposedAction]
    degraded_inputs: list[str]     # sources that were stale/missing; drives NFR-301

def run(inputs: ModuleInput) -> ModuleOutput: ...
```

Consequences of purity that we depend on:
- A module can be **replayed against an `EvidenceSnapshot`** to reproduce a historical answer.
- Golden-file tests are trivial (NFR-602).
- Modules run concurrently; the orchestrator gathers all inputs once.
- A missing external source degrades one module's confidence, not the whole request (NFR-301).

---

## 4. The six modules

### 4.1 Farm Intelligence
**In:** plots, tenures, crop cycles, farm resources, resource flows, water availability, soil,
capital constraints.
**Out:** per-plot status; expected income per m², per litre of water, per rupee of capital;
farm-composition options; binding constraints.

```
income_per_m2     = expected_revenue_paise / plot_area_sqm
income_per_litre  = expected_revenue_paise / expected_water_litres
income_per_rupee  = expected_incremental_income_paise / expected_input_cost_paise
```
Ranks options on `income_per_rupee` first (D-06), breaking ties on water efficiency.

### 4.2 Crop Health Intelligence
**In:** health observations, symptom checklists, images (assistive), weather (humidity, rain,
temperature), crop stage, variety susceptibility, intervention history.
**Out:** severity, spread risk, an **action plan**, monitoring interval, outbreak clustering.

Action plan is always ordered and always complete:
```
1. Immediate action        (remove affected leaves, isolate)
2. Farm management         (irrigation timing, ventilation, spacing)
3. Biological / IPM        (named option, mechanism, expected onset)
4. Chemical                (class + label caution + agronomist consult)   ← gated
5. Monitoring              (recheck in N hours/days, what to look for)
```
Chemical is emitted only when `severity ≥ threshold AND spread_risk ≥ threshold AND
diagnostic_confidence ≥ margin`; otherwise steps 1–3 and 5 only (INV-8, FR-522…FR-524).

Diagnostic humility: if `p(top1) − p(top2) < 0.15`, no diagnosis is asserted. The module
returns the intersection of safe actions across candidates plus a request for better input.

### 4.3 Quality Intelligence
**In:** crop health trajectory, variety grade potential, weather during grain fill / maturation,
input adequacy, historical grade outcomes for this variety in this zone.
**Out:** expected quantity ± band, grade distribution, harvest window, at-risk cycles with the
intervention that could save a grade.

```
expected_yield_kg   = base_yield(variety, zone) × health_factor × water_factor
                      × nutrient_factor × stress_factor × area_ha
grade_distribution  = f(health_trajectory, weather_stress_index, input_adequacy)
harvest_window      = sowing_date + duration(variety) ± f(accumulated_GDD, stress)
```
Every coefficient lives in `seed/agronomy/` with a source citation; none are invented in code.

### 4.4 Market Intelligence
**In:** lots (quantity, grade, ready date, location), buyers, demand signals, mandi price
history, fuel price, storage capacity and cost, financing cost.
**Out:** effective price per buyer per lot, transaction attractiveness, allocation plan,
negotiation brief, alternatives, supply/demand gap.

```
effective_price_paise_per_kg =
      buyer_price
    − logistics_cost_per_kg(distance_km, fuel_price, load_size)
    − handling_cost_per_kg
    − expected_quality_loss_per_kg(grade_gap, transit_days)
    − other_transaction_cost_per_kg
    − storage_cost_per_kg(days_held)
    − financing_cost_per_kg(payment_delay_days, cost_of_capital)

transaction_attractiveness =
      w1·norm(effective_price)
    + w2·buyer_reliability
    − w3·rejection_probability
    − w4·norm(payment_delay_days)
    + w5·quantity_fit(lot_qty, buyer_min, buyer_max)
    − w6·norm(distance_km)
```
Weights are configuration, shown in the UI, and every component is displayed in the breakdown
(FR-543) — the score is never a black box.

Allocation is a small greedy assignment (lots → buyers → storage) subject to quantity, grade
and capacity constraints, with the residual explicitly reported.

### 4.5 Risk Intelligence
**In:** all seven domains — climate, weather, crop health, market, policy, supply chain, global.
**Out:** risk register entries with probability × impact × exposure, causal chains, watchlist.

The **causal chain** is a first-class output, not prose:

```json
{
  "trigger": {"event_id": "...", "headline": "Diesel price raised ₹2.4/L", "source": "..."},
  "chain": [
    {"step": "logistics cost per tonne-km rises ~6%", "confidence": 0.88},
    {"step": "effective price from Buyer B (180 km) falls ₹0.42/kg", "confidence": 0.81},
    {"step": "Buyer C (20 km) overtakes Buyer B on attractiveness", "confidence": 0.74}
  ],
  "exposure": {"crop": "potato", "tonnes": 420, "farmers": 312, "value_at_risk_paise": 176_400_000},
  "recommended_action": "Revisit the potato allocation before the 14 Feb delivery window."
}
```

Risk-adjusted comparison (FR-555) always presents at least two strategies:
```
risk_adjusted_value = expected_value − λ · downside_deviation
```
with λ configurable and displayed. The higher-EV strategy is not auto-selected.

### 4.6 Scheme Intelligence
**In:** farmer profiles, scheme rules, documents on record, application history.
**Out:** per-farmer eligibility with rule-by-rule pass/fail, org-level aggregate opportunity,
document gaps, deadlines.

Eligibility rules are stored as machine-evaluable JSON alongside the original text:
```json
{"all": [
  {"attr": "land_area_ha", "op": "<=", "value": 2.0},
  {"attr": "state", "op": "in", "value": ["UP", "BR", "MP"]},
  {"any": [{"attr": "category", "op": "in", "value": ["SC","ST"]},
           {"attr": "is_woman_farmer", "op": "==", "value": true}]}
]}
```
Missing attributes yield `INSUFFICIENT_DATA` with the named gap — never a silent `NOT_ELIGIBLE`.
Sensitive attributes are consent-gated and used only here (FR-566).

### 4.7 Funding (thin, by design)
**In:** input plan, expected yield/revenue, expected scheme benefit, the six permitted factors.
**Out:** funding requirement, expected farmer ROI, suggested tranching, data-sufficiency label.

```
funding_requirement = input_plan_cost − expected_scheme_benefit − farmer_contribution
expected_farmer_roi = expected_incremental_income / fpo_investment
```
Deliberately shallow (D-21). It shows its arithmetic and states what it does not know. It
never phrases an output as withholding support from a named farmer (FR-605).

---

## 5. The orchestrator

### 5.1 Algorithm

```
1. RESOLVE SCOPE
     ContextScope(actor, organization, subject_ids)   ← the information boundary
2. PLAN
     LLM selects which modules the question needs, and over what subjects/horizon
3. GATHER            (parallel, deterministic, cached per request)
     current observations · external records · domain rows — all provenance-resolved
4. RUN MODULES       (parallel, pure)
5. RECONCILE         (LLM, structured tool use)
     - detect conflicts between module findings
     - apply cross-domain override where warranted, and record the override + reason
     - rank by expected impact × confidence × urgency
     - drop any claim lacking an EvidenceRef
6. FREEZE
     EvidenceSnapshot = {module outputs, observations, external records, org state,
                         prompt_version, model_id, module_versions} + SHA-256
7. EMIT
     DecisionPacket (9 sections) + Recommendation rows (status = SUGGESTED)
8. PERSIST
     recommendations · snapshot · DomainEvent(RecommendationGenerated) · audit records
```

Steps 3–4 and 6–8 are deterministic. Only 2 and 5 involve the model, and step 5's output is
schema-constrained tool use — never parsed free text (FR-803).

### 5.2 Cross-domain override

**This section was rewritten once the real data arrived, and the correction is worth keeping.**

The original sketch used an illustrative "unseasonal rain probability 0.71" for the February
potato harvest window. The measured figure, from 30 years of ERA5 reanalysis at the tract
point, is **0.167** — roughly one year in six. Building the demo on the invented number would
have produced a more dramatic story and a false one, and it would have been indistinguishable
from a measured number once it was on a screen.

Correcting it changed the story from a weather story to a price story, which is what the data
actually supports. On the seeded Prayagraj collective the modules produce this:

```
Farm module    → "Ganga-Par: Paddy — the crop actually planted here — ranks 4 of 4 on
                  return per rupee (0.28 against Mustard's 1.93)"                 conf 0.58
               → the same, on the doab                                            conf 0.58
Risk module    → "Paddy harvests into its annual price trough: Rs 20.30/kg in November
                  against Rs 23.69/kg in January, across 1,868 t"                 conf 0.70
               → "November arrivals run 36.6x the year's median month — the trough is a
                  glut, so it recurs rather than passing"                         conf 0.70
               → "Paddy is 99% of operated area across 749 farmers"               conf 0.90

Orchestrator output:
  override: current_cropping.paddy   (module: status_quo)
  reason:   "The collective's current concentration in paddy is contradicted by 3 findings
             from 2 independent modules, all pointing the same way about the same crop in
             the same window. Nobody proposed this cropping pattern — it is what is already
             planted, which is why it would otherwise go unexamined. This is not an
             instruction to stop growing paddy: it is the case for the board to make that
             choice deliberately, with the alternatives priced."
```

**A third correction, and this one is about not cheating.** An earlier run *did* show a
Market-module finding here — "paddy realises 33% below the mandi modal" — and it was an
artifact of reading an ascending price series as if it were descending, so the comparison was
against prices from two years earlier. Fixing that bug removed the finding, and with it the
override, because only one module was left disagreeing.

The tempting repair was to lower `OVERRIDE_QUORUM` to 1 and get the demo beat back. What was
done instead was to look for evidence that genuinely existed: the Farm module ranks every
crop and was reporting only the winner, throwing away where the *incumbent* crop sat. Naming
that is honest, independently useful — an FPO with 99% of its area in one crop wants to know
where that crop ranks, not which crop wins in the abstract — and it makes the convergence
real rather than manufactured.

The real realisation gaps, for the record: paddy 9.8%, potato 12.1%, and wheat, mustard and
guava all clear *above* the mandi modal. That last part is the better story anyway — it is
the collective's aggregation premium showing up in the data.

**The second correction is structural.** The original rule could only override something a
*module* had proposed, which quietly assumed the risky plan is always the one the AI
suggests. On real data the opposite held: 99% of operated area was already committed to a
crop that two independent modules found problems with, and nobody had proposed it. So the
reconciler now treats the **dominant planted crop** — named by the Risk module's concentration
finding — as an implicit plan that can be overridden the same way.

Overriding the plan nobody argued for is usually the more valuable half.

An override fires only when at least `OVERRIDE_QUORUM` (2) *distinct modules* produce adverse
findings about the same subject, each more confident than what they contradict by more than
`OVERRIDE_MARGIN` (0.05). One module disagreeing with another is a difference of opinion; two
agreeing against a third is a pattern.

The override is rendered in the packet, above the recommendations. A silent override would be
a trust failure — the CEO's ability to disagree is the whole human-in-the-loop guarantee, and
it needs something visible to disagree with.

### 5.3 The Decision Packet schema

Nine sections, fixed order (FR-801):

```python
class DecisionPacket(BaseModel):
    question: str
    scope: PacketScope
    situation:        list[Claim]      # what is happening
    impact:           list[Claim]      # who/what is affected, quantified
    recommendation:   list[ProposedAction]
    expected_outcome: list[Claim]      # with ranges, never point promises
    confidence:       ConfidenceBlock  # overall + per-section + what would raise it
    evidence:         list[EvidenceRef]
    actions:          list[AssignedAction]   # role, task, due date
    schedule:         list[ProposedCalendarEvent]
    drilldown:        DrilldownRefs    # farmer/plot/crop_cycle/buyer/lot ids
    overrides:        list[OverrideNote]
    generated_at: datetime
    snapshot_id: UUID
    prompt_version: str
    model_id: str
```

`Claim` carries `statement`, `magnitude`, `unit`, `confidence`, `evidence[]`. A claim with an
empty `evidence[]` is dropped before rendering (FR-804).

### 5.4 Prompt-injection posture

Farmer-supplied text, images and ingested news are **untrusted data** (NFR-405). They enter
the model only inside clearly delimited data blocks, never as instructions. The orchestrator's
tool schema is fixed, so the worst case of a successful injection is a bad *claim* — which
still needs an `EvidenceRef` and still needs human approval before anything happens. The
information boundary is not defended by the prompt at all: the data never enters the context
(§7 of `DATA-MODEL.md`).

---

## 6. Request flow — the killer demo

```
CEO: "What should we do this season to maximize sustainable farmer income?"
  │
  ├─▶ POST /api/v1/assistant/fpo/ask     { question, org_id }
  │     ├─ resolve ContextScope(CEO, org)
  │     ├─ plan: [farm, quality, market, risk, scheme] over active crop cycles
  │     ├─ gather: 1,000 farmers · 2,412 ac · 5 crops · weather · 24mo prices
  │     │          · 12 schemes · 20 news events · 8 buyers
  │     ├─ run modules in parallel
  │     ├─ reconcile (LLM) → override farm→potato on market+climate evidence
  │     ├─ freeze snapshot (hash) 
  │     └─ SSE stream sections as they resolve
  │
  ├─▶ UI renders 9 sections; every number has a confidence chip + provenance popover
  │
  ├─▶ CEO clicks "Show affected farmers"
  │     GET /api/v1/drilldown/{packet_id}/affected  → 312 farmers → plots → cycles
  │
  ├─▶ CEO approves recommendation #2 with modification (₹35,000 → ₹32,000)
  │     POST /api/v1/recommendations/{id}/approve
  │     → Approval row · status EXECUTED · DomainEvent · AuditRecord
  │
  ├─▶ Execution: tasks created · calendar events pending field approval
  │     · farmer notifications for SHARED_WITH_MEMBERS content only
  │
  └─▶ Farmer opens portal in Hindi, asks by voice
        POST /api/v1/assistant/farmer/ask  { question, farmer_id }
        → ContextScope(farmer) — org-internal rows are not in the result set at all
```

---

## 7. Concurrency, jobs and scheduling

| Job | Cadence | Does |
|---|---|---|
| Weather ingest | 6-hourly | Forecast + observed per district; derived observations |
| Mandi price ingest | daily | Price + arrivals per commodity/market |
| News classify | hourly | Fetch → classify domain → detect FPO exposure → `PolicyEventDetected` |
| Scheme refresh | daily | Re-embed changed scheme text |
| Eligibility recompute | nightly | All members × all active schemes (NFR-104) |
| Risk recompute | nightly + on event | Refresh the register |
| Quality/yield predictions | nightly | Per active crop cycle |
| Staleness sweep | nightly | Mark stale observations, raise verification tasks |
| Outbox dispatch | 5 s | Publish `DomainEvent` → notifications, WhatsApp |
| Morning briefing | 05:30 IST | Assemble the CEO's N-items-need-attention packet |

APScheduler in-process for MVP; each job is idempotent and keyed by `(job, business_date)` so
a re-run is safe.

---

## 8. Frontend structure

```
apps/web/app/
├── (fpo)/
│   ├── dashboard/          10 cards + morning briefing
│   ├── assistant/          ask → streamed DecisionPacket → approve
│   ├── farmers/            list · drill-down · farmer 360
│   ├── production/         expected quantity/quality/window by crop
│   ├── market/             buyers · effective price · allocation · negotiation brief
│   ├── risk/               risk register · causal chains
│   ├── schemes/            opportunity aggregate → segment → farmer list
│   ├── calendar/           unified, approval states
│   └── decisions/          decision history · frozen evidence viewer
├── (farmer)/
│   ├── today/              ≤3 taps to the day's actions
│   ├── my-farm/            plots · crop cycles · resources
│   ├── assistant/          voice + text, Hindi/English
│   ├── schemes/            my eligibility · documents
│   └── calendar/
└── (admin)/
    ├── organizations/ · data-sources/ · discrepancies/ · prompts/
```

Shared components that carry the invariants: `<ConfidenceChip>`, `<ProvenancePopover>`,
`<DiscrepancyBadge>`, `<EvidenceList>`, `<ApprovalGate>`, `<DemoDataBadge>`,
`<DecisionPacketView>`. Any surface showing an AI-derived number must use them — that is how
UI-02 and UI-04 stay true without per-page discipline.

---

## 9. Testing strategy

| Level | What | Tool |
|---|---|---|
| Unit | Module formulas against hand-computed cases | pytest |
| Golden | Each module over the seeded scenarios; output diffed against a checked-in file | pytest + syrupy |
| Invariant | The nine tests in `SRS.md#82-invariant-acceptance-tests` | pytest |
| Contract | OpenAPI ↔ generated TS types stay in sync | CI check |
| Replay | Re-run a module against a stored `EvidenceSnapshot`; output must match byte-for-byte | pytest |
| E2E | The killer-demo sequence, headless | Playwright |

The **replay test** is the one that proves the architecture: if a module is not pure, replay
diverges and the test fails.

---

## 10. Known architectural risks

| Risk | Mitigation |
|---|---|
| LLM latency blows NFR-102 | Stream sections; run modules in parallel; cache the gather step per request; degrade to module output without narrative on timeout (NFR-302). |
| Orchestrator hallucinates a number not in any module output | Every claim requires an `EvidenceRef`; unbacked claims are dropped, not rendered (FR-804). A post-generation validator cross-checks each magnitude against the snapshot. |
| Synthetic data reads as fake to judges | Agronomic coefficients from cited sources; distributions fitted to published district statistics; `DEMO DATA` labelling turned into a credibility signal rather than hidden. |
| Provenance machinery eats the whole build | It is built first (hour 0–12) precisely because everything else depends on it and retrofitting is impossible. |
| Scope creep back toward the full vision | `docs/MVP-SCOPE.md#cut-list` is binding; anything marked POST-MVP needs an explicit decision recorded in `context.md`. |
