# The Data Observer — what was built, and what it does

Date: 2026-08-30 · Branch: `feat/data-observer` · Status: **built, evidenced, nothing verified**

Companion to `docs/DATA-SOURCING-HANDOFF.md`, which ends with *"gathering done, nothing wired."*
This is the wiring. Design record: **ADR-0018**. Written so the next person can judge the work
rather than re-derive it.

---

## 1. The gap this closed

Ten public sources had been fetched, hashed and committed under `seed/generated/batch*/`, and
`grep -rn "generated/batch" apps/api` returned **nothing**. Three requirements were
unimplemented as a direct result, and two places in the code said so themselves:

| | Before |
|---|---|
| `DR-07` | `CREATE EXTENSION vector` ran at initdb with the requirement quoted beside it. Zero `Vector` columns, zero imports. |
| `FR-403` | `scheme.SCHEMES` was a hardcoded Python tuple; the `scheme` table was never read. |
| `FR-404` | `news_event` existed since the initial schema with **no producer and no consumer**. |
| `risk.py:736` | `degraded.append("policy and procurement change is not modelled — no scheme feed yet")` |
| `lookups/fpo.py` | *"that needs an ingested news feed this repository does not have"* |

---

## 2. What runs now

```
seed/generated/batch*/        ten cached sources, committed, SHA-256 in each MANIFEST
        │
        ▼  ingestion/registry.py + ingestion/schemes.py
ExternalRecord                34,225 rows across six batches, raw payload retained (FR-405)
        │
        ▼  knowledge/pipeline.py — the observer, deterministic, no model call
   classify → segment → embed → index
        │
        ├──► KnowledgeChunk    207 retrievable passages, Hindi canonical, append-only
        └──► NewsEvent          74 real government orders (FR-404)
                │
                ▼  knowledge/retrieval.py — retrieve() / recent()
        hybrid: Postgres full-text + pgvector, fused by rank, multiplied by trust
                │
                ▼  orchestrator/gather.py — DB rows to pure module input
                ▼  intelligence/risk.py — POLICY findings a CEO reads
```

### Row counts after `make seed`

| | |
|---|---|
| External records | 34,225 (60,127 including Agmarknet and weather) |
| Knowledge chunks | 207, of which 49 classified noise |
| Policy events | 74 |
| Database tables | 53 (was 52) |

---

## 3. The four decisions worth arguing with

**Hybrid retrieval, fused by Reciprocal Rank Fusion.** Dense vectors carry meaning across
languages — an English query for "crop insurance" reaches a Hindi order about
प्रधानमंत्री फसल बीमा योजना, measured cross-lingual cosine **0.795**. Lexical search catches
what embeddings blur: `लघु एवं सीमांत कृषक` is a legal category with a landholding threshold
attached, and a vector that places it near "small farmers" has lost the thing that matters.
RRF needs no score normalisation and degrades to whichever list exists.

**Trust multiplies the rank; it is not a tiebreak.** Decay comes from `provenance/trust.py` —
the same function that ages a farmer's plot-area claim, called with the same `as_of`.

**Trust is computed, never stored.** `KnowledgeChunk` has no `trust_score` column. The table is
append-only, and a stored decayed number would make a replay disagree with the confidence the
packet recorded on the day (INV-2).

**The licence gate is arithmetic.** `knowledge/gates.py` caps an unlicensed passage at **0.40**
against the orchestrator's **0.45** floor, so it is structurally unable to drive a
recommendation while staying readable as context. Copies the pattern
`crop_health.UNSOURCED_CONFIDENCE_CEILING = 0.42` already set.

---

## 4. What it is honestly not

**The listing is not the order.** The शासनादेश scraper harvests listing rows — a `subject`
field averaging 199 characters, never the linked PDF. So the system reports *that* an order
exists and *who it touches*, never what it is worth. The risk module names that limit in its
own `degraded_inputs` rather than leaving a reader to discover it.

**Semantic chunking mostly does not fire.** Every 199-character order subject returns as one
chunk via an explicit early return. It splits the four long FAQ answers **5 ways against 1** by
length — real work, on exactly the documents that warrant it, and nowhere else.

**No crop is ever named.** Measured across all 75 orders: not one names an individual crop.
They speak in budget heads and scheme names — `फसल` 23 times, `दलहन` twice, `तिलहन` once. Every
policy event therefore resolves as department-wide. Mapping the group terms onto demo crops was
considered and rejected: `तिलहन` covers every oilseed, and quietly resolving it to Mustard would
manufacture precision the order does not have.

**Nothing is verified.** Every passage is `UNVERIFIED`, and nine of ten licences are
unconfirmed. Scheme behaviour is unchanged until a human reviews them — that is ADR-0014
working, not a gap.

**The exposure figures are synthetic.** When a finding says *"touching 1,842 acres across 750
farmers"*, the orders are real and the farmers are the seeded Prayagraj FPO. Real government
data × synthetic farmer base.

---

## 5. Where it surfaces

| Surface | Who | What |
|---|---|---|
| `/risk` | FPO CEO | Three `policy` register entries from real orders, sized to 750 farmers |
| `/assistant` | FPO CEO | Packet Situation section cites orders; *"what has changed?"* reports departmental activity |
| `/decisions/[id]` | FPO CEO | Frozen evidence resolves to the exact cited passage |
| `/knowledge` | FPO CEO | Search, with `relevance × trust` shown and uncleared passages below a divider |
| `/schemes` | **Farmer** | Hindi-first government notices, searchable. Never states eligibility. |
| `make trace` | anyone | All nine stages over one real order, computed live |

The farmer screen is deliberate: `context.md` records the originating pain as farmers lacking
access to scheme information. A public state-portal order is neither FPO data nor another
farmer's, so INV-5 is not engaged — verified by token: a farmer gets **200** on `/schemes` and
**307 → /today** on every FPO route.

---

## 6. Bugs the code found by being run

Each of these produced a plausible wrong answer rather than an error, which is the failure mode
`DATA-SOURCING-HANDOFF.md` §6 catalogues.

**189 of 255 rows silently dropped.** `variety-field-crops` looks keyed by `(type, crop)` and is
not — it is a flattened grid where `CEREAL CROPS`/`Paddy` names 38 rows. `ON CONFLICT DO
NOTHING` absorbed the collision and reported a smaller, plausible count. The loader now raises.

**`प्राविधानित` contains `धान`.** "Provisioned" appears in nearly every budget order, so
substring matching attributed **26 of 26** policy events to paddy, including soil-conservation
releases. Now matched as whole tokens, with inflections declared rather than guessed.

**The append-only guard is incompatible with generated columns.** Postgres computes generated
columns *after* BEFORE-row triggers, so `NEW.search_doc` is always NULL inside the guard and
every UPDATE looked like an attempt to blank it. `knowledge_chunk` is the first table here with
one. Allowlisting it weakens nothing — a generated column cannot be written directly.

**`NewsDomain.INPUT_PRICE` has no `RiskDomain`.** Caught at persistence when a packet ran.

**Nearest-neighbour search always returns k rows.** "bitcoin mining" came back with three Hindi
government orders — correctly ranked, and useless. Measured bands **overlap** ("cold storage"
0.338 against "शेयर बाजार सेंसेक्स" 0.380), so no cosine threshold separates them cleanly; what
does is that junk queries have zero lexical hits. Dense neighbours now need cosine ≥ 0.42;
lexical hits bypass it entirely.

**Staff seniority lists reached the farmer feed.** The CMS files `ज्येष्ठता सूची` as
"circulars" — 39 domain-less chunks, so a smallholder opening "Government notices" was shown the
clerical cadre's seniority roster. Filtered, without swallowing the mechanisation programmes.

---

## 7. Commands

```bash
make trace          # walk one order through all nine stages (read-only, start here)
make ingest         # land batches + run the observer. Idempotent
make embed-model    # optional: installs the encoder runtime + ~120 MB model
make extract-schemes  # optional: Claude batch, writes a reviewable fixture
```

`make seed` runs the loaders and the observer, so a fresh clone needs nothing extra. Without
`make embed-model` retrieval is lexical-only and everything still works (NFR-303).

---

## 8. Next actions, in priority order

1. **Confirm the nine `UNKNOWN` licences.** Cheapest unblock in the repository, and ADR-0014
   requires a named human — it cannot be automated. Logged as **L1–L9** in `PROGRESS.md`.
2. **Fetch the order PDFs.** No PDF path exists anywhere (`pdfplumber` appears only in a design
   doc). This is what would turn "an order exists" into "it is worth ₹X to these farmers", and
   it is what the semantic chunker was built for.
3. **Review the extraction fixture** once someone runs `make extract-schemes`, then set
   `verified_by` on what survives. That is the only thing that lifts a cap.
4. **Decide the commercial question.** `up-go-agriculture` is recorded **COMMERCIAL USE NOT
   CLEARED**. Fine for a public-good entry; it blocks a product. `gates.licence_is_usable`
   already takes a `commercial` flag so the answer is computed, not remembered.

---

## 9. Conventions worth not relearning

- **Normalise for matching, never for storage.** The scraped Hindi carries zero-width joiners;
  `classify.normalise` strips them on a copy. `text_hi` keeps the published bytes (ADR-0015).
- **Aliases are declared, not derived.** Guessing Hindi morphology is how the `धान` bug returns.
- **`recent()` and `retrieve()` share one `_score()`.** A farmer-facing list that quietly lost
  the licence cap would be the worst possible place to lose it, and a test asserts they agree.
- **Chunk boundaries depend on whether an encoder was present at observe time** — 207 with, 195
  without. Stable once written, and replay is unaffected; see `pipeline.observe`'s docstring.
