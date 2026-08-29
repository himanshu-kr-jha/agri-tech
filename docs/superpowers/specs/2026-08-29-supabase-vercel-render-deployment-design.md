# Deployment: Supabase + Render + Vercel

Date: 2026-08-29 · Status: §4 (C1–C7) implemented and verified against Docker; §5 runbook not yet run

**Verification performed** (2026-08-29), against a database created with `TEMPLATE template0`
holding nothing but `plpgsql` — the closest local simulation of a new Supabase project:

| Check | Result |
|---|---|
| Full migration chain on a pristine database | all 6 revisions applied, `alembic_version = a63640eada8d` |
| Extension placement | `postgis`, `pgcrypto`, `vector` all in `extensions` — the Supabase layout |
| `uuid_generate_v7()` | returns a valid v7 UUID, proving `gen_random_bytes` resolves cross-schema |
| `plot.boundary` / `plot.centroid` | `udt_schema = extensions`, `udt_name = geography` — B2 resolved |
| Migration chain on Docker (with `initdb`) | applies unchanged; extensions stay in `public` |
| `make seed` | 1,000 farmers, 2,412 acres — matches `DEMO-CONTEXT.md` |
| `make test-api` / web vitest | 381 passed / 8 passed |
| ruff, eslint, mypy, tsc | clean |
| `docker build` from repo root | succeeds; `parents[4]` resolves to `/app/seed/generated` in-image |
| Containerized API → Postgres | `/api/v1/health` → `database: ok, postgis 3.4.3, vector 0.8.6` |

Target: a **live pilot** — real FPO users, not a demo link. That word sets every tier and
hardening choice below.

---

## 1. Topology

```
  Browser
     │  HTTPS
     ▼
  Vercel ─────────── Next.js 16 (App Router)
  apps/web           Server Components + route handlers under /api/*
     │               Holds the session cookie (first-party, set by its own route handler)
     │  HTTPS, Authorization: Bearer <JWT>
     ▼
  Render ─────────── FastAPI (Docker, built from the REPO ROOT)
  whole repo         The only tier that touches the database (ADR-0001)
     │               Ships seed/generated/ — ingestion reads it at runtime
     │  Postgres wire, Supavisor session pooler :5432
     ▼
  Supabase ───────── Postgres (Supabase-managed) + PostGIS + pgvector
                     Schema owned by Alembic, not by the Supabase dashboard
```

Both Render and Supabase in **Singapore**. Co-location beats user proximity here: one
browser request costs one round trip to Vercel/Render, but the orchestrator makes many
database round trips per decision packet. Render offers no Mumbai region, so putting
Supabase in Mumbai would put ~60 ms on *every* database call rather than on one HTTP call.

### Why the web tier still cannot reach Postgres

Supabase makes direct-from-browser data access easy, and we are deliberately not using it.
ADR-0001 makes FastAPI the single enforcement point for authorization, provenance
resolution and the INV-5 information boundary. Moving reads to PostgREST would relocate
that boundary into RLS policies and client code — precisely the failure INV-5 names. The
Supabase anon/service keys are therefore never given to Vercel.

---

## 2. The three blockers this design removes

| # | Blocker | Fix |
|---|---|---|
| B1 | `infra/initdb/01-extensions.sql` runs only under Docker. Supabase never runs it, so `postgis`, `pgcrypto` and `uuid_generate_v7()` are absent — and every table's `server_default=text("uuid_generate_v7()")` depends on that function. `alembic upgrade head` fails on the first `CREATE TABLE`. | A new **base Alembic revision** creates them. `alembic upgrade head` becomes sufficient on any empty Postgres. |
| B2 | Supabase installs PostGIS into the `extensions` schema. GeoAlchemy2 emits an unqualified `geography(POLYGON,4326)` in `domain/models/land.py:56`, which will not resolve. | `search_path = public, extensions` set in code (engine `connect_args` + Alembic), not by a hand-run `ALTER ROLE`. |
| B3 | Supabase's direct connection is IPv6-only; Render egress is IPv4. | Supavisor **session pooler**, port 5432 — IPv4-compatible and prepared-statement-safe, unlike transaction mode on 6543. |

### Non-blockers, confirmed by inspection

- **Collation.** Supabase forces `en_US.UTF-8`; Docker uses `--locale=C`. Audited every
  ordering that can reach an `EvidenceSnapshot`: `gather.py` has no SQL `ORDER BY` at all,
  the intelligence modules sort in Python with explicit keys, and `content_hash` is
  `json.dumps(sort_keys=True)` — all collation-independent. The single collation-sensitive
  ordering is `ORDER BY farmer.full_name` in `api/dashboard.py:321`, a UI listing that never
  reaches a snapshot. There are no `LIKE`/`ILIKE` queries, so no `text_pattern_ops`
  dependency. Because this is schema + re-seed rather than a binary restore, indexes are
  built fresh under Supabase's collation. **INV-2 is not at risk.** The docker-compose
  comment claiming otherwise is over-claiming and gets corrected.
- **Append-only triggers** (`b9000000guard`) are ordinary DDL — no superuser needed.
- **`AGRI_USE_FIXTURES`** is misdocumented. Its docstring claims "every adapter uses its
  fixture," but no ingestion adapter reads it; it is consulted only by `orchestrator/llm.py:53`,
  `narrator.py:69` and `assistant.py:101`. It is an **LLM kill-switch**. The adapters always
  read committed files. So "live LLM + fixture data" is simply `AGRI_USE_FIXTURES=false`
  plus real keys. Docstring gets corrected.

---

## 3. Data migration strategy: schema + re-seed, not pg_dump

`seed/generated/` is 23 MB across 755 committed files, and `.gitignore` documents the intent:
*"`git clone && make seed` has to work on a train."* The entire database is therefore
reproducible from the repo. `pg_dump`/restore would add binary-restore failure modes
(index collation, extension schema mismatch, ownership) to buy nothing.

**Consequence:** `make seed` is a **one-time bootstrap** run by hand against Supabase. It is
never wired into a deploy hook. `make seed-reset` truncates every table and must never be
reachable from Render.

---

## 4. Code changes

Seven changes, all in this repo, all before touching a cloud console.

### C1 — Bootstrap migration (new base revision)

`apps/api/alembic/versions/a0000000boot_extensions_and_uuidv7.py`, with
`down_revision = None`, then `b8effdc6a2cb.down_revision` re-pointed to `"a0000000boot"`.

Portable across Supabase and Docker:

```sql
CREATE SCHEMA IF NOT EXISTS extensions;              -- no-op on Supabase, creates on Docker
CREATE EXTENSION IF NOT EXISTS postgis  WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS vector   WITH SCHEMA extensions;
```

`IF NOT EXISTS` means an extension already living in `public` on an existing Docker database
is left exactly where it is — the migration never relocates one, and `search_path` covers
both locations.

`uuid_generate_v7()` is created in `public` with a **function-level search path**, because
its body calls `gen_random_bytes`, which lives in `extensions` on Supabase and possibly in
`public` on an older local database:

```sql
CREATE OR REPLACE FUNCTION public.uuid_generate_v7() RETURNS uuid
  LANGUAGE plpgsql VOLATILE
  SET search_path = public, extensions
AS $$ ... $$;   -- body copied verbatim from infra/initdb/01-extensions.sql
```

Existing local databases are already stamped at a later revision, so Alembic will not
re-run this on them; every statement is idempotent regardless.

`downgrade()` drops only the function. Dropping PostGIS from under a database is not a
reversal anyone wants automated.

### C2 — Search path on the runtime engine

`apps/api/agrivardhak/db/session.py`:

```python
engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
    pool_size=5, max_overflow=5, pool_recycle=300,   # pooler-friendly
    connect_args={"options": "-csearch_path=public,extensions"},
    echo=False, future=True,
)
```

In code rather than as an `ALTER ROLE` because a live pilot must not depend on a one-off
console statement nobody wrote down. Harmless on Docker: Postgres silently ignores a
`search_path` entry naming a schema that does not exist.

`pool_recycle=300` matters against a pooler that reaps idle connections; `pool_pre_ping` is
already there and stays.

### C3 — Search path in Alembic

`apps/api/alembic/env.py` passes the same option to `engine_from_config`, which does not
inherit C2's `connect_args`:

```python
connectable = engine_from_config(..., connect_args={"options": SEARCH_PATH_OPTION})
```

**It must be a connection option, not a `SET` statement.** The first implementation used
`connection.exec_driver_sql("SET search_path TO public, extensions")` after `connect()`, and
it failed in the worst available way. On a SQLAlchemy 2.0 connection that statement
implicitly opens a transaction, so Alembic's `begin_transaction()` nests inside it rather
than owning it; Alembic's commit does not commit the outer transaction, and closing the
connection rolls the entire migration back. The command printed a full set of `Running
upgrade` lines for all six revisions and **exited 0 with zero tables created** — not even
`alembic_version`. Caught only by querying the database afterwards rather than trusting the
log. The rationale is recorded on `SEARCH_PATH_OPTION` in `db/base.py` so it is not
reintroduced.

The constant lives in `db/base.py` because both `db/session.py` and `alembic/env.py` already
import from it, and a divergence between the two search paths would reproduce exactly the
Supabase failure this change exists to prevent.

### C4 — Correct two misleading comments

- `config.py:63` — say that `use_fixtures` disables the LLM, since that is all it does.
- `infra/docker-compose.yml` — the `--locale=C` comment claims seed-hash reproducibility
  depends on it. Replace with the truth: determinism comes from the fixed RNG seed and
  Python-side sorting; the locale is a local-consistency convenience.

### C5 — `Dockerfile` at the repo root

Build context is the **repo root**, not `apps/api` — non-negotiable, because
`ingestion/weather.py:40` and `agmarknet.py:33` resolve `parents[4] / "seed" / "generated"`
at runtime. An `apps/api`-only image would build clean and fail on the first weather or
market question.

```dockerfile
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY . .
RUN pip install uv && uv pip install --system -e apps/api
CMD ["sh", "-c", "uvicorn agrivardhak.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

The full `COPY` precedes the install deliberately. Hatchling's editable install resolves
`packages = ["agrivardhak"]` at install time, so copying `pyproject.toml` alone to win a
dependency-cache layer makes the build fail outright. Correctness over cache; if build
minutes become a problem later, split it with a `--no-install-project` dependency pass.

`psycopg[binary]` ships wheels and GeoAlchemy2 is pure Python, so `-slim` needs no build
toolchain. The editable install puts `agrivardhak` on `sys.path` while leaving `__file__` at
`/app/apps/api/agrivardhak/...`, which is what keeps the `parents[4]` fixture lookup
resolving to `/app/seed/generated`.

### C6 — `.dockerignore`

Excludes `node_modules/`, `.next/`, `.venv/`, `.git/`, `__pycache__/`, `.mypy_cache/`,
`.ruff_cache/`. **Must not exclude `seed/generated/`** — see C5.

### C7 — `apps/web/src/app/api/assistant/stream/route.ts`

Add `export const maxDuration = 60;` and `export const runtime = "nodejs";`. The SSE proxy
outlives Vercel's default function budget on a slow orchestrator answer, and the Edge
runtime is the wrong host for it.

---

## 5. Deployment runbook

Ordering is forced by one circular dependency: Vercel needs Render's URL, and Render's CORS
needs Vercel's domain. Render goes first because its hostname is derivable from the service
name; CORS is filled in at step 9.

### Phase 1 — Local (steps 1–3)

**1. Apply C1–C7 and verify against Docker first.** The bootstrap migration must be proven
on a database you can throw away:

```bash
make db-reset && make upgrade && make seed && make test
```

`db-reset` recreates the volume, so `01-extensions.sql` *and* the new bootstrap migration
both run — proving idempotence on the path most likely to break. Do not proceed until
`make test` is green.

**2. Create the Supabase project.** Region **Singapore (ap-southeast-1)**. Set a strong
database password and store it in your password manager — Supabase shows it once. Choose a
paid plan: the free tier pauses a project after 7 days of inactivity, which for a live pilot
is an outage.

**3. Copy the session-pooler URI.** Dashboard → *Connect* → **Session pooler** (port
**5432**). Do **not** take "Direct connection" (IPv6-only, Render cannot reach it) or
"Transaction pooler" (6543, no prepared statements). The shape:

```
postgresql://postgres.<project-ref>:<password>@aws-N-ap-southeast-1.pooler.supabase.com:5432/postgres
```

Copy it from the dashboard rather than assembling it by hand — the `aws-N` prefix varies.
For this codebase, change the scheme to `postgresql+psycopg://` and **percent-encode any
special characters in the password** (`@` → `%40`, `#` → `%23`, `/` → `%2F`).

### Phase 2 — Schema and data into Supabase (steps 4–5)

**4. Migrate the schema.** From the repo root:

```bash
export AGRI_DATABASE_URL="postgresql+psycopg://postgres.<ref>:<pw>@aws-N-ap-southeast-1.pooler.supabase.com:5432/postgres"
cd apps/api && .venv/bin/alembic upgrade head && cd -
```

An exported environment variable outranks `apps/api/.env`, so your local Docker settings are
untouched. Verify in the Supabase SQL editor:

```sql
select uuid_generate_v7();                       -- a v7 uuid: bootstrap migration worked
select extname, nspname from pg_extension
  join pg_namespace n on n.oid = extnamespace;   -- postgis + pgcrypto + vector in "extensions"
select count(*) from information_schema.tables
  where table_schema='public' and table_type='BASE TABLE';
```

**Expect 51 — one lower than Docker's 52.** Both hold the same 50 domain tables plus
`alembic_version`; Docker additionally counts `spatial_ref_sys` in `public`, because
`infra/initdb/01-extensions.sql` runs `CREATE EXTENSION postgis` with no `WITH SCHEMA`. Under
this migration it lands in `extensions` and drops out of the count. Both figures are
*measured*, not predicted.

`scripts/progress.py` asserts `rows={"__tables__": 49}` using this same query (line 379), and
that is a **floor** (`rows.get(table, 0) >= minimum`, line 407), not an equality — so 51 and 52
both pass. The 49 is merely stale, predating the three migrations after the initial schema. No
action needed; noted so nobody "fixes" the number.

**5. Seed once.** With the same variable still exported:

```bash
make seed
```

Expect several minutes — 1,000 farmers and two seasons of history over a pooled connection.
Then confirm the numbers the demo asserts:

```sql
select count(*) from farmer;                    -- 1000
select round(sum(area_sqm)/4046.86) from plot;  -- 2412 acres (DEMO-CONTEXT.md)
```

Unset the variable afterwards (`unset AGRI_DATABASE_URL`) so you do not later run tests
against the pilot database.

### Phase 3 — Render (steps 6–7)

**6. Create the Web Service.** Connect the repo. Runtime **Docker**, Dockerfile path
`./Dockerfile`, **root directory left blank** (repo root — C5). Region **Singapore**.
Instance type **Starter or above**: the free tier sleeps after 15 minutes and wakes in ~50 s,
which a pilot user reads as "the site is broken."

- Health Check Path: `/api/v1/health`
- Pre-Deploy Command: `cd apps/api && alembic upgrade head`

The pre-deploy command is what keeps schema and code in step on every future push. It is
`upgrade`, never `seed` — see §3.

**7. Set Render environment variables.**

| Key | Value |
|---|---|
| `AGRI_DATABASE_URL` | the session-pooler URI from step 3 |
| `AGRI_JWT_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(48))"` — a fresh one, never the dev default |
| `AGRI_ENVIRONMENT` | `production` |
| `AGRI_DEBUG` | `false` |
| `AGRI_USE_FIXTURES` | `false` — this is what keeps the LLM live (§2) |
| `AGRI_ANTHROPIC_API_KEY` | real key |
| `AGRI_NVIDIA_API_KEY` | real key (the intent router, ADR-0011) |
| `AGRI_LLM_PROVIDER` | `nvidia` |
| `AGRI_CORS_ORIGINS` | placeholder `["http://localhost:3000"]` — corrected at step 9 |

`AGRI_CORS_ORIGINS` is a `list[str]`, so pydantic-settings parses it as **JSON**. It must be
a bracketed, double-quoted array; a bare comma-separated string raises at startup.

Deploy, then confirm: `curl https://<service>.onrender.com/api/v1/health` — it queries the
database, so a 200 proves Render→Supabase over the pooler end to end.

### Phase 4 — Vercel (step 8)

**8. Import the repo.** Root Directory **`apps/web`** (the Next.js app is self-contained —
its own `package.json`, no workspace dependencies). Framework preset auto-detects as
Next.js.

Environment variable: `NEXT_PUBLIC_API_URL = https://<service>.onrender.com`

Not a secret — it is `NEXT_PUBLIC_` because `app/login/page.tsx:23` reads it client-side.
Do not put `AGRI_DEV_TOKEN` here: `lib/session.ts:36` falls back to it, and a static CEO
token in production would hand every visitor CEO scope. That fallback exists for
`make dev-env` and must stay local.

### Phase 5 — Close the loop and verify (steps 9–10)

**9. Set the real CORS origin.** Back in Render, set

```
AGRI_CORS_ORIGINS=["https://<your-app>.vercel.app"]
```

and redeploy. Add any custom domain as a second array element. Vercel preview deployments
get per-deployment hostnames that will not be in this list — preview builds cannot call the
API, which is the correct default for a pilot.

**10. Verify against the invariants, not just the homepage.**

| Check | Passes when |
|---|---|
| `GET /api/v1/health` | 200, and reports the database reachable |
| Sign in as `ceo@demo.agrivardhak` | session cookie set by the Vercel route handler, dashboard renders |
| Open a decision packet | evidence drill-down resolves — proves PostGIS and the `extensions` search path under real queries |
| Ask the assistant a question | a narrated answer, not the keyword fallback — proves the LLM keys and `AGRI_USE_FIXTURES=false` |
| Sign in as `farmer@demo.agrivardhak` | every `/fpo/*` route returns 403 (INV-5) |
| Approve a recommendation | state advances only with an `Approval` row (INV-1) |
| Farmer directory | sorts in dictionary order, not ASCII order — the one expected collation difference (§2) |

---

## 6. Pilot hardening (do not skip for real users)

- **Backups.** Supabase daily backups on Pro; enable PITR before the first real farmer
  record exists. The seed is reproducible — real user data is not.
- **Secrets.** `AGRI_JWT_SECRET` and the database password live only in Render's environment.
  Rotating the JWT secret invalidates every session; do it on any suspected exposure.
- **`make seed-reset` is a loaded gun.** It truncates every table. It must never appear in a
  Render command field. Consider gating it behind `AGRI_ENVIRONMENT == "local"`.
- **Migration safety.** The pre-deploy command runs `upgrade head` against live data. From
  the first real user onward, every migration must be reviewed for destructive DDL —
  append-only tables (DR-04) make some column changes irreversible by design.

---

## 7. Repo obligations

Per `CLAUDE.md` §8, this change also carries:

- **ADR-0018 — Deployment topology and the Supabase extension boundary.** Records why the
  web tier still cannot reach Postgres despite Supabase making it easy (ADR-0001, INV-5),
  why extensions moved from `initdb` into a migration, and why the session pooler.
- **`docs/ARCHITECTURE.md`** — a deployment section; the 8-layer model currently implies
  one host.
- **`scripts/progress.py`** — a `Deliverable("M-DEPLOY", ...)` whose evidence is the
  bootstrap revision symbol and the `Dockerfile`, added *before* implementation.
- **`.env.example`** — a commented Supabase-shaped `AGRI_DATABASE_URL` alongside the Docker
  one, since both are now supported (your "switchable by env" choice).

---

## 8. What this design does not do

- No CI/CD pipeline beyond Render and Vercel's built-in git triggers.
- No Render Cron Job — fetchers stay local, fixtures stay committed (your choice).
- No staging Supabase project. The bootstrap migration makes one cheap to add later, which
  is most of the point of choosing it over a hand-run SQL script.
- No custom domain, no CDN tuning, no rate limiting. Flag if the pilot needs them.
