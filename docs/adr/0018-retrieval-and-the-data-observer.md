# ADR-0018 — Hybrid retrieval over a gated knowledge base

Date: 2026-08-29 · Status: Proposed

## Context

`DR-07` has been in the SRS since the first commit: *"Scheme and news text is embedded with
pgvector for retrieval; the raw text is retained."* `infra/initdb/01-extensions.sql` creates
the extension with that requirement quoted in a comment. Nothing ever used it — no `Vector`
column, no import. `FR-403` and `FR-404` were unimplemented for the same reason, and
`news_event` has existed since the initial schema with no producer and no consumer.

Meanwhile `seed/` accumulated ten cached public sources across six batches, hashed and
committed, and `grep -rn "generated/batch" apps/api` returned nothing.
`docs/DATA-SOURCING-HANDOFF.md` named the state exactly: **"gathering done, nothing wired."**

Two facts about the corpus bound every choice below, and both were measured rather than
assumed.

**It is small, and the documents are short.** The शासनादेश scraper harvests *listing rows*,
not order documents: 75 orders, `subject` averaging 199 characters and never exceeding 329,
of which 13 are scheme guidelines and 52 are budget-head sanctions. The agridarshan CMS adds
125 records of which 24 FAQs carry real prose and most of the rest are staff promotions. The
genuinely useful corpus is roughly 50 short passages.

**Almost none of it is cleared for use.** Nine of ten sources carry `licence = "UNKNOWN"`,
and the one exception — shasanadesh — is *non-commercial research and private study, with
attribution*, recorded as **COMMERCIAL USE NOT CLEARED**. Under ADR-0014 that data is cached
but inert.

## Decision

A **Data Observer** stage between `ExternalRecord` and the orchestrator —
classify → segment → embed → index — writing `KnowledgeChunk` rows, with one retrieval
function, `knowledge.retrieval.retrieve`, as the only seam callers see.

Four choices inside that are worth recording.

**Hybrid retrieval, fused by Reciprocal Rank Fusion.** Dense vectors handle paraphrase: an
English query for "crop insurance" reaches a Hindi order about प्रधानमंत्री फसल बीमा योजना
(measured cross-lingual cosine 0.795), which lexical search cannot do. Postgres full-text
handles the opposite failure: `लघु एवं सीमांत कृषक` is a legal category with a landholding
threshold attached, and an embedding that places it near "small farmers" has lost the thing
that matters. RRF needs no score normalisation and degrades to whichever list exists.

**Trust multiplies the rank; it does not filter or tie-break.** Decay comes from
`provenance/trust.py` — the same function that ages a farmer's plot-area claim, called with
the same `as_of` — so a stale unlicensed chunk loses to a fresher authoritative one that
matches slightly worse.

**Trust is computed, never stored.** `KnowledgeChunk` has no `trust_score` column. The table
is append-only, and a stored decayed number would also make a replay against an
`EvidenceSnapshot` disagree with the confidence the packet recorded on the day (INV-2).

**The licence gate is arithmetic, not process.** `knowledge/gates.py` caps an unlicensed
passage at **0.40**, below the orchestrator's 0.45 floor, so it is *structurally* incapable
of driving a recommendation while remaining readable as context. An unverified extraction
caps at 0.55, matching `scheme.UNVERIFIED_CONFIDENCE_CEILING`. This copies the pattern
`crop_health.UNSOURCED_CONFIDENCE_CEILING = 0.42` already established, and the comment there
applies verbatim: the cap is doing useful work.

The one place a model is used — proposing structured fields from Hindi order text — runs as
a deliberate offline batch whose output is committed as a reviewable fixture and lands
`UNVERIFIED`. The request path never calls a model.

## Consequences

Easier: `FR-403`, `FR-404` and `DR-07` are satisfied; the ten cached sources are no longer
inert data on disk; `risk.py`'s hardcoded *"policy and procurement change is not modelled —
no scheme feed yet"* is replaced by evidenced POLICY findings; and "what has changed?" reports
real government activity instead of only price moves.

Harder: two retrieval paths to reason about instead of one, and an optional native dependency
(`onnxruntime`) that some clones will not have.

Accepted, and worth stating plainly: **semantic chunking is close to a no-op on today's
data.** A 199-character subject is already one passage, so `segment()` returns it unchanged
via an explicit early return. The similarity-breakpoint path is implemented and tested
because the four long FAQ answers need it and the order PDFs will need it more — but it is
not doing work today, and pretending otherwise would misrepresent the system.

Also accepted: **nothing is verified on day one**, so scheme behaviour is unchanged until a
human reviews the extractions. That is ADR-0014 working, not a gap.

## Alternatives considered

**`sentence-transformers` with torch.** Rejected on weight, not quality: ~2.5 GB of runtime
for a corpus of a few hundred short passages, against ~50 MB of `onnxruntime` plus a 118 MB
int8 model. The repository's promise is that `git clone && make seed` works on a train.

**Lexical only, amending DR-07.** Defensible for 50 documents, and rejected because the
cross-lingual case is real: the corpus is Hindi and FPO staff will ask in both languages.

**A dedicated vector service.** Rejected for the reason ADR-0001 already gave: two more
services to run at the demo. pgvector in the Postgres we already run covers this at this
scale.

**Storing `trust_score` on the chunk, refreshed by a job.** Rejected — it breaks append-only
and desynchronises replay from the packet it is checking.

**Adding a news scraper for `FR-404`.** Rejected as unnecessary: the शासनादेश stream *is* a
government policy feed — dated, categorised, published by the department whose decisions it
records — and it is the only source whose licence anyone has read. A new source would have
added an eleventh `UNKNOWN` licence to solve a problem we already had the data for.

**Letting the model's extraction lift a cap when confidence is high.** Rejected by ADR-0014
in advance: *"Source authority says nothing about whether our extraction of it was correct,
and extraction is where the error actually occurs."*
