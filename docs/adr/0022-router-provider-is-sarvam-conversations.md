# ADR-0022 — Router provider: Sarvam, on the `-conversations` model, not the flagship

Date: 2026-09-16 · Status: Accepted · Amends ADR-0011 (provider) and ADR-0020 (model)

## Context

ADR-0011 put the intent router and the relevance selector behind NVIDIA NIM because no
Anthropic key was available at the time. ADR-0020 already lived through the cost of that
choice once: NVIDIA retired the router's model underneath a running system, silently, and
`orchestrator/llm.py`'s own fallback ladder made the failure indistinguishable from "no key
configured" — the exact regression ADR-0011 was written to remove.

Sarvam was proposed as a replacement provider, motivated by its dedicated Indic-language
models — relevant to a future caller of this same `llm.py` chokepoint (a Hindi-language
farmer `Ask` path does not exist yet; today the router classifies English/Hinglish text
against a closed enum and the UI's Hindi/English strings are hand-written, not model-derived,
so this motivation is forward-looking, not a current requirement). The more immediate driver
is ADR-0020's own rejected alternative — "pin a provider-independent model" — which named no
Anthropic key as the blocker. That blocker still holds (`AGRI_ANTHROPIC_API_KEY` is empty in
this deployment); Sarvam is the provider with a live key where Anthropic is not.

`llm.py` is a single chokepoint by design: both callers (`router.py`, `review.py`) go through
`structured(system, user, schema) -> dict | None`, and provider selection lives entirely in
two functions plus three `Settings` fields. Adding a provider should be additive there, not a
rewrite — that is what got measured.

## Decision

**Provider: Sarvam. Model: `sarvam-105b-conversations`, not `sarvam-105b`, on `/v1`.**

Three options were measured against the real router payload — long system prompt, JSON
schema, closed enum — per ADR-0020's own rule that raw `/chat/completions` latency does not
predict this.

| Model | Endpoint | Direct-call latency | `routing-eval` |
|---|---|---|---|
| `sarvam-105b` (128K, flagship) | `/v1` | 3.65s (single call, minimal schema) | 2 workers: 46/46 correct **among calls that reached the model** — but 18/64 (28%) timed out and fell back. 1 worker (serialized, to rule out concurrency): still timed out on nearly every call across all 3 payload rungs; run did not finish in 53 minutes and was stopped. |
| `gemma4` / `glm5.2` / `deepseekv4-flash` (open-source) | `/v2` | — | Not reachable: `400 invalid_request_error`, *"this endpoint is currently in beta and not available"*, on every call on this account. |
| `sarvam-105b-conversations` (32K) | `/v1` | 1.0–1.2s (3 direct calls) | **63/64 (98%)**, default 2 workers. One miss (*"can I get the kisan credit card"* → `REFUSE`, wanted `MY_SCHEMES`) — a model miss, not a plumbing one, and the same order of magnitude as the single miss ADR-0020 accepted for the model it shipped. No case fell back to keywords. |

`sarvam-105b` failing under **one worker, serialized**, rules out rate-limiting or
concurrency contention as the cause — it is the model's own latency against this payload
shape, the same trap ADR-0020 names: *"raw single-token latency ... matching the 8B it
replaces. The 8x spread only appears under the router's real payload."* The 128K flagship
pays for context and reasoning capacity the router's closed-enum classification does not use.

`gemma4` would likely have been the better architectural fit — its own docs state it "answers
directly, never returns `reasoning_content`," the same non-reasoning shape ADR-0020 selected
`gpt-oss-20b` for over NVIDIA's reasoning-tier nemotron models. It is not usable today because
the account has no beta access to `/v2`.

`router_timeout_seconds` **stays at 8.0.** `sarvam-105b-conversations`'s worst observed call
is ~1.2s, comfortably inside it — no timeout change needed, unlike the alternative below.

## What building this surfaced

The provider dispatch in `llm.py` had a bug mid-edit before this ADR: the Sarvam branch of
`structured()` was `return bool(settings.sarvam_api_key)` — returning a boolean where every
caller expects `dict[str, Any] | None`. Both callers would have silently received `True`
where they expected a parsed plan or a claim list. Fixed by generalizing the two providers to
one dispatch — `base_url, api_key` selected per provider, one request path, matching the
docstring's own reasoning that two call sites do not justify per-provider branching beyond
that. Sarvam's `/chat/completions` takes the same `Authorization: Bearer` header and the same
`response_format` ladder (`json_schema` → `json_object` → plain) as NVIDIA NIM, so nothing in
the ladder itself changed.

Separately — not a code decision, but worth recording since it nearly became one: a live
Sarvam key was committed into `.env.example` (tracked) instead of `apps/api/.env` (gitignored,
what `config.py` actually loads). Caught and moved before commit. No production consequence,
but it is the second time in this project's history a secret nearly landed in the repo by
going in the file that looks like the real one rather than the one `_ENV_FILE` resolves to.

## Consequences

**Easier.** Router accuracy holds at parity with the NVIDIA baseline this replaces — 98%
both. No header, parsing, or ladder change in `llm.py`; a provider switch is a three-line env
change (`AGRI_LLM_PROVIDER`, `AGRI_SARVAM_API_KEY`, `AGRI_ROUTER_MODEL`), same as ADR-0011
intended. The account now has a working path to Sarvam's Indic-language models for whichever
caller eventually needs one — not exercised yet, but no longer blocked on plumbing.

**Harder.** `sarvam-105b-conversations` is not documented by Sarvam as "the fast router
model" the way `gpt-oss-20b` was measured and chosen for that role in ADR-0020 — it was found
by elimination (flagship too slow, open-source tier inaccessible) rather than by a vendor
signpost. If Sarvam retunes or retires it, the failure mode is exactly ADR-0020's: silent
fallback to keywords, `fell_back` on the routing event the only signal. That alerting gap is
still open (ADR-0020's own accepted follow-up) and this change does not close it.

**Accepted.** The `/v2` open-source models are the better long-term fit and are deliberately
left unused — revisit once beta access is granted, and re-measure rather than assume gemma4's
"no reasoning pass" claim holds up under the real payload, per the same rule this ADR just
applied to the 105B flagship. NVIDIA config (`nvidia_api_key`, `nvidia_base_url`) stays in
`Settings` and `.env.example` as a working, documented fallback — not removed, since ADR-0011
already made provider switching a one-line change and there is no reason to spend that back.

## Alternatives considered

**`sarvam-105b` (flagship).** Rejected — measured, not assumed: near-universal timeouts on
the router's real payload even fully serialized, which rules out concurrency as the cause.

**`gemma4` / the open-source `/v2` tier.** Rejected for now, not on merit — inaccessible
(`400`, beta-gated) on this account. The best fit on paper; re-measure once available.

**Raise `router_timeout_seconds` and keep `sarvam-105b`.** Rejected on the same grounds
ADR-0020 rejected it for `nemotron-3-nano`: it puts a multi-second model on the critical path
of every question, which is worse than the keyword fallback it exists to avoid.

**Keep NVIDIA (`gpt-oss-20b`).** Not wrong — still measured at 98%/1.34s median in ADR-0020 —
but superseded here because Sarvam clears the same bar while opening a path to Indic-language
models on a provider not yet exercised anywhere else in the stack.
