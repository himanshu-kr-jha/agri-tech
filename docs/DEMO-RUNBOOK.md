# Demo runbook

Everything needed to get from a clean checkout to the seven-minute demo in
`docs/MVP-SCOPE.md#demo-script`. **It works with the network disconnected** — that is
asserted by a test, not hoped for (NFR-303).

---

## 1. Start it

```bash
make setup          # uv sync + pnpm install + docker compose up -d db
make upgrade        # alembic upgrade head
make seed           # the synthetic Prayagraj FPO + real prices, weather, climatology
make dev-token      # copy the JWT it prints
```

Put the token where the web tier can find it — it is read server-side only, never sent to
the browser:

```bash
cat > apps/web/.env.local <<EOF
AGRI_DEV_TOKEN=<the token>
NEXT_PUBLIC_API_URL=http://localhost:8000
EOF

make dev            # api on :8000, web on :3000
```

Then open <http://localhost:3000/assistant>.

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

### A farmer token, for the boundary moment

```bash
cd apps/api && .venv/bin/python -c "
import uuid
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from agrivardhak.config import get_settings
from agrivardhak.api.auth import issue_token
from agrivardhak.domain.enums import Role
from agrivardhak.domain.models.organization import Organization, Farmer
e = create_engine(get_settings().database_url)
with Session(e) as s:
    org = s.execute(select(Organization)).scalars().first()
    f = s.execute(select(Farmer)).scalars().first()
print(issue_token(user_id=uuid.uuid4(), roles={Role.FARMER},
                  organization_id=org.id, farmer_id=f.id))"
```

Swap it into `.env.local` and reload. Better still, show the status codes rather than the
screen — this is the more convincing demonstration:

```
farmer token →  /fpo/dashboard   403      /farmer/today   200
                /fpo/farmers     403
                /fpo/market      403
                /decisions       403
                /risk-register   403
                /audit           403
                /assistant/ask   403
```

The farmer view is built farmer-scoped from the start rather than filtered down from an
organization query, so org-internal rows are never in the result set for a rendering bug to
leak.

---

## 4. If something goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| Every page says "Could not reach the API" | API not running | `make api` |
| Pages render but say "organization staff only" | `AGRI_DEV_TOKEN` is a farmer token, or missing | `make dev-token`, update `.env.local`, restart the web server |
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
