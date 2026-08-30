# ADR-0021 — An ambiguous question refuses; it does not decide

Date: 2026-08-30 · Status: Accepted · Amends ADR-0011

## Context

ADR-0011 gave the router four shapes and one escape hatch: anything that fails validation
falls through to `_fallback`, which for staff is hardcoded to `shape=DECISION` with modules
from the keyword planner. That escape hatch serves three different situations, and it turns
out they are not alike.

The router's system prompt forbids `LOOKUP` with a null key — *"do not answer with LOOKUP and
a null key, which is not a valid classification"* — and `_validate` enforced it by returning
`None`. But a model that emits `{"shape":"LOOKUP","lookup":null}` is not malfunctioning. It is
saying *"the question asks what is true, and none of these keys is what it asks for"*. That is
a well-formed judgement about an underspecified question, and it was the model's only way to
express one, since the enum has no `CLARIFY` member.

Treating that judgement as a validation failure sent the turn to `_fallback`, so the heaviest
possible response was produced for the vaguest possible input. Measured on 2026-08-30 with
`openai/gpt-oss-20b`, six runs each:

| Question | Full Decision Packet |
|---|---|
| "how many" | 4 / 6 |
| "show me" | 2 / 6 |
| "tell me" | 1 / 6 |

Seven times in eighteen, a two-word fragment froze an `EvidenceSnapshot` and wrote
`Recommendation` rows at `SUGGESTED`. Nothing was unsafe — INV-1 still requires a human to
approve anything, and the packet was fully evidenced — but the decision history accumulated
packets for questions nobody asked, which devalues the snapshot for the decisions that need
one, the same argument ADR-0011 used to keep `LOOKUP` from freezing snapshots at all.

## Decision

**`LOOKUP` with a null key resolves to `REFUSE`, not to a fallback.**

One line in `_validate`, where the plan was previously discarded. The turn is still a real
routed answer — `fell_back` stays `False`, because the model answered and we understood it.

**The other two paths into `_fallback` are unchanged.** No key configured, and a provider that
has gone away, both keep the keyword planner and its `DECISION`. This is deliberate and is the
whole reason the change is one line rather than a rewrite of `_fallback`: NFR-303 requires a
keyless deployment to *answer*, degraded, rather than refuse everything. ADR-0020 is the
cautionary case — when the provider retired our model, keyword fallback gave wrong-shaped
answers for four days; refusing every question for four days would have been worse.

## Consequences

**Easier.** Fragments stop producing decision records. Re-measured over 24 runs after the
change: zero Decision Packets, against seven in eighteen before. `packet_id` and
`content_hash` come back null, and no `Recommendation` rows are written.

**Unchanged.** `make routing-eval` scores 63/64 (98%) before and after — this path is not
exercised by questions a real person types, which is exactly why it went unnoticed.

**Harder — and this is the honest limitation.** The refusal a user now sees is
`STAFF_REFUSAL`: *"That is outside what this assistant covers. I can answer about this
collective's members, crops, production, risks, buyers, schemes and working capital."* For
"how many" that lists the right next steps but misdescribes the problem: the question is not
outside what the assistant covers, it is underspecified. The correct answer is *"how many
what — members, plots, or tonnes?"*, and there is no shape that can say it. A `CLARIFY` shape
is the real fix and is deliberately not in this change.

Two related gaps stay open, both documented here so they are not rediscovered as bugs:

- **Bare nouns are answered confidently rather than questioned.** "farmers" routes to
  `MEMBERSHIP_SUMMARY` at confidence 1.00, six times in six. The model is not signalling
  ambiguity, so this path never reaches the code above.
- **Mixed-scope questions silently drop the out-of-scope half.** "how many farmers are there
  with us along with dynamic programming solutions" answers the count and never mentions the
  rest. The prompt instructs this — *"If any offered key matches the question, use LOOKUP with
  that key"* — and there is no way to express a partial answer.

`_unknown_crop` already demonstrates the idiom both gaps want: name what is missing, then name
what can be asked instead. It is special-cased to crops.

## Alternatives considered

**Make `_fallback` itself return `REFUSE`.** Rejected — it breaks NFR-303. A deployment with no
model key would refuse every question instead of degrading to keyword routing, and the
ADR-0020 outage would have been an outage rather than a degradation.

**Allow `LOOKUP` with a null key through to the lookup layer.** Rejected: every lookup needs a
key to dispatch on, so this only moves the failure later and makes it a crash instead of a
shape.

**Add the `CLARIFY` shape now.** Deferred, not rejected — it is the right answer to both open
gaps above. It is a contract change (a fifth `ResponseShape`, a renderer, regenerated TS
contracts, an SRS entry) rather than a one-line correction, and bundling it here would mean
shipping the fix for a measured defect behind a design discussion. Filed as the follow-up.

**Leave it.** Rejected. A vague fragment writing recommendations into decision history is the
failure ADR-0011 was written to eliminate, arriving by a different route.
