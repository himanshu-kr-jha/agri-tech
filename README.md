# AgriVardhak

**An AI decision & orchestration platform for Indian farmer collectives (FPO / PACS / SHG).**

> An FPO CEO asks *"What should we do this season to maximize sustainable farmer income?"*
> and gets back an **auditable Decision Packet** — situation, impact, recommendation, expected
> outcome, confidence, evidence, actions, drill-down — that a human approves before anything
> executes.

Built for the **AI for Public Good** challenge — *Inclusive AI, Social Impact and Empowerment
of Underserved Communities*.

**Status:** all 44 MUST deliverables built and evidenced · 311 tests, none skipped · runs with
the network disconnected. See [`PROGRESS.md`](PROGRESS.md) — its lower half is generated from
what the repository can prove, not from what someone typed.

---

## Quick start

Five commands from a fresh clone to a running demo. **No API keys needed** — the whole path
works offline.

```bash
git clone <this repo> && cd agrivadhak

make setup     # venv + npm install + Postgres in Docker + migrations   (~3 min first run)
make demo      # seed 1,000 farmers, real prices/weather, write the dev token
make dev       # API on :8000, web on :3000
```

Then open **<http://localhost:3000>** and sign in.

### Demo logins

All three are seeded, all use the password **`agrivardhak`**, and the sign-in page lists them so
you do not have to remember. Which dashboard you land on is decided by your **role**, on the
server — not by the URL you typed.

| Sign in as | Username | You get |
|---|---|---|
| **Ramesh Verma — CEO** | `ceo@demo.agrivardhak` | The organization console: assistant, every member, buyer negotiations, risk register, decision history. The only role that can approve a crop plan. |
| **Sunita Devi — Field Officer** | `officer@demo.agrivardhak` | The same console, but may approve crop protection and *not* a funding allocation |
| **Pushpa Nishad — Member** | `farmer@demo.agrivardhak` | Their own farm, in Hindi and English. Nothing else. |

As the CEO, ask:

> *What should we do this season to maximize sustainable farmer income?*

The answer takes about six seconds and streams in section by section.

Then **sign out and sign in as the member.** Every organization URL redirects them to their
own farm, and the API returns `403` underneath — the redirect is a courtesy, the refusal is
the boundary. Those credentials are published on purpose: they are synthetic accounts in a
demonstration system, and a credential that is documented and flagged is safer than one that
looks like a secret while being equally guessable. The API only serves that list outside
production.

### Prerequisites

| | Version | Check | If missing |
|---|---|---|---|
| **Docker** with Compose v2 | any recent | `docker compose version` | [docs.docker.com/get-docker](https://docs.docker.com/get-docker/) |
| **uv** | ≥ 0.4 | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Node.js** | ≥ 20 | `node --version` | [nodejs.org](https://nodejs.org/) |
| **Python 3.12** | exactly 3.12 | `python3.12 --version` | `uv` will fetch it if absent |
| **make** | any | `make --version` | `apt install build-essential` |

Python 3.13 does **not** work — a dependency has no wheel for it yet. `uv venv --python 3.12`
inside `make setup` pins this for you; you do not need 3.12 as your system Python.

Postgres runs in Docker on **port 5433**, not 5432, so it will not collide with a Postgres you
already have. Credentials are `agrivardhak` / `agrivardhak` / `agrivardhak`.

### Verify it worked

```bash
make check     # ruff + mypy (54 files) + eslint + tsc
make test      # 311 tests, ~2 min
make progress  # regenerate PROGRESS.md from evidence
```

If `make test` is green you have a working system. There is no step after this that can
silently fail.

---

## What you are looking at

| Open | To see |
|---|---|
| **`/assistant`** | Ask a question. Nine sections stream in fixed order; every number carries a confidence chip. **The amber banner at the top is the point** — it is where the system disagrees with itself, in front of you. |
| `/dashboard` | The morning briefing (what is waiting on *you*, first) above ten organization cards |
| `/decisions/<id>` | The frozen evidence behind a decision — SHA-256, module versions, and a **replay** that rebuilds the packet from those bytes and says whether it still matches |
| — | Approve a recommendation **with a different amount**. Both numbers persist. |
| `/risk` | The register, ordered by *exposure* rather than probability. One row explains why a near-certain event is the climate, not a risk. |
| `/market` | Headline price versus what the collective actually banks |
| `/farmers/<id>` | Every plot area with its source, date, confidence and conflict badge |
| `/impact` | Reports what it **could not** attribute as prominently as what it could |

### See the information boundary

Sign out, then sign in as `farmer@demo.agrivardhak`.

A farmer gets **403 on all ten organization endpoints** and 200 on their own record. The
farmer view is built farmer-scoped from the start rather than filtered down from an
organization query, so org-internal rows are never in the result set for a rendering bug to
leak.

`docs/DEMO-RUNBOOK.md` has the full seven-minute walkthrough.

---

## The problem

An FPO with 1,000 farmers does not know, three months ahead, that 400 tonnes of tomato are
coming. So it cannot secure buyers, storage or logistics — and the farmers take the loss. The
same organization cannot see which members are leaving government benefits unclaimed, cannot
tell a ₹34/kg buyer 180 km away from a ₹30/kg buyer 22 km away in terms of what actually lands
in a farmer's hand, and cannot reconstruct why it made a decision when a member disputes their
share.

None of that is a missing model. It is missing **connective tissue** between farmer-level
reality, external intelligence, and organizational decisions.

## What this is

Not a farmer advisory app. Not a disease classifier. Not a marketplace.

A layer that turns fragmented farmer-level data plus external agricultural intelligence into
**organization-level actions with a permanent audit trail** — optimizing for *sustainable
farmer income and FPO financial health*, never for FPO profit alone.

**Seven deterministic intelligence modules** — Farm, Crop Health, Quality, Market, Risk,
Scheme, Funding — each a pure function over provenance-resolved inputs. An orchestrator
gathers, runs them, reconciles their disagreements, freezes the evidence and emits a Decision
Packet where every claim carries its sources.

An LLM narrates the result. It does not decide it — which is what lets the whole thing replay
from stored bytes and run with the network unplugged.

## What makes it defensible

| | |
|---|---|
| **Human-in-the-loop** | There is no code path that writes `EXECUTED` without reading an approval row back from the database. Not "should not" — *cannot*. |
| **Frozen evidence** | Every recommendation stores a hashed, immutable snapshot of its inputs, module versions and coefficients. *"Why did it say that on 22 August?"* is answerable forever, and the UI has a replay button that checks. |
| **Provenance everywhere** | Every consequential value carries source, time, confidence and verification status. A field-verified observation and a stale self-report do not get the same weight. |
| **Conflicts surface** | Farmer says 2.0 acres, records say 1.6, officer says 1.8 — all three are shown and verification is requested. It never silently picks one. |
| **A real information boundary** | Enforced in the data-access layer, not by asking a model nicely. |
| **Honest attribution** | Advice that was never followed is **not** scored as failed. A favourable season **confounds** a good outcome rather than confirming it. |
| **IPM-first** | Crop protection is a chemical *class* plus "read the label and consult a local agronomist" — never a product and a dose. The unsourced knowledge base is capped below the orchestrator's own decision floor, so it structurally cannot drive a recommendation. |

---

## The data: what is real and what is not

This matters more than usual here, so it is stated plainly and enforced in code.

**Real, cited, and committed as offline fixtures:**

- **23,460 Agmarknet price rows** — 731 days, five verified Prayagraj markets
- **2,439 tract-days of weather** — Open-Meteo, three tract centroids
- **30 years of ERA5 hazard climatology** — half-month frequencies, derived not asserted
- Verified block list, agro-climatic zone, GI guava spec from GI Journal 19

**Synthetic and labelled `DEMO DATA` on every screen it touches:** the 1,000 farmers, their
plots, the buyers and the lots.

**Unsourced and capped:** cost-of-cultivation and crop-protection coefficients. The system
lowers its own confidence because of them — crop health caps at **0.42**, deliberately below
the orchestrator's 0.45 floor. [`seed/sources.md`](seed/sources.md) lists all 56 open items.

The demo is anchored to **Prayagraj district, Uttar Pradesh**, chosen because the Ganga and
Yamuna split it into three agriculturally distinct tracts — so one FPO contains irrigated
paddy–wheat farmers *and* rain-fed Vindhyan farmers, and risk clustering shows a real pattern
rather than a flat list.

---

## Repository layout

```
apps/api/agrivardhak/
├── domain/          entities, enums, units — no I/O
├── intelligence/    the seven modules, each a pure function
├── orchestrator/    gather → reconcile → freeze → emit, plus lifecycle
├── provenance/      trust decay, conflict detection, resolution
├── ingestion/       Agmarknet, Open-Meteo adapters
├── learning/        outcome, adherence, attribution
└── api/             FastAPI routers
apps/web/src/app/
├── (fpo)/           assistant, dashboard, decisions, risk, market, farmers, impact
└── (farmer)/        the farmer's own view — a separate route group on purpose
seed/                fetch scripts + committed fixture payloads
```

## Documentation

| Read this | For |
|---|---|
| [`docs/DEMO-RUNBOOK.md`](docs/DEMO-RUNBOOK.md) | **The seven-minute walkthrough**, troubleshooting, and answers to the hard questions |
| [`PROGRESS.md`](PROGRESS.md) | What is built and what is left — machine-verified |
| [`context.md`](context.md) | Product thesis and decision log — **start here to understand *why*** |
| [`CLAUDE.md`](CLAUDE.md) | The rules: ten invariants, stack, conventions |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Eight layers, module contracts, the orchestrator algorithm and the override rule |
| [`docs/SRS.md`](docs/SRS.md) | Full requirements with stable FR/NFR ids |
| [`docs/DATA-MODEL.md`](docs/DATA-MODEL.md) | Entities, events, provenance |
| [`docs/MVP-SCOPE.md`](docs/MVP-SCOPE.md) | The plan, the cut list, the demo script |
| [`seed/sources.md`](seed/sources.md) | Citation register gating every non-synthetic value |
| [`docs/adr/`](docs/adr/) | Architecture decision records |

## Stack

Next.js 16 · React 19 · TypeScript · Tailwind · FastAPI · Python 3.12 · SQLAlchemy 2 ·
PostgreSQL 16 + PostGIS + pgvector · Claude (Anthropic SDK), for narration only.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Every page says *"Could not reach the API"* | API not running | `make api` in a second terminal |
| Redirected to `/login` unexpectedly | Session expired (12h) | Sign in again |
| Sign-in says *"Could not reach the API"* | API not running | `make api` |
| `make seed` prints nothing new | Already seeded — it is idempotent | `make seed-reset` |
| `make setup` fails on the venv | Python 3.13 picked up | `uv venv --python 3.12 --clear` in `apps/api` |
| Assistant returns 500 | Stale schema | `make upgrade` |
| Port 5433 already in use | Another Postgres or a stale container | `make db-down`, then `make db-up` |
| Everything is broken | | `make db-reset && make demo` — nuclear but reliable |

**No external service needs to be up.** Prices, weather and climatology are stored payloads;
without an Anthropic key the packet is produced deterministically and reports
`model_id: deterministic`. A test runs the entire pipeline with every socket blocked.

## Contributing

Read [`CLAUDE.md`](CLAUDE.md) first — the ten invariants are product law, not style. In
particular: never fabricate agronomy (cite it in `seed/sources.md` or flag it
`SYNTHETIC — DEMO ONLY`), and never let a number reach a screen without provenance.

Finished something? Add a `Deliverable(...)` to `scripts/progress.py` with the evidence that
proves it, then run `make progress`. A row with no evidence stays ⬜ regardless of what anyone
writes in the table.
