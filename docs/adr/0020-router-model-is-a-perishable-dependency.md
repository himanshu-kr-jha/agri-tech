# ADR-0020 — The router model is a perishable dependency

Date: 2026-08-30 · Status: Accepted · Amends ADR-0011

## Context

ADR-0011 chose `meta/llama-3.1-8b-instruct` as the intent router on measured evidence: 617ms
and 441ms against llama-3.3-70b's 56.4s, with `response_format: json_schema` honoured. That
measurement was taken on 2026-08-23 and was correct on the day.

**NVIDIA retired the model on 2026-08-26T09:00:00Z.** Every routing call since has returned:

```
410 Gone — The model 'meta/llama-3.1-8b-instruct' has reached its end of life
```

`meta/llama-3.3-70b-instruct`, the comparison point in ADR-0011's own spike table, was retired
in the same sweep. Both entries in that table are now dead.

Nothing alerted. The fallback ladder in `orchestrator/llm.py` retries three times, returns
`None`, and `router.plan` falls through to `_fallback(reason="model unavailable")` — which for
an FPO audience is hardcoded to `shape=DECISION` with modules from `engine.plan_for`. That is
precisely the behaviour ADR-0011 was written to remove: *"the `Ask` feature answered every
question with the same nine-section Decision Packet."* The regression restored the exact
failure the ADR exists to prevent, and did it silently.

Observed on 2026-08-30: *"which government schemes provide crop insurance to farmers"* — a
question `SCHEME_ELIGIBILITY` exists to answer — returned a full Decision Packet opening on the
November paddy price trough, with five recommendations spanning insurance, soil health, FPO
formation and mechanisation. The answer was internally consistent, fully evidenced, correctly
scoped, and about the wrong question. Retrieval was healthy throughout: 11 `knowledge_chunk`
citations landed in the packet. The failure was upstream of everything that looked suspicious.

The graceful degradation worked exactly as designed. That is the problem: NFR-303 is written
for *no key configured*, a state the operator chose. A model retired underneath a running
system is not that state, but it is indistinguishable from it at the call site.

## Decision

**Router model: `openai/gpt-oss-20b`.**

Re-run of ADR-0011's spike against `integrate.api.nvidia.com/v1` on 2026-08-30, plus this
repo's own `make routing-eval`:

| Model | Raw latency (10 tokens, ×2) | Router latency (median / max) | `routing-eval` |
|---|---|---|---|
| `openai/gpt-oss-20b` | 531ms, 541ms | **1.34s / 1.61s** | **63/64 (98%)** |
| `nvidia/nemotron-3-nano-30b-a3b` | 555ms, 503ms | 4.11s / 11.47s | 7/7 on the smoke set |
| `meta/llama-3.1-8b-instruct` | 410 Gone | — | — |
| `meta/llama-3.3-70b-instruct` | 410 Gone | — | — |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | — | 23.2s, fell back | — |
| `minimaxai/minimax-m3` | — | 21.4s, fell back | — |
| gemma-3-4b/12b-it, mistral-nemo-12b, phi-3.5-moe, zamba2-7b | 404 for this account | — | — |

Of 83 models the account can list, two are both reachable and usable for structured routing.

`router_timeout_seconds` **stays at 8.0**. gpt-oss-20b's worst observed routing call is 1.61s,
comfortably inside it. The reasoning models were rejected partly on this: nemotron-3-nano
routes correctly but its 11.47s worst case exceeds the timeout, so it would intermittently fall
back into the very bug this ADR closes — a fix that reintroduces the failure under load is not
a fix.

Note the shape of the trap: raw single-token latency is ~500ms for both survivors, matching the
8B it replaces. The 8× spread only appears under the router's real payload — long system
prompt, JSON schema, closed enums. **Latency must be measured through `router.plan`, not
against `/chat/completions` with "say hi".** ADR-0011's table measured the latter, which is why
it could not have predicted this.

**The default moves into code, not just config.** `config.py` carried the dead model as its
default, so a fresh clone was broken regardless of `.env`. `.env.example` now names
`AGRI_ROUTER_MODEL` explicitly rather than leaving it to an invisible default.

**`fell_back` is the first thing to check.** It was already streamed to the UI on the `routing`
event and already logged at WARNING. The signal existed and nobody was looking at it. Both
`config.py` and `.env.example` now say so at the point of use.

## Consequences

**Easier.** Routing works: 98% on the eval, and the reported question now answers with
*"Pradhan Mantri Fasal Bima Yojana: 400 members look eligible"* plus the three unrecorded facts
blocking 400 eligibility assessments. Latency improves on the original design target — 1.34s
median against ADR-0011's projected ~500ms–1s per round trip, in the same band.

**Harder.** We now depend on `openai/gpt-oss-20b` having the same expiry the last one did. This
ADR does not solve that; it documents the failure mode so the next occurrence is diagnosed in
minutes rather than mistaken for a prompt, embedding or rendering problem. The honest position
is that a hosted model id is perishable and our provider gives no deprecation signal we consume.

**Accepted.** Silent degradation stays silent. Making a dead model loud — a startup probe, or
surfacing `fell_back` as a banner — is the right fix and is deliberately not in this change,
which restores correct behaviour and leaves the alerting to a change that can be tested on its
own. Filed as the obvious follow-up.

**Unchanged.** No prompt, schema, enum, lookup, module or intelligence code was touched. The
router's design is not implicated; only the string naming its model.

## Alternatives considered

**Keep the timeout at 8.0 and adopt nemotron-3-nano.** Rejected: an 11.47s worst case against
an 8.0s timeout means intermittent fallback to the bug being fixed.

**Raise `router_timeout_seconds` to 30 and adopt nemotron-3-nano.** Rejected. It works — this
was the first fix tried and it did restore correct routing — but it puts a 4–11s model on the
critical path of every question to accommodate a model that is 3× slower than an available
alternative, and ADR-0011's rule still holds: a router slower than the work it schedules is
worse than the keyword planner it replaces.

**Pin a provider-independent model via Anthropic.** Rejected for this change: `AGRI_LLM_PROVIDER`
already supports it and the code path exists, but no key is available in this environment and
the demo must run on the NVIDIA tier. Worth revisiting — it is the only option here that makes
the router's availability something we control.

**Detect 410 specifically and fail loudly instead of falling back.** Rejected as bundled scope,
and it is the wrong shape: the router should degrade for *any* provider failure, not treat one
status code as special. The correct version is surfacing `fell_back` to the operator, which is
the follow-up above.

**Do nothing and let it fall back.** Rejected. Keyword fallback answers a lookup question with a
Decision Packet, which is the failure ADR-0011 was written to eliminate.
