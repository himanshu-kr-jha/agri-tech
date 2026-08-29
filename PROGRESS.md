# AgriVardhak — Progress

The single place to see what is built and what is left.

This file has **two layers, and they work differently**:

| Layer | Written by | What it says |
|---|---|---|
| **Intent** (this section) | Humans | What we are building next, what is blocked, and why |
| **Reality** (below the marker) | `make progress` | What the repository can actually *prove* is done |

The reality layer is generated from evidence — a symbol that must import, a test that must
pass, a row count that must hold. **You cannot mark something done by editing the table.**
That is the point: a hand-maintained progress board drifts from the code within days, and a
board nobody trusts is worse than no board.

```bash
make progress          # regenerate
make progress-check    # exit 1 if stale (suitable for CI)
```

---

## Right now

**All 44 MUST deliverables are built and evidenced.** The demo runs end to end: a CEO asks a
question, gets an evidence-backed Decision Packet, approves a recommendation with a modified
value, and the system records who authorised what under which role. It runs with the network
disconnected.

**What the last stretch produced, and what it cost:**

Six intelligence modules, an orchestrator that reconciles them, an approval lifecycle that
makes INV-1 structural rather than documented, and eight screens. Along the way the real data
contradicted the plan four times, and each correction is recorded rather than patched over:

| What we assumed | What the data said | What changed |
|---|---|---|
| Unseasonal rain in the Feb potato window, p = 0.71 | **p = 0.167** from 30 years of ERA5 | The demo moved from a weather story to a price story, which is what the evidence supports (`docs/ARCHITECTURE.md` §5.2) |
| An override means the AI's proposal was wrong | 99% of area was already in one crop **nobody proposed** | The reconciler now overrides the *status quo* too — usually the more valuable half |
| Storage cost belongs in effective price | It made a fair ₹7.05/kg offer read as ₹3.23 | Sunk cost is reported, never deducted: it is identical under every option, so it cannot inform a choice |
| A guava orchard returns 11× per rupee | Perennial costs had been copied from annual crops | Perennials are reported separately and never ranked against annuals |

**Since then — the external corpus is wired (ADR-0018).** Ten cached public sources had been
fetched, hashed and committed, and read by nothing; `docs/DATA-SOURCING-HANDOFF.md` called it
*"gathering done, nothing wired"*. All six batches now land as `ExternalRecord` rows, and the
Data Observer turns the text-bearing ones into retrievable, cited passages. Three things
changed that a user can see:

- **`DR-07` is satisfied.** pgvector was created at initdb on day one and never used. Retrieval
  is now hybrid — vectors plus Postgres full-text, fused by rank — and an English question
  reaches a Hindi order (measured cross-lingual similarity 0.795).
- **The Risk module stopped disclaiming a capability it now has.** `risk.py` hardcoded
  *"policy and procurement change is not modelled — no scheme feed yet"*. It reports evidenced
  POLICY findings from real UP government orders instead.
- **"What has changed?" reports government activity**, not only price moves and conflicts.

What it deliberately did *not* do is lift a single confidence cap. Nine of ten licences are
unconfirmed, so that text is capped at 0.40 — below the orchestrator's 0.45 floor — and can
inform without deciding. ADR-0014 requires a named human, and no code path can substitute.

**Next, if there is time:** S2 (sell-now vs hold with a break-even) is the highest-value
remaining item — the seasonal spread the data already shows is ₹10/kg in February against
₹19.50 in November, and quantifying the storage trade-off against it is a genuine answer to
"what should we do this season".

---

## Blocked / needs a human

| # | Item | Blocks | Who can unblock |
|---|---|---|---|
| **O-2** | A Prayagraj-area FPO contact or agronomist to sanity-check the district profile | Credibility of every agronomic number | You. One conversation catches more than the whole `seed/sources.md` checklist. |
| **P1–P7** | Crop-protection knowledge base against a cited authority | Every diagnosis is capped at 0.42 confidence — deliberately below the orchestrator's floor, so it cannot drive a recommendation | Anyone, via `seed/sources.md` §13 |
| **E1–E6** | Cost of cultivation from a cited survey | Farm economics are capped at 0.62 and labelled synthetic on every screen | Anyone, via `seed/sources.md` §12 |
| **A1–A16** | Yield, damage-ratio and integrated-farming coefficients | Production and risk figures are plausible but unsourced | Anyone, via `seed/sources.md` §4 and §12 |
| **L1–L9** | Licence confirmation for the nine `UNKNOWN` sources in `seed/source_registry.py` | Every retrieved passage from them is capped at 0.40, structurally below the orchestrator's floor — readable as context, unable to drive a recommendation | Anyone who will read a portal's terms and put their name on it. **Cheapest unblock in the repository**, and ADR-0014 makes it un-automatable by design. |
| **O-3** | WhatsApp Business API sandbox | S5 only. Not on the demo path. | You. |
| **G3b** | Block→tract mapping (which side of which river) | Geographic precision in the drill-down | Anyone, from the district map |

Filling in **P1–P7** and **E1–E6** would do more for this system's credibility than any
further code. The caps are working as designed — they keep unsourced numbers out of
decisions — but a capped module is a module that cannot help much.

---

## Recently resolved

| Date | What |
|---|---|
| 2026-08-29 | **The fetched corpus is no longer inert.** 34,225 external records landed, 195 retrievable chunks, 74 real government orders as policy events. `DR-07`, `FR-403` and `FR-404` move from unimplemented to satisfied. |
| 2026-08-23 | **Every invariant is asserted.** The four `xfail` placeholders are gone; 305 tests pass with none skipped. |
| 2026-08-23 | **Offline demo proven, not assumed.** A test runs the whole pipeline with every socket blocked (NFR-303). |
| 2026-08-23 | **Replay is checkable in the UI.** A decision page rebuilds its packet from the stored snapshot and reports whether it still matches. |
| 2026-08-23 | **30-year hazard climatology derived** from ERA5 — and it corrected a fabricated probability in our own architecture doc. |
| 2026-08-22 | **Agmarknet unblocked.** Undocumented JSON API behind Agmarknet 2.0; five real markets, 23,460 price rows. |
| 2026-08-22 | **Agro-climatic zone corrected** — Central Plain, not Eastern Plain. Would have made every production figure wrong. |

---

## Known risks to the schedule

| Risk | Status |
|---|---|
| Provenance layer overruns | **Cleared** |
| LLM latency > 30s | **Cleared, and structurally.** The packet is produced deterministically in ~6 s; the model only narrates, and a failure returns the packet unchanged. |
| External API down at demo time | **Cleared.** Prices, weather and climatology are all cached payloads, and an offline test proves the path. |
| Seed reads as fake | Mitigated: real blocks, real market ids, real GI area, real prices and weather, `DEMO DATA` badges on everything synthetic |
| Scope creep toward the full vision | Held. The cut list in `docs/MVP-SCOPE.md` §4 was respected — voice and WhatsApp did not ship. |
| **Unsourced agronomy** | **Live, and now the main one.** The system is honest about it — every affected figure is capped and labelled — but honesty about a weakness is not the same as not having it. |

---

<!-- BEGIN GENERATED — do not edit below this line; run `make progress` -->

_Generated by `make progress`. Every row below is verified against the repository — a status cannot be set by editing this table._

## MVP progress: 55/55 MUST deliverables (100%)

```
████████████████████  100%
```

| | Done | In progress | Not started |
|---|---:|---:|---:|
| **MUST** | 55 | 0 | 0 |
| All | 56 | 0 | 3 |

### Repository facts

| Fact | Value |
|---|---|
| Test suite | green — 403 passed, 0 failed, 0 xfail placeholders |
| Database tables | 53 |
| Seeded farmers | 1,000 |
| Seeded crop cycles | 7,258 |
| Observations | 3,081 |
| Open discrepancies | 8 |
| Agmarknet backfill | 731 days, 23,460 price rows |
| External records | 60,127 |
| Knowledge chunks | 207 |
| Policy events | 74 |

### Phase 0 — Foundation (hours 0–6) — 7/7

| | ID | Deliverable | Requirements | Evidence |
|---|---|---|---|---|
| ✅ | M1 | Schema + Alembic migrations | `DR-01…09` | 2/2 checks |
| ✅ | M0a | Append-only enforcement (DB triggers) | `DR-04, INV-2` | 2/2 checks |
| ✅ | M0b | Module + DecisionPacket contracts | `FR-500, FR-801` | 3/3 checks |
| ✅ | M5 | Auth, roles and ContextScope enforcement | `FR-104, FR-809, NFR-401` | 5/5 checks |
| ✅ | M0c | FastAPI app + health | `API-01` | 1/1 checks |
| ✅ | M0d | Next.js app + invariant components | `UI-02, UI-04` | 1/1 checks |
| ✅ | M0f | Canonical units + conversions | `DR-02, ADR-0009` | 3/3 checks |

### Phase 1 — Provenance & data (hours 6–18) — 11/11

| | ID | Deliverable | Requirements | Evidence |
|---|---|---|---|---|
| ✅ | M2 | Provenance: trust, decay, resolution | `FR-301…307` | 4/4 checks |
| ✅ | M3 | Discrepancy detection + resolution | `FR-304, FR-305, INV-4` | 4/4 checks |
| ✅ | M4 | Seed: Prayagraj FPO, 1,000 farmers | `DR-09, C-2` | 5/5 checks |
| ✅ | M4b | Agmarknet ingestion + 24-month backfill | `FR-402, EXT-02` | 2/2 checks |
| ✅ | M4c | Weather ingestion + crop-stress index | `FR-401, FR-406` | 4/4 checks |
| ✅ | M6 | Quality Intelligence module | `FR-531…534` | 6/6 checks |
| ✅ | M7 | Market Intelligence module (effective price, scoring, allocation) | `FR-541…545` | 5/5 checks |
| ✅ | M7b | Market data plumbing: lots, offers, price ingestion | `FR-546, EXT-02` | 6/6 checks |
| ✅ | M15a | FPO dashboard: 10 cards | `UI-01` | 4/4 checks |
| ✅ | M15b | Farmer list + drill-down | `FR-806, NFR-103` | 4/4 checks |
| ✅ | M15f | Information boundary enforced at the API | `INV-5, FR-809` | 3/3 checks |

### Phase 2 — Intelligence (hours 18–36) — 13/13

| | ID | Deliverable | Requirements | Evidence |
|---|---|---|---|---|
| ✅ | M8 | Risk Intelligence module | `FR-551…555` | 1/1 checks |
| ✅ | M9 | Scheme Intelligence module | `FR-561…565` | 1/1 checks |
| ✅ | M10 | Farm Intelligence module | `FR-511, FR-512` | 1/1 checks |
| ✅ | M11 | Crop Health Intelligence module | `FR-521…526, INV-8` | 4/4 checks |
| ✅ | M8b | Hazard climatology (30y ERA5) + risk register | `FR-552, FR-554` | 2/2 checks |
| ✅ | M13a | Gather layer: database to pure module inputs | `FR-500, INV-3` | 6/6 checks |
| ✅ | M13b | Reconciliation: ranking + visible override | `FR-802, FR-804` | 5/5 checks |
| ✅ | M13 | Orchestrator + evidence freezing | `FR-801…806, FR-704` | 5/5 checks |
| ✅ | M13c | LLM narration, optional and off the critical path | `FR-807, NFR-302, NFR-303` | 2/2 checks |
| ✅ | M14 | Approval lifecycle | `FR-705…710, INV-1` | 5/5 checks |
| ✅ | M14b | Assistant + approval API | `API-05, FR-807, FR-705` | 4/4 checks |
| ✅ | M4d | Scheme catalog with official portals | `FR-403, FR-561` | 3/3 checks |
| ✅ | M0e | Domain-event outbox dispatcher | `DR-05, ADR-0007` | 3/3 checks |

### Phase 3 — The loop closes (hours 36–52) — 10/10

| | ID | Deliverable | Requirements | Evidence |
|---|---|---|---|---|
| ✅ | M12 | Funding requirement (thin) | `FR-601…606, SAF-04` | 3/3 checks |
| ✅ | M15c | Assistant view + SSE streaming | `API-05, FR-807` | 2/2 checks |
| ✅ | M15d | Risk register + market screens | `UI-08, FR-544` | 2/2 checks |
| ✅ | M15e | Decision history + frozen evidence viewer | `FR-710` | 2/2 checks |
| ✅ | M15g | Approval gate in the UI | `INV-1, UI-11` | 1/1 checks |
| ✅ | M16 | Farmer portal (Hi/En) | `UI-05, UI-06, FR-808` | 3/3 checks |
| ✅ | M17 | Unified calendar + approval gate | `FR-901…906` | 3/3 checks |
| ✅ | M18 | Outcome, adherence, attribution | `FR-1001…1004, INV-7, SAF-12` | 6/6 checks |
| ✅ | M19 | Morning briefing | `FR-811` | 2/2 checks |
| ✅ | M20 | Impact metrics panel | `FR-1201…1203` | 3/3 checks |

### Phase 4 — Hardening (hours 52–66) — 3/3

| | ID | Deliverable | Requirements | Evidence |
|---|---|---|---|---|
| ✅ | M21 | Every invariant asserted, no placeholders | `SRS §8.2` | 8/8 checks |
| ✅ | M22 | Replay test (module purity) | `ARCHITECTURE §9, INV-2` | 5/5 checks |
| ✅ | M23 | Offline demo run (no network) | `NFR-303` | 2/2 checks |

### Phase 5 — Conversational assistant (docs/adr/0011) — 6/6

| | ID | Deliverable | Requirements | Evidence |
|---|---|---|---|---|
| ✅ | M24 | Assistant contracts + NIM provider adapter | `FR-807, NFR-302` | 4/4 checks |
| ✅ | M25 | Intent router with keyword fallback | `FR-807, NFR-303` | 3/3 checks |
| ✅ | M26 | Named lookups, organization and farmer | `FR-806, INV-5` | 5/5 checks |
| ✅ | M27 | Review gate: deterministic grounding, order-only selector | `FR-802, FR-804` | 4/4 checks |
| ✅ | M28 | Chat endpoint + conversation turns | `API-05, FR-709` | 6/6 checks |
| ✅ | M12b | Funding intelligence reachable + announcements shared | `FR-601…606, FR-105, INV-5` | 2/2 checks |

### Phase 6 — Data Observer: the external corpus (docs/adr/0018) — 5/5

| | ID | Deliverable | Requirements | Evidence |
|---|---|---|---|---|
| ✅ | M29 | External records: all six fetched batches landed | `FR-405, DR-08, ADR-0013` | 4/4 checks |
| ✅ | M30 | Data Observer: classify, segment, embed, index | `DR-07, FR-403, ADR-0015` | 10/10 checks |
| ✅ | M31 | Policy events from the government-order stream | `FR-404, FR-551, D-13` | 5/5 checks |
| ✅ | M32 | Knowledge search screen + the licence marker in the UI | `DR-07, UI-04, ADR-0014` | 3/3 checks |
| ✅ | M33 | Farmer-facing government notices, Hindi-first | `UI-05, UI-06, FR-808, INV-5` | 6/6 checks |

### Stretch — build if ahead of schedule — 1/4

| | ID | Deliverable | Requirements | Evidence |
|---|---|---|---|---|
| ✅ | S1 | Outbreak clustering | `FR-525` | 3/3 checks |
| ⬜ | S2 | Sell-now vs hold + break-even | `FR-547` |  |
| ⬜ | S3 | Supply/demand gap | `FR-548` |  |
| ⬜ | S5 | WhatsApp inbound Q&A | `ADR-0008` |  |

---

**Adding a deliverable:** add a `Deliverable(...)` to `scripts/progress.py` with the evidence that proves it — a symbol that must import, a test that must pass, or a row count that must hold — then run `make progress`. A row with no evidence stays ⬜ regardless of what anyone writes here.

<!-- END GENERATED -->
