# Demo runbook

Everything needed to get from a clean checkout to the seven-minute demo in
`docs/MVP-SCOPE.md#demo-script`. **It works with the network disconnected** — that is
asserted by a test, not hoped for (NFR-303).

---

## 1. Start it

```bash
make setup          # venv + npm install + Postgres in Docker + migrations
make demo           # seed the FPO, real prices, weather, climatology, demo accounts
```

```bash
make dev            # api on :8000, web on :3000
```

Then open <http://localhost:3000> and sign in.

### The three demo logins

Password for all of them: **`agrivardhak`**. The sign-in page lists them, so nothing has to
be typed from memory or from this page.

| | Username | Lands on |
|---|---|---|
| Ramesh Verma — CEO | `ceo@demo.agrivardhak` | the organization console |
| Sunita Devi — Field Officer | `officer@demo.agrivardhak` | the same console, narrower approval rights |
| Pushpa Nishad — Member | `farmer@demo.agrivardhak` | their own farm |

Which dashboard you get is decided by the role grants in the database and returned by the
API. The client cannot ask for a role — there is a test that posts `"roles": ["FPO_CEO"]`
alongside the farmer's credentials and asserts it comes back `FARMER`.

**Sanity check before you present** (about two minutes):

```bash
make check          # ruff + mypy + tsc + eslint
make test           # 310 tests, none skipped
make progress       # regenerates PROGRESS.md from evidence
```

---

## 2. What the seed contains

| | |
|---|---|
| Farmers | 1,000 across three tracts (Ganga-par, doab, Yamuna-par) |
| Operated area | 2,412 acres (976.2 ha) |
| Active crop cycles | 1,288 Kharif, mostly paddy |
| Aggregated lots | 5, with 9 buyer offers anchored to real modal prices |
| Data conflicts | 8, deliberate — the provenance moment needs them |
| **Agmarknet prices** | **23,460 rows, 731 days, five real Prayagraj markets** |
| **Weather** | **2,439 tract-days, real Open-Meteo** |
| **Hazard climatology** | **30 years of ERA5, half-month hazard frequencies** |

Everything about the *outside world* is real. Everything about the *collective* is synthetic
and carries a `DEMO DATA` badge wherever it appears.

---

## 3. The path through the screens

| Screen | What to show |
|---|---|
| `/dashboard` | The briefing first — **what is waiting on you**, then ten cards. Point at "Unresolved data conflicts: 8". |
| `/assistant` | Ask *"What should we do this season to maximize sustainable farmer income?"* Sections stream in fixed order over ~6 s. |
| — | **The amber banner is the moment.** Four findings, two independent modules, about a crop nobody proposed — it is simply what is planted. |
| `/decisions/<id>` | Scroll to **Frozen evidence**: the SHA-256, the module versions, and a replay that rebuilds the packet from those bytes and says whether it still matches. |
| — | Approve one recommendation **with a different amount**. Both numbers persist; it is recorded as a modification, not a plain approval. |
| `/risk` | Ordered by exposure, not by probability. Note the row that says a hazard is the *climate*, not a risk. |
| `/market` | Headline price vs what the collective banks. Rejection rate costs four times the freight. |
| `/farmers` → one farmer | Every plot area carries source, date, confidence and a conflict badge. |
| `/today` | Switch to a farmer token (below). Bilingual, their own farm only. |
| `/impact` | Reports what it **could not** attribute as prominently as what it could. |

### The boundary moment

Sign out, then sign in as `farmer@demo.agrivardhak`.

Every organization URL now redirects the member to their own farm. Show the status codes
rather than the screen — it is the more convincing demonstration, and it is what a technical
judge will ask for:

```
farmer token →  /fpo/dashboard   403      /farmer/today   200
                /fpo/farmers     403
                /fpo/market      403
                /decisions       403
                /risk-register   403
                /audit           403
                /assistant/ask   403
```

The redirect is a courtesy for someone who typed the wrong URL. The refusal is the boundary,
and it does not care how the browser got there.

The farmer view is built farmer-scoped from the start rather than filtered down from an
organization query, so org-internal rows are never in the result set for a rendering bug to
leak.

---

## 4. If something goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| Every page says "Could not reach the API" | API not running | `make api` |
| Sent back to `/login` unexpectedly | Session expired — tokens last 12 hours | Sign in again |
| Sign-in says "Could not reach the API" | API not running | `make api` |
| `make seed` says nothing happened | Already seeded; it is idempotent | `make seed-reset` |
| Assistant returns 500 | Usually a stale schema | `make upgrade` |
| Prices or weather look empty | The fixture bundle was not loaded | The payloads are committed under `seed/generated/` (14.7 MB, 738 files) — `make seed-reset` reloads them without touching the network |
| Answers take longer than ~8 s | First request warms connection pools | Ask once before the demo starts |

**There is no fallback needed for a network outage.** No external call is on the request
path: prices, weather and climatology are all stored payloads, and the LLM only narrates —
without a key the packet is produced deterministically and says `model_id: deterministic`.

---

## 5. What to say when asked the hard questions

**"Are these numbers real?"** The market prices, the weather and the hazard climatology are
real and cited in `seed/sources.md`. The farmers, plots and buyers are synthetic and labelled
on every screen. The cost-of-cultivation and crop-protection figures are unsourced
placeholders — and the system caps its own confidence because of it, below the threshold that
would let them drive a recommendation. That register lists exactly what is still open.

**"What stops it hallucinating?"** A claim cannot be constructed without an evidence
reference — it is a validation error, not a filter. The number a module produces is
arithmetic over gathered data; the model only writes prose around numbers it did not choose,
and if it fails the packet is produced anyway.

**"What if it is wrong?"** Then a human disagrees with it, which is why the override is shown
rather than applied. Nothing executes without an approval row signed by someone holding the
right role, and there is no code path that can write `EXECUTED` without reading that row back
from the database.

**"Can you prove it said that six months ago?"** Open any decision and press replay. It
rebuilds the packet from the stored snapshot alone and tells you whether it still matches.

**"What is it worst at?"** Agronomy. Every yield coefficient and every disease association is
an unsourced placeholder. The system is honest about it and caps itself accordingly, but a
capped module is a module that cannot help much — one conversation with a Prayagraj
agronomist would do more for this than another week of code.
