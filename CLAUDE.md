# AgriVardhak — Claude Code Project Instructions

> AI decision & orchestration platform for Indian farmer collectives (FPO / PACS / SHG).
> Converts fragmented farmer-level data + external agricultural intelligence into
> **auditable, human-approved organization-level actions** that raise sustainable
> farmer income while keeping the collective financially healthy.

**Read `context.md` before your first substantive change in a session.** It carries the
product thesis, the locked decisions, and the reasoning behind them. This file carries
the rules you must not break.

---

## 1. The one-sentence thesis

> An FPO CEO asks *"What should we do this season to maximize sustainable farmer income?"*
> and gets back a **Decision Packet** — situation, impact, recommendation, expected outcome,
> confidence, evidence, actions, schedule, drill-down — that a human approves before
> anything executes.

Optimization target, verbatim and non-negotiable:

> **Maximize sustainable farmer income + FPO financial health, subject to risk,
> available capital, demand, crop suitability, water/land constraints, operational
> constraints and sustainability.**

Never write copy, prompts, or objective functions that optimize FPO profit *alone*, and
never promise "maximum profit". The phrase is *sustainable farmer income*.

---

## 2. Non-negotiable invariants

These are product law. If a change would violate one, stop and raise it instead of coding around it.

| # | Invariant | What it means in code |
|---|---|---|
| **INV-1** | **Human-in-the-loop.** AI never autonomously performs a consequential action. | Every `Recommendation` walks `SUGGESTED → REVIEWED → APPROVED → EXECUTED → OUTCOME_RECORDED`. No code path may write `EXECUTED` without an `Approval` row signed by a human user with the right role. |
| **INV-2** | **Evidence is frozen.** A recommendation is explainable forever. | On generation, persist an immutable `EvidenceSnapshot` (JSONB + SHA-256 content hash). Never recompute a historical recommendation from live data. |
| **INV-3** | **Every consequential value carries provenance.** | source, observed_at, recorded_at, confidence, verification_status. See `docs/DATA-MODEL.md#provenance`. A value without provenance may not enter an intelligence module. |
| **INV-4** | **Conflicts surface, they do not resolve silently.** | When sources disagree beyond tolerance, emit a `DataDiscrepancy` and lower confidence. Never let the system quietly "pick 1.8 acres". |
| **INV-5** | **Information boundary between assistants.** | Only data explicitly marked official/shared crosses from the FPO context to a farmer, or from one farmer to another. Enforced in the data-access layer, not in prompts. |
| **INV-6** | **Prediction ≠ Recommendation.** | `Prediction` is a claim about reality (yield will be 4.2 t, conf 0.81). `Recommendation` is a proposed action. Separate tables, separate lifecycles, separate evaluation. |
| **INV-7** | **Adherence is recorded.** | We store whether the human actually followed the recommendation and how faithfully. A model must never learn "my advice failed" from advice that was never implemented. |
| **INV-8** | **Chemical safety floor.** | Crop-protection output is IPM-first: prevention → cultural → biological → chemical, and chemical is *class/option + "consult label & local agronomist"*, never an unattributed exact product+dosage. See `docs/SRS.md#safety`. |
| **INV-9** | **Farmer owns their data.** | Consent is explicit, per-purpose, revocable. Research datasets are anonymized + aggregated. Data-derived revenue routes to an ecosystem fund (Model C). |
| **INV-10** | **Recommendations are reversible & re-evaluated.** | New material data does not mutate an approved recommendation; it emits a `RecommendationSuperseded` event and flags the prior decision for review. |

---

## 3. Stack

| Layer | Choice | Notes |
|---|---|---|
| Web app | **Next.js 16 (App Router) + TypeScript + Tailwind + shadcn/ui** | FPO console, farmer portal, field-officer screens. Server Components by default. |
| API / AI | **Python 3.12 + FastAPI + Pydantic v2** | Intelligence modules, orchestrator, ingestion workers. |
| DB | **PostgreSQL 16 + PostGIS + pgvector** | One store: relational + geospatial plots + embeddings for scheme/news RAG. |
| ORM / migrations | **SQLAlchemy 2.x + Alembic** | Python owns the schema. Next.js reads through the FastAPI API only — no direct DB access from the web tier. |
| LLM | **Claude (Opus 5 / Sonnet 5) via the Anthropic SDK** | Orchestrator + the two Assistants. Intelligence modules are deterministic Python. |
| Queue / async | **Postgres-backed outbox + APScheduler** | No Kafka/Redis for MVP. |
| Voice | **Browser Web Speech + Whisper fallback** | Demo-grade Hindi voice, not telephony IVR. See scope note in `docs/MVP-SCOPE.md`. |
| WhatsApp | **Meta Cloud API sandbox** | Thin farmer notification + Q&A path only. |
| Auth | **NextAuth (web) → JWT verified by FastAPI** | Role claims in the token; row-level authorization in Python. |

Before writing any Anthropic API code, load the `claude-api` skill — do not answer model-id,
pricing, or caching questions from memory.

---

## 4. Repository layout

```
agrivadhak/
├── CLAUDE.md              ← you are here
├── context.md             ← product context + decision log (read first)
├── PROGRESS.md            ← what is built vs left (`make progress`)
├── docs/
│   ├── SRS.md             ← requirements, FR-/NFR- IDs, acceptance criteria
│   ├── DATA-MODEL.md      ← entities, events, provenance, the 8 resolved decisions
│   ├── ARCHITECTURE.md    ← 8 layers, module contracts, orchestrator algorithm
│   ├── MVP-SCOPE.md       ← 72-hour plan, cut list, demo script
│   ├── DEMO-CONTEXT.md    ← Prayagraj district profile the seed derives from
│   ├── GLOSSARY.md        ← ubiquitous language — use these words exactly
│   ├── adr/               ← architecture decision records
│   └── discovery-transcript.md  ← source product-discovery session (read-only)
├── apps/
│   ├── web/               ← Next.js
│   └── api/               ← FastAPI
│       └── agrivardhak/
│           ├── domain/        ← entities, value objects, events (no I/O)
│           ├── intelligence/  ← the six modules, each a pure function
│           ├── orchestrator/  ← decision packet assembly
│           ├── ingestion/     ← weather, mandi, scheme, news adapters
│           ├── provenance/    ← observation + confidence machinery
│           └── api/           ← FastAPI routers
├── packages/
│   └── contracts/         ← shared TS types generated from Pydantic schemas
└── seed/
    ├── sources.md         ← citation register — gates every non-synthetic value
    └── ...                ← synthetic Prayagraj FPO: 1,000 farmers, 2 seasons of history
```

---

## 5. Ubiquitous language

Use these words exactly; do not invent synonyms. Full list in `docs/GLOSSARY.md`.

`Organization` (type = FPO | PACS | SHG) · `Membership` · `Farmer` · `Farm` · `Plot` ·
`PlotTenure` · `CropCycle` · `Observation` · `FarmResource` · `ResourceFlow` ·
`Prediction` · `Recommendation` · `EvidenceSnapshot` · `Approval` · `Intervention` ·
`Outcome` · `Attribution` · `DataDiscrepancy` · `DecisionPacket` · `Scheme` ·
`EligibilityAssessment` · `Buyer` · `EffectivePrice` · `TransactionAttractiveness` ·
`RiskRegisterEntry` · `CalendarEvent`.

Words we deliberately do **not** use: "user" for a farmer (say `Farmer`), "field" for land
(say `Plot`), "score" without a named metric, "AI decided" (AI *recommends*).

---

## 6. Coding conventions

**General**
- IDs are UUIDv7 (`uuid_generate_v7()`), never sequential integers, never natural keys.
- Money is `BIGINT` **paise**. Never floats. Format at the edge.
- Area is `NUMERIC` **square metres** canonical; display in acres (`/4046.86`) or hectares.
- Mass is `NUMERIC` **kilograms**. Prices are paise-per-kilogram.
- All timestamps `TIMESTAMPTZ`, stored UTC, rendered `Asia/Kolkata`.
- Every table has `created_at`, `updated_at`; append-only tables have no `updated_at`.

**Python**
- Type hints everywhere; `mypy --strict` on `domain/` and `intelligence/`.
- Intelligence modules are **pure functions**: `(ModuleInput) -> ModuleOutput`. No DB calls,
  no network, no clock reads inside them — inputs are gathered by the orchestrator and
  passed in. This is what makes them testable and replayable against an `EvidenceSnapshot`.
- Every module output carries `confidence: float` and `evidence: list[EvidenceRef]`.
- Ruff for lint/format. Line length 100.

**TypeScript**
- Server Components by default; `"use client"` only for interactivity.
- No `any`. Types for API payloads are generated into `packages/contracts` — do not hand-write them.
- Every number rendered to a user gets a unit and, where it is AI-derived, a confidence chip.

**Prompts**
- Prompts live in `apps/api/agrivardhak/orchestrator/prompts/*.md`, versioned, never inline strings.
- Every prompt that produces a recommendation must emit the `DecisionPacket` JSON schema
  via tool use — never free-text parsing.

**Tests**
- `pytest`. Intelligence modules require golden-file tests over seeded scenarios.
- One end-to-end test must assert INV-1: an unapproved recommendation cannot execute.

---

## 7. Commands

```bash
# once
make setup                # uv sync + pnpm install + docker compose up -d db

# dev
make dev                  # api on :8000, web on :3000
make seed                 # load the synthetic 1,000-farmer FPO
make migrate m="message"  # alembic revision --autogenerate
make upgrade              # alembic upgrade head

# quality
make check                # ruff + mypy + tsc + eslint
make test                 # pytest + vitest
```

If a command above does not exist yet, create it in the `Makefile` rather than documenting
a longer incantation.

---

## 8. Working rules for Claude in this repo

1. **Docs are the spec.** If you change behaviour that `docs/SRS.md` describes, update the
   FR/NFR entry in the same change. Requirement IDs are stable — never renumber.
2. **Finish a deliverable, run `make progress`.** `PROGRESS.md` is the shared view of what
   is built. Its lower half is generated from evidence — a symbol that must import, a test
   that must pass, a row count that must hold — so you cannot mark something done by editing
   the table. Starting something new? Add a `Deliverable(...)` to `scripts/progress.py` with
   the evidence that will prove it, *then* build it.
3. **Decisions get ADRs.** Any choice a future reader would ask "why?" about goes in
   `docs/adr/NNNN-title.md` using the existing template. Link it from `context.md`.
4. **Scope discipline.** This is a 48–72 hour build for 3–5 people. `docs/MVP-SCOPE.md`
   has an explicit cut list. Do not implement anything marked `POST-MVP` without being asked.
5. **Never fabricate agronomy.** Yield coefficients, pesticide guidance, scheme eligibility
   rules and mandi prices must come from a cited source in `seed/sources.md` or be clearly
   labelled `SYNTHETIC — DEMO ONLY` in both the data and the UI.
6. **The demo is a deliverable.** Changes must keep `make seed && make dev` reproducing the
   killer demo in `docs/MVP-SCOPE.md#demo-script`.
7. RTK is available for token-efficient shell ops (see the global instructions); the hook
   rewrites commands transparently.
