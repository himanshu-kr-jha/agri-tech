# ADR-0006 — Deterministic intelligence modules under an LLM orchestrator

Date: 2026-08-22 · Status: Accepted

## Context

Discovery rejected the "one giant prompt that analyzes everything" design in favour of six
specialized intelligence modules with an orchestrator above them. What was left open is *what
the modules are made of*: trained ML models, LLM calls, or deterministic code.

Three constraints bear on this:

1. **72 hours.** Training and validating yield, price and disease models is not achievable, and
   an undertrained model is worse than no model.
2. **INV-2 and the replay property.** Every recommendation must be reproducible from its frozen
   evidence snapshot. A non-deterministic module cannot be replayed.
3. **INV-3 and explainability.** Every number needs an evidence trail. An LLM asked to compute
   an effective price will produce a plausible number with no derivation.

## Decision

**The six intelligence modules are deterministic pure functions.** No I/O, no clock, no network,
no database access — inputs are gathered by the orchestrator and passed in. Every coefficient
comes from a cited source in `seed/agronomy/`; none are invented in code.

**The LLM makes exactly two kinds of judgement:** which modules a question needs (planning), and
how to reconcile, prioritize, override and narrate their findings (synthesis). Its synthesis
output is schema-constrained tool use, never parsed free text.

Every claim in a Decision Packet carries an `EvidenceRef`. Claims without one are dropped before
rendering, so an invented number cannot reach the user.

## Consequences

**Easier.** Every number in a packet is reproducible and derivable. Golden-file tests over the
seeded scenarios become trivial. A replay test — re-running a module against a stored snapshot
and diffing byte-for-byte — proves the whole architecture holds. Modules run concurrently. A
judge asking "how did you get 82%?" gets a formula, not a shrug.

**Harder.** The formulas must be written and sourced, which is real work — and they will be less
accurate than a well-trained model would eventually be. The "AI" claim is narrower: the
intelligence is in the orchestration and the data model, not in a trained network.

**Accepted.** We would rather defend a system that is transparently right than one that is
opaquely approximate. The module contract is designed so a deterministic formula can be swapped
for a trained model later without touching the orchestrator: same `ModuleInput`, same
`ModuleOutput`, bumped `version` string recorded on every recommendation.

## Alternatives considered

- **Trained ML models in the MVP.** Rejected on schedule and defensibility. Retained as the
  first post-hackathon upgrade, with the module contract already shaped for it.
- **LLM-driven modules with tool access.** Fastest to build and demos superficially well.
  Rejected: destroys determinism, replay, evidence trails and golden tests — the four properties
  the product's credibility rests on.
- **Hybrid — deterministic core with an LLM fallback for missing data.** Rejected as a hidden
  non-determinism that would surface exactly when a judge probed an edge case.
