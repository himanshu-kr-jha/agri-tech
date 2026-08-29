# Data Sourcing — session handoff

Date: 2026-08-28 · Branch: `data-scraping` (merged to `main`) · Status: **gathering done**

> **Update 2026-08-29 — wired.** All six batches now land as `ExternalRecord` rows and the
> text-bearing ones are retrievable through the Data Observer (ADR-0018). §2's goal —
> *retire the SYNTHETIC labels* — is **not** met and cannot be until the licences in §8.1 are
> confirmed: retrieved text is capped below the orchestrator's floor, so it informs without
> deciding. What did change is that the data is reachable, cited and visible instead of
> sitting inert on disk. **`docs/DATA-OBSERVER-HANDOFF.md`** is that work's own handoff.

Written so the next session — or the next person — resumes without re-deriving anything.
Companions: `docs/DATA-SOURCING.md` (the agreed design), `SOURCES_FOUND.md` (the source
register), `docs/adr/0012`–`0017` (the six decisions), `seed/source_registry.py` (the code
that is the single source of truth for what we fetch).

---

## 1. Resume in sixty seconds

```bash
git checkout data-scraping
export DATA_GOV_IN_API_KEY=...        # ask; never committed
make fetch-status                     # 10 sources, 6 batches, health + staleness
make fetch-due                        # re-fetch only what is past cadence
```

**What exists:** ten external sources fetched and cached under `seed/generated/batch*/`, each
with a `MANIFEST.json` carrying publisher, access route, licence and SHA-256.

**What does not exist:** any connection to the intelligence layer. No schema change, no
ingestion into Postgres, no edits to `seed/sources.md`, no confidence cap lifted. Everything
so far is gathering.

---

## 2. What this work actually is

Not "an ingestion fabric". The goal is narrow: **retire the `SYNTHETIC` labels in `seed/`.**

Every unsourced number in this repo already carries a confidence cap, so that goal has an
exact meaning — *lift the caps*:

| Debt | Where | Cap | Status |
|---|---|---|---|
| P1–P7 crop-protection conditions | `intelligence/crop_health.py` | **0.42** | Left alone deliberately — below the 0.45 orchestrator floor, so an unsourced diagnosis structurally cannot drive a recommendation. That cap is doing useful work. |
| E1–E6 cost of cultivation | `intelligence/farm.py:CROP_ECONOMICS` | **0.62** | **Blocked.** See §5. |
| A1–A4 base yields | `seed/reference.py:VarietySpec` | — | **Now boundable.** See §4. |
| Scheme eligibility rules | scheme module, `rules_verified=False` | **0.55** | Source found (batch 3), rules not transcribed. |

---

## 3. The decision record

Twenty-nine questions, asked and answered across nine grilling rounds. Settled — do not silently
revisit; if one turns out wrong, change it deliberately and say so.

| # | Question | Answer |
|---|---|---|
| 1 | Which cap first? | Cost of cultivation E1–E6 — *later reversed, see Q18* |
| 2 | Geographic scope | Real corpus UP-wide; sample FPO stays Prayagraj and stays synthetic |
| 3 | How much of the spec'd fabric | Minimal registry, **no scheduler**, plus staleness + fetch log |
| 4 | Unsourceable values | **Binary** — synthetic or dropped. No middle tier |
| 5 | "Separate" means what | Synthetic *entities*, real *reference data*. Already the existing pattern |
| 6 | Crop list bound | All UP crops, area descending, **no floor** — availability sets the limit |
| 7 | Batching | Per data type, record-level checkpoints |
| 8 | Health monitoring | Staleness + fetch log. **Not** reachability polling |
| 9 | Mixed provenance in a ranking | **Exclude unsourced-cost crops** from the ranking → ADR-0012 |
| 10 | `CropSpec` conflation | Split into UP-wide `CropReference` + Prayagraj placement map |
| 11 | Where cost data lives | `ExternalRecord`, orchestrator-gathered → ADR-0013 |
| 12 | Scrapers | Four by domain, opaque JSON cursor |
| 13 | Who lifts a cap | **A named human verifier** → ADR-0014 |
| 14 | Source documents | Extracted JSON always; URL + SHA-256 + `retrieved_at` always; file if small |
| 15 | Add P0–P5 `authority_level`? | **No** — see §7 |
| 16 | University cost studies | Accept in principle, sequence late |
| 17 | Do they enter the ranking? | **No** — advisory tier, orchestrator suggestions only |
| 18 | Priority after E1–E6 blocked | **Swap** — MSP first, cost demoted to batch 2 |
| 19 | Licence handling | Record per source, default `UNKNOWN`, `UNKNOWN` blocks a cap lift |
| 20 | Recheck cadence | MSP 90d · cost 365d · schemes 90d · varieties 365d · prices 1d |
| 21 | Hindi | **Canonical**, translation derived and versioned → ADR-0015 |
| 22 | agridarshan SPA | Find its API — *found, and rejected, see §6* |
| 23 | Advisory tier in `ModuleOutput` | Separate `advisory_findings` list, not a confidence value |
| 24 | Publisher vs access route in citations | Registry-bound constructor **plus** a test |
| 25 | Yield: district mean vs variety potential | **Different attributes**, not competing claims. The gap is management-quality signal |
| 26 | MSP announced but procurement unknown | **Reference-only.** Never presented as a reachable floor |
| 27 | `Govt Procurement Centre` buyer | Keep; price from real MSP with availability caveat; delete the `1.05` "MSP-linked" multiplier |
| 28 | Three temporal granularities | Gather resolves each to the value in force at `as_of` |
| 29 | Cross-source naming | One canonical alias table → ADR-0017 |

---

## 4. What we have

Ten sources, six batches, all `OK`. Full detail in `SOURCES_FOUND.md`.

| Batch | Domain | Sources | Note |
|---|---|---|---|
| 1 | MSP | 2 | **Current to 2025-26.** 23 crops with cost and MSP |
| 2 | Cost of cultivation | 2 | Stale (2017-18) and **aggregate only** |
| 3 | Scheme | 2 | UP government orders (Hindi, to 24/08/2026) + public CMS |
| 4 | Variety | 1 | 255 rows, real variety names |
| 5 | Production | 1 | **33,306 UP rows**, area + production → yield |
| 6 | Procurement | 2 | Includes `farmers_benefited` |

**The most valuable find is batch 5.** District × season × crop × year with area *and*
production means yield is derivable, which bears on A1–A4. Allahabad district means 2007–14:
wheat ~2.3, paddy ~2.4, potato ~16.3 t/ha, against repo synthetics of 4.0–4.3, 4.2–4.5 and
23–25. Variety *potential* legitimately exceeds a district *average*, so this does **not**
prove the synthetics wrong — it bounds them, which was previously impossible.

---

## 5. What is blocked, and on what

**E1–E6 (the 0.62 Farm cap).** The itemised six-component cost breakdown does not exist on
data.gov.in — searched four ways (`human labour`, `operational cost`, `input cost crop`,
`fertiliser consumption cost`); the catalogue has aggregates, MSP and return-over-cost only.
The itemised tables live in the DES *Cost of Cultivation of Principal Crops* reports.

- `desagri.gov.in` — **`ECONNREFUSED 164.100.114.118`**, repeatedly, over hours
- `mospi.gov.in` — reachable, but now a **JS SPA**; `/412-cost-cultivation-principal-crops`
  returns a 2.6 KB shell. Its API has not been found. **This is the next thing to try.**

Aggregating will not substitute: `farm.py:69-76` states the six-way split is load-bearing —
*"a single 'cost of cultivation' number cannot answer 'what if we are short of cash in
October'."*

**Every licence but one is `UNKNOWN`,** so under ADR-0014 nine of ten sources are **cached but
inert**. The exception is shasanadesh, whose Copyright Policy allows *non-commercial research
and private study, with attribution* — recorded as **COMMERCIAL USE NOT CLEARED**, which
matters because AgriVardhak is intended as a product.

---

## 6. Traps that fail silently

Each of these produces a plausible wrong answer rather than an error.

**`PRAYAGRAJ` matches zero rows.** The district crop-production series predates the 2018
rename; the district is `ALLAHABAD`. A join on the current name returns nothing, quietly.

**A single un-paged request looks like a complete dataset.** The production resource is 246k
rows nationally. Before paging was added, one request returned a prefix that looked whole.
`fetch()` now pages by offset and the manifest records `fetched_count` vs `total`.

**2014 is an outlier low year.** An early read of the yield data used 2014 alone and
overstated the synthetic-vs-real gap as ~3×. Across 2007–14 it is ~1.5–1.8×. Use the
multi-year mean.

**`--force` must not stamp `last_changed`.** A forced re-download is not the source changing.
Conflating them falsifies the one field that answers *when did this actually change*.

**Hashing the response envelope creates phantom changes.** data.gov.in returns volatile
wrapper fields. The content hash covers `records` and `field` only.

**An unmapped name silently shortens a list.** `R & M` / `Rapeseed/Mustard` / `Mustard` are one
crop across three sources, and `Paddy (Grade A)` / `Paddy (Common)` are two crops that look
like one. ADR-0017: alias at gather, and raise on unmapped rather than skip.

**A 403 is not a puzzle to solve.** Four agridarshan reference endpoints return 403 —
authentication-gated, therefore not public data. Do not attempt to get around it.

---

## 7. Rejected, with reasons — do not re-propose without new information

| Rejected | Why |
|---|---|
| **`agridarshan.up.gov.in/api/` beneficiary endpoints** | `beneficiaryMgt/getBenfById`, `farmerRegister/getVerifier`, `grantWiseBill/getFarmerList` — an internal DBT system holding **personal farmer records**. Reachable; out of bounds under INV-9 and the DPDP Act |
| agridarshan reference endpoints | Probed: all 403. Only `cms/getAll` is public, and it is used |
| Working around data.gov.in's Akamai block | Anti-bot protection. `api.data.gov.in` is the sanctioned route and works |
| `authority_level` (P0–P5) as a DB column | Two scalars meaning "how much do we believe this" drift apart, and `trust.py` can consume only one. P0–P5 lives in the docs as discovery triage |
| A commercial scraping vendor | Non-deterministic output fights `EvidenceSnapshot` replay; plain stdlib covers these sources |
| Browser automation for the SPA | Contradicts the plain-Python decision and breaks offline reproducibility (NFR-303) |
| Translating Hindi on ingest | Voids `Scheme`'s traceability guarantee. **लघु एवं सीमांत कृषक** is a legal category a fluent translation destroys invisibly |
| Collapsing E1–E6 to one aggregate | The six-way split is load-bearing for cash-flow reasoning |
| A middle "cited to a secondary source" tier | Becomes the default dumping ground; the caps stop meaning anything |

---

## 8. Next actions, in priority order

1. **Confirm licences.** Nine sources are inert until someone does. Cheapest unblock by far,
   and ADR-0014 requires a *named human* — this cannot be automated away.
2. **Find MoSPI's API** for 4.12, to reach the itemised cost tables and unblock E1–E6.
   Read its bundle the way `agridarshan`'s and `agmarknet`'s were read.
3. **Wire batch 1 (MSP)** into the model. Agreed in Q18 and not started. Needs
   `ExternalRecordKind.MSP`, orchestrator gather, and the *announced / procurement / market /
   realization* distinction the system currently cannot express.
4. **Use batch 5 to bound A1–A4** — a validation harness comparing synthetic yields against
   district means, rather than a silent replacement.
5. **Transcribe UP scheme rules** from batch 3, from the Hindi, by a human, under ADR-0014.
   Filter on category `नीतियोँ/योजनाओं संबंधी दिशा-निर्देश`.
6. **Untried and reachable:** `seednet.gov.in` (varieties), `fci.gov.in` (procurement),
   `enam.gov.in` (market).
7. **Retry periodically:** `desagri.gov.in`, `upagripardarshi.gov.in`, `upagriculture.com`,
   `farmer.gov.in`, `cacp.dacnet.nic.in`.

---

## 9. Conventions worth not relearning

- Seed fetchers are **standalone scripts, stdlib only** — they run without the API venv.
  That is why there is no `httpx` here despite it being an API dependency.
- `seed/generated/` **is tracked** (738 pre-existing agmarknet files) because NFR-303 requires
  the demo to run with the network disconnected.
- `fetch_log.jsonl` is **gitignored** (conflicts on every merge); `fetch_state.json` is
  **tracked**, because shared change-detection state is the point.
- Adding a data.gov.in source is **one row** in `seed/source_registry.py`. Batch 4 and batch 6
  needed no new code at all.
- Ruff line length 100. Five pre-existing lint errors in `fetch_agmarknet.py`,
  `fetch_weather.py`, `fetch_climatology.py` are **not ours** — they are on `main`.
