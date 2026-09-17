# ADR-0011 — Conversational assistant: routing, response shapes, and the NIM provider

Date: 2026-08-23 · Status: Accepted · Amended by ADR-0020 (model), ADR-0021 (ambiguity), and
ADR-0022 (provider)

## Context

The `Ask` feature answered every question with the same nine-section Decision Packet. The
question only ever reached `engine.plan_for()`; `reconcile()` never saw it. Four of the eight
questions the product brief lists for an FPO CEO matched no `PLAN_HINTS` keyword and fell
through to "run all six modules and return a crop plan" — so *"which farmers require
attention?"* was answered with a season-long cropping recommendation.

Three further gaps: no conversation state of any kind, so "why did you say that?" could not be
answered; no farmer assistant at all (`_require_org` rejects farmers outright); and
`intelligence/funding.py`, the `announcement` table and `DecisionPacket.schedule` were all
written-but-unreachable.

We also had no Anthropic key available and needed to run on NVIDIA NIM.

## Decision

**Four response shapes, not one.** `DECISION` (full packet, `EvidenceSnapshot` frozen,
`Recommendation`s written at `SUGGESTED`), `LOOKUP` (a `list[Claim]`, nothing persisted beyond
the turn), `EXPLAIN` (a read over a frozen anchor packet), `REFUSE`. Freezing a snapshot for
"which farmers need attention" would devalue the snapshot for the decisions that need one.

**`LOOKUP` reuses `Claim` verbatim.** Not a new type. `Claim.evidence` is `Field(min_length=1)`,
so citation stays enforced at the schema level, and one renderer plus one grounding validator
serve both response paths.

**Routing is an LLM classifier over a closed set.** A small model maps the question to
`{shape, lookup, modules, entities}`, where `lookup` comes from a twelve-item enum and
`modules` from `engine.MODULES`. No query generation. Anything unmapped falls through to
`DECISION` — a worse-fitting answer, never a wrong one. The keyword planner survives as the
fallback.

**Review splits in two.** *Grounding* is deterministic: every magnitude and evidence ref in the
rendered answer must resolve to the result that produced it, or the reviewed output is
discarded. *Relevance* is an LLM **selector** that orders and selects but may never rewrite or
delete, with a protected floor — overrides, below-floor confidence, safety text — always
rendered.

**Provider: NVIDIA NIM over `httpx`,** not the OpenAI SDK. Two call sites do not justify a
dependency, and `httpx>=0.27` is already required.

**Router model: `meta/llama-3.1-8b-instruct`.** *Retired by NVIDIA on 2026-08-26; see
ADR-0020. The reasoning below stands — a small model over a closed enum — but this id and
both rows of the latency table are dead.*

## What the spike measured

Run against `integrate.api.nvidia.com/v1` on 2026-08-23, before any of the above was built.
**Both Llama rows were retired on 2026-08-26 and now return 410** — kept as the record of
what was measured, not as a menu. ADR-0020 has the current numbers, and notes that this
table measures raw `/chat/completions` latency rather than latency through `router.plan`,
which is where the models differ by 8×.

| Model | Latency (10 tokens, repeated) |
|---|---|
| `meta/llama-3.3-70b-instruct` | 56.4s, 47.6s — steady state, not cold start |
| `meta/llama-3.1-8b-instruct` | 617ms, 441ms |
| `mistralai/mistral-7b-instruct-v0.3` | HTTP 404, unavailable |

Structured output, on the 8B:

| Rung | Result |
|---|---|
| `response_format: json_schema` | ✅ ~1s, correct object shape, enum on `shape` honoured |
| `response_format: json_object` | valid JSON, schema **entirely ignored** — the format does not convey it |
| plain prompting | echoed the schema definition back as its answer |

Two findings changed the design. **Enums must be inside the JSON schema**: with `lookup` typed
as a bare string the server enforced structure but not vocabulary, and the model returned
`lookup: "FARMER"` — not a valid key. And **the prompt-side rungs must name the echo failure
explicitly**, because "reply matching this schema" is read by a small model as "reply with this
schema" a meaningful fraction of the time.

## Consequences

**Easier.** The right question gets the right answer shape. Follow-ups are a read over frozen
bytes, so "why?" cannot produce a different answer than the one it explains. The farmer
assistant becomes possible without weakening INV-5, because `lookups/fpo.py` and
`lookups/farmer.py` share no query code. `NFR-303` survives: with no key at all the router
falls back to keywords, the selector renders everything, and the whole chat still works.

**Harder.** Two response shapes mean two renderers and two test paths. The router is a new
failure mode, mitigated by the fallback ladder but not eliminated. A 12-item enum is a thing to
maintain, and every new lookup is a code change rather than a prompt change — accepted
deliberately, as the alternative is text-to-SQL.

**Costs.** One extra model round trip (~500ms–1s) before work begins, covered by streaming the
router's decision to the UI immediately. An 8B classifier will misroute sometimes; the closed
enum bounds the damage to "wrong shape", never "wrong data", and validation against
`lookups_for(audience)` means it can never misroute *across the information boundary*.

**Rejected.** An LLM orchestrator that chooses recommendations — it forfeits INV-2 replay, the
offline demo, and injection containment, all three of which `narrator.py` already refused this
trade for. A generic LOOKUP handler over generated SQL. A service-layer refactor of
`dashboard.py`, which would rewrite code under 354 passing tests for no demo-visible gain.
