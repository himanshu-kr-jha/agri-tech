# MVP Scope & 72-Hour Plan — AgriVardhak

Version 1.0 · 2026-08-22 · **Binding**

Constraint: **48–72 hours, 3–5 people.** This document is the knife. Anything marked
`POST-MVP` does not get built without an explicit decision recorded in `context.md`.

---

## 1. The one thing we are demoing

> An FPO CEO asks one question and receives an **auditable decision** — not a dashboard,
> not a chatbot answer — which they approve, which becomes tasks and calendar entries, which
> farmers see only the permitted slice of, and whose reasoning is still reconstructable a
> month later.

Everything in the build either serves that sentence or is cut.

---

## 2. Scope decision on the three farmer channels

All three channels were requested. In 72 hours, three channels at full depth is not
achievable, so depth is graded rather than channels dropped (ADR-0008):

| Channel | Depth in MVP | Rationale |
|---|---|---|
| **Web (Hindi/English)** | **Complete.** Farmer portal: today's actions, my farm, assistant, schemes, calendar. | This is the channel judges will actually use. |
| **Voice** | **Demo-grade.** Browser Web Speech API for Hindi/English input on the assistant field, TTS for the answer. No telephony, no IVR tree. | Delivers the accessibility story convincingly at ~3 hours of work. Real IVR is a week. |
| **WhatsApp** | **One thin path.** Outbound notification of approved farmer-facing actions + inbound free-text question routed to the Farmer Assistant. Sandbox number. | Proves the channel exists without owning a conversation-state machine. |

If WhatsApp sandbox provisioning is not done by hour 24, it is cut and the notification path
falls back to in-app. That call is made at the hour-24 checkpoint, not later.

---

## 3. In scope — the build list

### Must exist for the demo to work

| # | Deliverable | Requirements |
|---|---|---|
| M1 | Postgres schema + Alembic migrations for the full entity catalog | DR-01…DR-09 |
| M2 | Observation/provenance layer: write, trust weighting, decay, current-value view | FR-301…FR-307 |
| M3 | Discrepancy detection + inline surfacing + resolution flow | FR-304, FR-305, UI-10 |
| M4 | Seed: **Prayagraj FPO** — 1,000 farmers, 2,412 acres across 3 tracts, 5 crops, 2 past seasons + 1 active, 8 buyers, 12 schemes, 20 news events, 24 months of prices. Every non-synthetic value gated by a `seed/sources.md` row. | DR-09, C-2, D-24 |
| M5 | Auth + roles (Admin / CEO / Farmer) + `ContextScope` enforcement in repositories | FR-104, FR-809, NFR-401/402 |
| M6 | Quality Intelligence module | FR-531…FR-534 |
| M7 | Market Intelligence module (effective price, attractiveness, allocation, brief) | FR-541…FR-546 |
| M8 | Risk Intelligence module (7 domains, register, causal chains) | FR-551…FR-555 |
| M9 | Scheme Intelligence module (rule engine, aggregate, drill-down, doc gaps) | FR-561…FR-565 |
| M10 | Farm Intelligence module (thin: status + income-per-rupee ranking) | FR-511, FR-512 |
| M11 | Crop Health Intelligence module (checklist-driven, IPM action plan, humility gate) | FR-521…FR-524 |
| M12 | Funding requirement (thin, arithmetic shown) | FR-601…FR-606 |
| M13 | Orchestrator + Decision Packet + evidence freezing + override | FR-801…FR-806, FR-704 |
| M14 | Approval lifecycle incl. approve-with-modification | FR-705…FR-710 |
| M15 | FPO console: dashboard, assistant, drill-down, risk, market, schemes, decisions | UI-01…UI-04, UI-08 |
| M16 | Farmer portal (Hi/En) + voice input | UI-05, UI-06, FR-808, FR-810 |
| M17 | Unified calendar + approval gate + tasks | FR-901…FR-906 |
| M18 | Outcome + adherence + attribution capture on one seeded past recommendation | FR-1001…FR-1004 |
| M19 | Morning briefing | FR-811 |
| M20 | Impact metrics panel with measured/estimated/proxy labels | FR-1201…FR-1203 |
| M21 | The nine invariant tests | SRS §8.2 |

### Build if ahead of schedule

| # | Deliverable | Requirements |
|---|---|---|
| S1 | Outbreak clustering across the membership | FR-525 |
| S2 | Sell-now vs hold analysis with break-even holding period | FR-547 |
| S3 | Supply/demand gap for next season | FR-548 |
| S4 | Farm-composition proposals (integrated farming) | FR-513 |
| S5 | WhatsApp inbound Q&A | ADR-0008 |
| S6 | Module accuracy panel | FR-1005 |
| S7 | Risk watchlist with thresholds | FR-556 |

---

## 4. Cut list {#cut-list}

Consciously **not** built. Each was discussed in discovery and deferred.

| Cut | Why | When |
|---|---|---|
| Marketplace / transaction execution | The product is intelligence, not a mandi. D-05. | POST-MVP |
| Payment & disbursement rails | `FundingAllocation` records the decision, not money movement. D-21. | POST-MVP |
| Real financial optimizer | Needs financial history we do not have, and a finance team. D-21. | POST-MVP |
| Trained CV disease model | ADR-0006. Checklist + assistive image label instead. | POST-MVP |
| Trained yield/price ML models | Deterministic formulas with cited coefficients are more defensible in 72h. | POST-MVP |
| Satellite / IoT / soil-sensor ingestion | Explicitly deferred in discovery. | POST-MVP |
| Government record integration | "not for prototyping stage". | POST-MVP |
| Researcher dataset marketplace, free/paid tiers | Business model, not product spine. D-22. | POST-MVP |
| Field Officer / Procurement / Finance / Researcher roles | Three roles for MVP. The CEO exercises field-officer approvals. | POST-MVP |
| Logistics booking, warehouse management | Costs are modelled; operations are not. | POST-MVP |
| Blockchain | Append-only + content hash gives the same property. | Never |
| Offline-first sync | Real need, but a multi-week problem. | POST-MVP |
| Multi-tenant billing, org onboarding self-serve | Admin seeds organizations. | POST-MVP |
| Telephony IVR | Browser voice covers the demo. ADR-0008. | POST-MVP |
| Regional languages beyond Hindi | i18n structure supports it; only hi/en strings shipped. | POST-MVP |
| Resource-flow substitution reasoning | Modelled and displayed, not reasoned over. FR-208. | POST-MVP |

---

## 5. Hour-by-hour plan

Five roles. With 3 people, merge **BE-2 into BE-1** and **AI into BE-1**, and cut S1–S7 entirely.

| Role | Owns |
|---|---|
| **BE-1** | Schema, provenance, repositories, auth/scope |
| **BE-2** | Ingestion adapters, seed generator, jobs |
| **AI** | Modules, orchestrator, prompts, evidence freezing |
| **FE-1** | FPO console |
| **FE-2** | Farmer portal, i18n, voice, shared invariant components |

### Phase 0 — Hours 0–6 · Foundation

| Role | Work |
|---|---|
| BE-1 | Repo skeleton, Docker Compose (pg16+postgis+pgvector), Alembic, entity catalog → migrations, `ContextScope` in the repository base class |
| BE-2 | Seed generator scaffold; **work the `seed/sources.md` checklist for Prayagraj** — zone, crop calendar, Agmarknet market list, base yields — before any generator logic |
| AI | `ModuleInput`/`ModuleOutput`/`Finding`/`EvidenceRef` contracts; `DecisionPacket` schema; module stubs returning fixtures |
| FE-1 | Next.js app, auth, layout, `<ConfidenceChip>` `<ProvenancePopover>` `<DemoDataBadge>` |
| FE-2 | i18n scaffold (hi/en), farmer shell, mobile layout |

**Gate @ 6h:** migrations apply; a stub Decision Packet renders end to end from API to UI.
Contracts are frozen from here — no schema churn after this point.

### Phase 1 — Hours 6–18 · Provenance & data

| Role | Work |
|---|---|
| BE-1 | Observation write path, trust weights, decay, `current_observation` view, discrepancy detection + resolution endpoint |
| BE-2 | Weather + mandi adapters with fixture fallback; seed 1,000 farmers across the three Prayagraj tracts with the `DEMO-CONTEXT.md` §5 distributions, 2 past seasons, 1 active |
| AI | Quality + Market modules for real, against seeded data; golden tests |
| FE-1 | Dashboard 10 cards; farmer list + drill-down |
| FE-2 | Farmer today/my-farm; Hindi strings; `<DiscrepancyBadge>` |

**Gate @ 18h:** `make seed && make dev` renders a real dashboard for 1,000 farmers with real
confidence chips. Provenance is done — nothing is retrofitted after this.

### Phase 2 — Hours 18–36 · Intelligence

| Role | Work |
|---|---|
| BE-1 | Approval lifecycle, `Approval`/`AuditRecord`/`DomainEvent` outbox, recommendation state machine |
| BE-2 | Scheme + news ingestion, embeddings, nightly jobs, outbox dispatcher |
| AI | Risk + Scheme + Farm + Crop Health modules; orchestrator plan/gather/reconcile; evidence freezing + hash |
| FE-1 | Assistant view with SSE streaming; `<DecisionPacketView>`; risk register; market/buyer screens |
| FE-2 | Farmer assistant, voice input, scheme view |

**Checkpoint @ 24h:** WhatsApp go/no-go. Scope-vs-clock review; cut from S-list first, then
from the bottom of the M-list (M20 → M18 → M11 in that order).

**Gate @ 36h:** the CEO can ask the question and get a real, evidence-backed packet.

### Phase 3 — Hours 36–52 · The loop closes

| Role | Work |
|---|---|
| BE-1 | Approve-with-modification; supersession; execution → tasks + calendar events |
| BE-2 | Morning briefing job; notification dispatch; WhatsApp path if green |
| AI | Cross-domain override; negotiation brief; allocation plan; confidence floor behaviour |
| FE-1 | Approval UI, decision history + frozen-evidence viewer, calendar, impact panel |
| FE-2 | Farmer notifications, calendar, boundary verification pass |

**Gate @ 52h:** the full killer-demo sequence (SRS §8.1, steps 1–10) runs end to end.

### Phase 4 — Hours 52–66 · Hardening

- Nine invariant tests green (M21).
- Replay test green — proves module purity.
- Seed determinism verified: `make seed` twice → identical hashes.
- Offline run verified: full demo with network disabled, on fixtures.
- Hindi pass: no untranslated English fragments in the farmer view.
- Performance: dashboard p95 ≤2 s; packet completes ≤30 s.
- `DEMO DATA` labelling audit across every screen and export.

### Phase 5 — Hours 66–72 · Pitch

- Demo rehearsed three times, timed, with a scripted failure recovery.
- Backup: recorded video + a seeded database snapshot that reproduces the exact demo state.
- Slides: problem → the ₹ leakage → the decision loop → live demo → auditability → impact
  metrics → ethics (consent, boundary, ecosystem fund) → what's next.
- One-pager for judges with the architecture diagram and the invariant table.

---

## 6. Demo script {#demo-script}

**Setup:** seeded organization **"Prayagraj Kisan Producer Company Limited"** — 1,000 farmers,
2,412 acres across the district's three tracts (Ganga-par, doab, Yamuna-par), 5 crops
(paddy, wheat, potato, mustard, guava), 1,282 active Kharif cycles, 8 buyers, 5 aggregated
lots, 9 buyer offers anchored to real modal prices, 8 deliberate data conflicts.
Full profile: `docs/DEMO-CONTEXT.md`.

Everything the demo asserts about the *outside world* is real: 23,460 Agmarknet price rows
from five real Prayagraj markets, 2,439 days of Open-Meteo weather at three tract points, and
30 years of ERA5 hazard climatology. Everything about the *collective* is synthetic and
labelled as such on every screen.

**Run it:** `make seed && make dev`. The whole path works with the network disconnected
(NFR-303) — there is a test that runs the pipeline with sockets blocked.

| # | Beat | What the judge sees | Time |
|---|---|---|---|
| 1 | CEO logs in | 10-card dashboard + morning briefing: *"7 items need attention"*, priority-ordered, each with quantified impact | 0:30 |
| 2 | The question | *"What should we do this season to maximize sustainable farmer income?"* — typed, or spoken in Hindi | 0:15 |
| 3 | The packet streams | Nine sections appear in order. Every number has a confidence chip. | 1:00 |
| 4 | **The override moment** | The banner above the recommendations: *paddy is 99% of operated area across 749 farmers; it harvests into the annual price trough (₹20.30/kg in November against ₹23.69 in January); November arrivals run 36.6× the median month; and on both irrigated tracts it ranks last of four on return per rupee.* Four findings, two independent modules, same crop, same window. **Nobody proposed this cropping pattern — it is simply what is planted, which is why it would otherwise go unexamined.** The packet prices the alternative and explicitly declines to tell the board what to grow — and the finding itself notes that assured procurement and food security are real reasons to grow paddy that the cost model does not price. | 0:40 |
| 5 | **Provenance moment** | Hover a number → source, observed date, verification status. Click a disputed plot area → three conflicting claims (farmer 2.0 ac / record 1.6 / officer 1.8), no silent winner. | 0:30 |
| 6 | Drill-down | The packet's drill-down resolves to 749 named farmers → their plots → crop cycles → health readings, each with its own provenance. Filter the member list by tract to see the exposure cluster. | 0:40 |
| 7 | Market depth | Headline price versus what the collective actually banks. The punchline is *which* cost does it — not the 180 km of freight (₹0.81/kg) but the rejection rate (₹3.74/kg on ₹34), four times as much. Second punchline: months of accrued storage are shown and **deliberately not deducted** — sunk cost cannot inform a choice between buyers, and subtracting it once turned a fair ₹7.05/kg offer into a ruinous-looking ₹3.23. | 0:45 |
| 8 | Approve with modification | ₹35,000 → ₹32,000. Both values persist. Tasks and calendar events are created, pending field approval. | 0:30 |
| 9 | **Boundary moment** | Switch to a farmer token. They see their own crops in Hindi and English — and get **403 on the dashboard, the member list, the buyer negotiations and the decision history**. Show the status codes, not just the screen: the farmer view is built farmer-scoped from the start, so org-internal rows are never in the result set for a rendering bug to leak. | 0:45 |
| 10 | *(cut)* | Voice was descoped — see §4. The bilingual farmer portal ships; telephony does not. | — |
| 11 | **Audit moment** | Open a stored decision. The frozen-evidence panel shows the SHA-256 hash, the module versions and the coefficients in force — then **replays the packet from those bytes alone and reports whether it still matches**. "Explainable forever" is a claim most systems make and none can check; here it is a row on the page that is able to say no. | 0:40 |
| 12 | Learning loop | Approve with a modified value (₹35,000 → ₹32,000): both numbers persist, and it is recorded as a *modification* so the system does not learn that its figure was accepted. Then the attribution rule: advice that was never followed is **not scored as failed**, and a favourable season **confounds** a good outcome rather than confirming it. | 0:40 |
| 13 | Impact | The panel reports what it *could not* attribute as prominently as what it could. On a fresh install every figure is zero, and that is the correct thing to show. | 0:20 |

**Optional beat (if S1 ships):** late-blight outbreak clustering across the doab potato belt —
47 farms reporting similar symptoms in a humid window, geographic cluster detected, FPO alerted
before the spread. Slot after beat 6. This is the strongest available demonstration that we are
detecting *organizational* risk rather than classifying a leaf.

**Total ≈ 7 minutes.** Beats 4, 5, 9, 11 and 12 are the ones that separate this from a
dashboard with a chatbot. If time is cut, drop 7 and 13 — never 4, 5, 9 or 11.

**The line that ties it together, and it is true rather than a slogan:** every number on
every screen can be traced to an observation or a fetched payload; every recommendation is
frozen with the evidence that produced it; and nothing at all happens until a named human
holding a named role says so. The invariant tests in `apps/api/tests/test_invariants.py` are
what make that checkable — including one that asserts an unapproved recommendation *cannot*
execute, and one that runs the entire pipeline with every socket blocked.

---

## 7. Risk register for the build itself

| Risk | P | Impact | Mitigation | Trigger |
|---|---|---|---|---|
| Provenance layer overruns | M | Fatal — everything depends on it | Built first, hours 6–18, by the strongest backend person | Not done by hour 20 → drop decay, keep source+timestamp+verification only |
| LLM latency > 30 s | M | High | Parallel modules, SSE streaming, per-request gather cache | Hour 36 → precompute the demo packet nightly and stream from cache, labelled |
| Seed data reads as fake | M | High | Cited coefficients, fitted distributions, honest `DEMO DATA` labelling | Hour 30 review with fresh eyes |
| **A fabricated Prayagraj detail is spotted** (invented mandi name, wrong zone, lapsed scheme) | M | **High** — discredits every other number on screen | `seed/sources.md` gates the seed; district facts marked ⚠️ in `DEMO-CONTEXT.md` must be verified or dropped | Any seed value without a source row |
| No local sanity-check available (O-2 unanswered) | M | Medium | Keep the ⚠️ markers honest; if no contact is found, present district specifics as illustrative rather than authoritative | Hour 30 |
| Scope creep to the full vision | **H** | High | This document; POST-MVP requires a `context.md` entry | Any commit touching a cut item |
| External API down at demo time | M | Fatal | Full fixture fallback; offline run verified at hour 60 | Always demo on fixtures |
| Three channels dilute all three | **H** | Medium | Graded depth (§2); WhatsApp go/no-go at hour 24 | Hour 24 |
| Person-down (illness, other commitments) | M | High | No single-owner module; contracts frozen at hour 6 so anyone can pick up a stub | Any 6h silence |

---

## 8. Definition of done

The MVP is done when all of the following are true:

- [ ] `make seed && make dev` reproduces the demo with the network disabled
- [ ] All 13 demo beats run without intervention
- [ ] The nine invariant tests pass
- [ ] The replay test passes (module purity proven)
- [ ] Seed is deterministic: two runs produce identical content hashes
- [ ] No untranslated English in the Hindi farmer view
- [ ] Every synthetic value carries a `DEMO DATA` marker
- [ ] Every non-synthetic value in `seed/` has an `OK` row in `seed/sources.md`
- [ ] No ⚠️ item from `DEMO-CONTEXT.md` §10 remains unverified in shipped data or the pitch
- [ ] Dashboard p95 ≤ 2 s; Decision Packet ≤ 30 s
- [ ] Every MUST requirement in `SRS.md` is implemented or explicitly listed here as descoped
- [ ] `context.md` records every deviation from this plan
