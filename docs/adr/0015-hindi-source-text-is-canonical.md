# ADR-0015 — Hindi source text is canonical; translation is derived

Date: 2026-08-28 · Status: Proposed

## Context

`seed/sources.md` §7 lists the Uttar Pradesh state schemes (S9–S12) as `TODO`. Those schemes
are published in Hindi, on state portals, and largely nowhere else. Hindi is therefore not an
enhancement to scheme coverage — it is the only route to it. Central schemes have English;
state schemes frequently do not.

The obvious implementation is to translate on ingest and store English. That would place an
unverified transformation inside the chain that decides whether a farmer is told they qualify
for a benefit, and it contradicts the guarantee `Scheme` already makes: `eligibility_text` is
*"the original wording it was transcribed from... a rule we cannot trace back to published
text is a rule we should not be applying to someone's benefits."* If the published text was
Hindi and we store English, that traceability is void.

The risk is not hypothetical or cosmetic. **लघु एवं सीमांत कृषक** is a legal category tied to
specific landholding thresholds, not a descriptive phrase. A translator that renders it as
"small farmers" has destroyed the rule while producing fluent, plausible English — a failure
that is invisible to every downstream consumer.

## Decision

The Hindi original is **canonical and frozen** in `eligibility_text`.

- Translation is a **derived** field carrying its own provenance: translator identity and
  version, per INV-3.
- `eligibility_rules` are transcribed **from the Hindi**, by a human, under ADR-0014.
- Legal category terms get a maintained glossary (लघु/सीमांत कृषक, अनुसूचित जाति/जनजाति,
  कृषक दुर्घटना). A domain glossary beats a general translator precisely where fluency
  hides error.

## Consequences

Easier: the farmer-facing surfaces — the farmer assistant, WhatsApp, the Hindi UI — consume
the original rather than a round-trip through English. Keeping Hindi canonical removes a
translation hop rather than adding one.

Harder: a reviewer verifying a scheme rule must read Hindi. This is a real staffing
constraint and should be stated rather than discovered.

Accepted: translation quality becomes a provenance question with a version attached, not a
silent preprocessing step.

## Alternatives considered

**Translate on ingest, store English as primary.** Rejected — voids the traceability
guarantee above.

**Translate and store both, treating English as authoritative for rules.** Rejected. It looks
safer than it is: the rules would still derive from the translation, so the failure mode is
unchanged and merely better documented.
