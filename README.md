# AgriVardhak

**An AI decision & orchestration platform for Indian farmer collectives.**

> An FPO CEO asks *"What should we do this season to maximize sustainable farmer income?"*
> and gets back an **auditable decision** — situation, impact, recommendation, expected outcome,
> confidence, evidence, actions, schedule, drill-down — that a human approves before anything
> executes.

Built for the **AI for Public Good** challenge — *Inclusive AI, Social Impact and Empowerment
of Underserved Communities*.

---

## The problem

An FPO with 1,000 farmers does not know, three months ahead, that 400 tonnes of tomato are
coming. So it cannot secure buyers, storage or logistics — and the farmers take the loss. The
same organization cannot see which of its members are leaving government benefits unclaimed,
cannot tell a ₹35/kg buyer 180 km away from a ₹32/kg buyer 20 km away in terms of what actually
lands in a farmer's hand, and cannot reconstruct why it made a decision when a member disputes
their share.

None of that is a missing model. It is missing **connective tissue** between farmer-level
reality, external intelligence, and organizational decisions.

## What this is

Not a farmer advisory app. Not a disease classifier. Not a marketplace.

A layer that turns fragmented farmer-level data plus external agricultural intelligence into
**organization-level actions with a permanent audit trail** — optimizing for *sustainable farmer
income and FPO financial health*, never for FPO profit alone.

Six deterministic intelligence modules — Farm, Crop Health, Quality, Market, Risk, Scheme —
feed an LLM orchestrator that reconciles them, overrides them when cross-domain evidence
demands it, and produces a **Decision Packet** where every claim carries its evidence.

## What makes it defensible

| | |
|---|---|
| **Human-in-the-loop** | AI recommends and explains. A human approves. Only then does anything execute. |
| **Frozen evidence** | Every recommendation stores an immutable, hashed snapshot of its inputs. *"Why did it say that on 22 August?"* is answerable forever. |
| **Provenance everywhere** | Every consequential value carries source, time, confidence and verification status. A field-verified observation and a stale self-report do not get the same weight. |
| **Conflicts surface** | Farmer says 2 acres, records say 1.6, officer says 1.8 — the system shows all three and asks for verification. It never silently picks one. |
| **Real information boundary** | Farmers never see FPO internal strategy or other farmers' data — enforced in the data-access layer, not by asking a model nicely. |
| **Honest attribution** | We record whether advice was actually followed. `CONFOUNDED` is a valid result. We do not claim credit we cannot prove. |
| **IPM-first** | Crop protection defaults to prevention and biological control; chemicals only when severity and confidence justify it, always with the label caution. |

## Documentation

| Read this | For |
|---|---|
| [`PROGRESS.md`](PROGRESS.md) | **What is built and what is left** — the lower half is machine-verified |
| [`context.md`](context.md) | Product thesis, decision log, why everything is the way it is — **start here** |
| [`CLAUDE.md`](CLAUDE.md) | The rules: invariants, stack, conventions, working agreements |
| [`docs/SRS.md`](docs/SRS.md) | Full requirements with stable FR/NFR ids and acceptance criteria |
| [`docs/DATA-MODEL.md`](docs/DATA-MODEL.md) | Entities, events, provenance, and the eight resolved design questions |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Eight layers, module contracts, the orchestrator algorithm |
| [`docs/MVP-SCOPE.md`](docs/MVP-SCOPE.md) | The 72-hour plan, the binding cut list, the demo script |
| [`docs/DEMO-CONTEXT.md`](docs/DEMO-CONTEXT.md) | Prayagraj district profile — the ground truth the seed derives from |
| [`seed/sources.md`](seed/sources.md) | Citation register gating every non-synthetic value |
| [`docs/GLOSSARY.md`](docs/GLOSSARY.md) | Ubiquitous language — use these words exactly |
| [`docs/adr/`](docs/adr/) | Architecture decision records |
| [`docs/discovery-transcript.md`](docs/discovery-transcript.md) | The product-discovery session this is all derived from |

## Stack

Next.js 15 · TypeScript · FastAPI · Python 3.12 · PostgreSQL 16 + PostGIS + pgvector ·
Claude (Anthropic API) for orchestration.

## Status

**Phase 1 in progress.** Schema, provenance layer and seed are done; the intelligence modules
and orchestrator are next. See [`PROGRESS.md`](PROGRESS.md) for the current picture — its
lower half is generated from what the repository can prove, not from what someone typed.

## A note on the data

The demo is anchored to **Prayagraj district, Uttar Pradesh** — chosen because the Ganga and
Yamuna split it into three agriculturally distinct tracts, so a single FPO contains irrigated
paddy–wheat farmers *and* rain-fed Vindhyan farmers, and risk clustering shows a real pattern
rather than a flat list.

All demo data is **synthetic**. Agronomic coefficients come from cited sources in
`seed/sources.md`; anything without a source is flagged and rendered with a `DEMO DATA` marker
in the UI. We would rather label our assumptions than imply precision we do not have.
