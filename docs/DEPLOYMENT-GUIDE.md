# Deployment Guide — from this repo to a live URL

> **Purpose.** This file is written for **a future Claude Code session that has no memory of
> the conversation that produced it**, and for the human operating alongside it. It carries
> the verified state of the repo, the questions that must be answered before anything is
> created in a cloud console, and then the exact end-to-end steps.
>
> Companion documents — read in this order, do not skip:
> 1. `docs/adr/0019-deployment-topology-and-extension-boundary.md` — *why* the topology is
>    what it is. Every alternative you might be tempted to propose is already rejected there
>    with a reason.
> 2. `docs/superpowers/specs/2026-08-29-supabase-vercel-render-deployment-design.md` — the
>    design and the original runbook, including the verification evidence table.
> 3. **This file** — the operator runbook: question round, ordered steps, verification,
>    troubleshooting, rollback, and a resumable state tracker.
>
> This guide does not replace those two. It sequences them and adds what they leave to the
> operator.

---

## 0. Instructions to the assistant reading this

**You must run §2 (the question round) and get answers before you create, buy, or configure
anything.** The deployment has irreversible-ish steps (paid plans, a database that will hold
real farmer data, a JWT secret that invalidates sessions when rotated). Guessing an answer
here is not a time saving; it is a rollback.

Follow this loop:

1. **Re-verify state, do not trust this file's dates.** Run §1's verification block. This
   file was written on **2026-08-30**; if the git log or the file list disagrees with §1,
   the repo moved and you re-derive before proceeding.
2. **Ask §2's questions.** Batch them — do not ask twenty times in a row. Group A first
   (it changes everything downstream), then B and C together, then D. Offer the recommended
   default for each; a user who says "you pick" gets the default, recorded in §3.
3. **Write the answers into §3 of this file** (edit it, commit it). That table is what makes
   this survivable across a context compaction — if you wake up mid-deployment, §3 and §10
   tell you where you are.
4. **Run the phases in order.** Phases are ordered by a forced dependency (§4). Do not
   parallelize Render and Vercel; Vercel needs Render's hostname and Render's CORS needs
   Vercel's domain.
5. **Never mark a step done from the absence of an error.** Each step has an explicit
   *expected output*. §9 exists because one of these steps has already failed silently once,
   exiting 0 having created zero tables.
6. **Never run `make seed-reset` against the pilot database.** It truncates every table.

Things you may **not** decide alone: choosing a paid plan, putting a real key into a cloud
console, pointing the deployment at a branch other than the one the user names, and anything
that would touch real (non-synthetic) farmer data.

---

## 1. Verified state as of 2026-08-30

### 1.1 What is already true (verified by inspection today)

| Fact | Evidence |
|---|---|
| Code changes C1–C7 from the design spec are **implemented and in the repo** | `apps/api/alembic/versions/a0000000boot_extensions_and_uuidv7.py` exists; `db/base.py:32` holds `SEARCH_PATH_OPTION = "-csearch_path=public,extensions"`; `db/session.py:24` and `alembic/env.py:15` both use it; `Dockerfile` + `.dockerignore` at repo root; `apps/web/src/app/api/assistant/stream/route.ts` sets `runtime = "nodejs"` and `maxDuration = 60` |
| The deliverable is marked complete and evidence-backed | `PROGRESS.md:247` — `M-DEPLOY … 8/8 checks` |
| The migration chain is linear with one base and one head | asserted by `apps/api/tests/test_deployment.py` |
| **No cloud resource exists yet** | design spec header: "§5 runbook not yet run — no cloud resource exists yet". Nothing in the repo references a live hostname |
| Local Docker Postgres is up and healthy | `docker ps` → `agrivardhak-db  Up (healthy)` |
| The API image needs no build toolchain | `psycopg[binary]` ships wheels, GeoAlchemy2 is pure Python, passwords use stdlib PBKDF2 (`api/passwords.py`) — nothing native to compile |
| `alembic` is a **runtime** dependency, so Render's pre-deploy command works inside the image | `apps/api/pyproject.toml` → `dependencies = [… "alembic>=1.14" …]` |

### 1.2 What is NOT ready — the blockers between here and a deploy

| # | Blocker | Why it blocks |
|---|---|---|
| **P1** | Branch `feat/data-observer` is **6 commits ahead of `main`, 0 behind**, and carries **28 uncommitted files** — an in-flight Hindi/English i18n feature (`apps/web/src/lib/i18n.ts`, `lib/locale.ts`, `components/language-toggle.tsx`, `app/actions/`, plus edits to every farmer and FPO page) | Vercel and Render deploy from a **git branch**. Uncommitted work does not ship. Half-finished work that *does* ship breaks the build. This must be resolved first — see Q2. |
| **P2** | No Supabase / Render / Vercel resources, no production secrets | Phases 1–4 |
| **P3** | `AGRI_JWT_SECRET` is still the dev default in `.env.example` | A known secret in production means anyone can mint a CEO token. Non-negotiable, see step 3.2 |

### 1.3 Verification block — run this first, every session

```bash
cd /Users/divya/Documents/agri-tech
git status --short | wc -l          # 28 on 2026-08-30 → uncommitted i18n work still open
git rev-list --left-right --count main...HEAD   # "0  6" → branch ahead of main by 6
git log --oneline -5
ls apps/api/alembic/versions/a0000000boot_extensions_and_uuidv7.py   # bootstrap migration
grep -n "M-DEPLOY" -A2 PROGRESS.md | head -5
docker ps --format '{{.Names}}\t{{.Status}}'
```

If any of these disagree with §1.1/§1.2, **stop and re-derive** before asking §2's questions —
some answers below assume this state.

---

## 2. The question round — ask these before touching a console

> Ask in groups. Give the recommendation. Record every answer in §3.

### Group A — what this deployment *is* (ask first; it changes everything below)

**Q1. What is this deployment for?**

| Option | What it changes |
|---|---|
| **(a) Demo / judging link** *(recommended if there are no real farmers yet)* | `AGRI_ENVIRONMENT=demo` → the sign-in page keeps offering the seeded demo accounts (`api/login.py:154` allows `local`, `demo`, `test` only). Free/cheap tiers become defensible. Hardening §8 can be deferred. |
| **(b) Live pilot with real FPO users** | `AGRI_ENVIRONMENT=production` → `/api/v1/auth/demo-accounts` returns **404** and the login page shows no credentials (it degrades gracefully to an empty list, `app/login/page.tsx:32`). You must create real users, and §8 hardening (backups/PITR, secret handling, migration review) is mandatory before the first real record. |
| **(c) Staging dry run** | Same as (a) but with a throwaway Supabase project you expect to delete. Everything here still applies; skip §8. |

Consequence to state out loud when asking: **choosing `production` hides the demo logins.**
If someone plans to open the URL and click "ceo@demo.agrivardhak", they want `demo`.

**Q2. What ships — which branch, and what happens to the uncommitted i18n work?**

The repo has 28 uncommitted files implementing a language toggle across the farmer and FPO
screens. Options:

| Option | Steps implied |
|---|---|
| **(a) Finish it, then merge to `main`, deploy `main`** *(recommended)* | Complete the i18n work → `make check && make test` green → commit → merge `feat/data-observer` → `main` → both hosts track `main` |
| **(b) Ship the branch as-is** | Commit the i18n work (or `git stash` it) → both hosts track `feat/data-observer`. Faster, but the deployed branch keeps moving under you as you develop |
| **(c) Stash i18n, merge the 6 branch commits to `main`, deploy `main`** | The language toggle is absent from the deployment; nothing else is lost |

Never: deploy `main` as it stands — it is missing all 6 data-observer commits.

**Q3. Is a live LLM required, and which keys do you have in hand right now?**

| Key | If present | If absent |
|---|---|---|
| `AGRI_ANTHROPIC_API_KEY` | narrated Decision Packets and a real assistant | set `AGRI_USE_FIXTURES=true` — deterministic module output, packets rendered unnarrated (NFR-303). The product still works; it reads flatter |
| `AGRI_NVIDIA_API_KEY` (intent router, ADR-0011) | questions route to the right handler | set `AGRI_LLM_PROVIDER=none` — keyword routing. **Be explicit that this is a known degradation:** ADR-0020 records that a dead router silently turns every question into a Decision Packet |

`AGRI_USE_FIXTURES` is an **LLM kill-switch only** — the ingestion adapters read committed
files from `seed/generated/` regardless of it. "Live LLM over committed data" is
`AGRI_USE_FIXTURES=false` plus real keys. `DATA_GOV_IN_API_KEY` is a *local fetcher* key and
is **not needed** in any cloud environment.

### Group B — hosting accounts and money

**Q4. Do you already have Supabase, Render and Vercel accounts, and can this be a paid tier?**

Free tiers have failure modes that read as outages to a user:
- Supabase free: the project **pauses after 7 days idle**.
- Render free: the service **sleeps after 15 min** and wakes in ~50 s.
- Vercel Hobby: fine for this, but is **not licensed for commercial use**.

Recommendation for a judged demo you will open on a known date: free tiers are acceptable if
you wake both services 30 minutes before. For a pilot with real users: Supabase Pro (~$25/mo)
+ Render Starter (~$7/mo).

**Q5. Region — Singapore for both Render and Supabase, confirmed?**

Recommended: yes. ADR-0019 rejects Mumbai-for-Supabase because Render has no Mumbai region,
and the orchestrator makes many DB round trips per decision packet against one browser round
trip. Co-location beats user proximity here. Only revisit if a data-residency requirement
exists — say so if the user mentions one, because that changes the topology, not just a
dropdown.

**Q6. Custom domain, or `*.vercel.app`?**

`*.vercel.app` is the default and needs no DNS. A custom domain must be added as a **second
element** of `AGRI_CORS_ORIGINS` and requires DNS records. Note that Vercel **preview**
deployments get per-deployment hostnames that will not be in the CORS list — preview builds
cannot call the API, which is the correct default for a pilot.

### Group C — data

**Q7. Seed the synthetic 1,000-farmer Prayagraj FPO into the pilot database?**

Recommended: **yes** — `make seed` is a one-time hand-run bootstrap (ADR-0019 §5). It is
never wired into a deploy hook.

**Q8. Will this database ever hold real (non-synthetic) farmer data?**

If yes, §8 hardening is mandatory **before the first real record**: PITR/backups, a consent
record per INV-9, and a review policy for every future migration (the Render pre-deploy runs
`upgrade head` against live data, and append-only tables per DR-04 make some column changes
irreversible by design).

**Q9. Does semantic (vector) retrieval need to work in production, or is lexical search
acceptable?**

The API image installs `apps/api` **without** the `[embed]` extra and ships no model file
(`knowledge/embed.py:41` looks for `apps/api/models/multilingual-minilm`). So in production,
retrieval falls back to Postgres lexical search — the documented, supported fallback.

- **(a) Accept lexical** *(recommended — zero work, and it is the designed degradation)*
- **(b) Enable vectors** — add `-e "apps/api[embed]"` plus a model-download step to the
  `Dockerfile`, growing the image by ~120 MB and the build by minutes. Do **not** do this
  unless the user asks: it is not in the design spec, so it needs its own ADR note.

### Group D — process

**Q10. Who runs the console steps?** The assistant cannot click through Supabase, Render or
Vercel dashboards. Confirm the human will do steps marked **[HUMAN]** and paste back the
values marked **→ record**. Everything marked **[CLI]** the assistant can run.

**Q11. Any deadline?** If a demo is at a fixed hour, schedule Phase 2 (`make seed` over a
pooled connection takes several minutes) and the free-tier wake-up accordingly.

---

## 3. Answer record — fill this in, then commit

| # | Question | Answer | Decided on |
|---|---|---|---|
| Q1 | Purpose / `AGRI_ENVIRONMENT` | _(demo / production / staging)_ | |
| Q2 | Branch that ships; i18n disposition | | |
| Q3 | Anthropic key? NVIDIA key? `AGRI_USE_FIXTURES`? | | |
| Q4 | Accounts exist? Paid or free tier? | | |
| Q5 | Region | | |
| Q6 | Domain | | |
| Q7 | Seed synthetic FPO? | | |
| Q8 | Real farmer data ever? | | |
| Q9 | Vector retrieval or lexical? | | |
| Q10 | Who runs console steps | | |
| Q11 | Deadline | | |

**Resources created** (fill in as you go — this is the recovery record):

| Resource | Value |
|---|---|
| Supabase project ref | |
| Supabase session-pooler URI | *(never paste the password here — password manager only)* |
| Render service URL | `https://__________.onrender.com` |
| Vercel deployment URL | `https://__________.vercel.app` |
| `AGRI_JWT_SECRET` | *(password manager only)* |

---

## 4. The ordering constraint (why the phases are not parallel)

```
Local gate ──▶ Supabase ──▶ schema + seed ──▶ Render ──▶ Vercel ──▶ CORS ──▶ verify
   §5            §6.1          §6.2           §6.3       §6.4      §6.5      §7
```

There is one circular dependency: **Vercel needs Render's URL** (`NEXT_PUBLIC_API_URL`) and
**Render's CORS needs Vercel's domain** (`AGRI_CORS_ORIGINS`). Render goes first because its
hostname is derivable from the service name; CORS is filled in afterwards at §6.5.

---

## 5. Phase 0 — the local gate (do not skip)

Nothing below is cloud work. It is the gate that makes the cloud work boring.

**5.1 Resolve the uncommitted work** per Q2. If finishing the i18n feature:

```bash
cd /Users/divya/Documents/agri-tech
git status --short              # expect the 28 files from §1.2
make check                      # ruff + ruff format --check + eslint + mypy + tsc
make test                       # pytest (381 passing as of the last spec run) + vitest (8)
```

Expected: both exit 0. A failing `tsc` here is a failing Vercel build later — Vercel runs
`next build`, which typechecks.

**5.2 Prove the bootstrap migration on a database you can throw away.**

```bash
make db-reset && make upgrade && make seed && make test
```

`db-reset` recreates the volume, so `infra/initdb/01-extensions.sql` *and* the new bootstrap
migration both run — the path most likely to break. Expected `make seed` tail:

```
  farmers        1,000
  total area     2,412 acres
```

Those two numbers are what `docs/DEMO-CONTEXT.md` asserts and what §7 re-checks against
Supabase.

**5.3 Commit and merge** per Q2's answer. Then:

```bash
make progress          # regenerate PROGRESS.md from what the repo can prove
git log --oneline -3
```

**Gate: do not open a cloud console until 5.1–5.3 are green and committed.**

---

## 6. Deployment phases

Legend: **[HUMAN]** = browser/console work · **[CLI]** = the assistant can run it.

### 6.1 Phase 1 — Supabase (Postgres)

**Step 1 [HUMAN] — create the project.**
- Region: **Singapore (`ap-southeast-1`)** (Q5).
- Plan per Q4. Free pauses after 7 days idle.
- Set a strong database password and **store it in a password manager immediately** —
  Supabase shows it once. → record.

**Step 2 [HUMAN] — copy the connection string.**
Dashboard → **Connect** → **Session pooler**, port **5432**.

> Take **only** the session pooler.
> - "Direct connection" is **IPv6-only** and Render's egress is IPv4 → unreachable (B3).
> - "Transaction pooler" on **6543** forbids prepared statements, which psycopg uses.

Shape:
```
postgresql://postgres.<project-ref>:<password>@aws-N-ap-southeast-1.pooler.supabase.com:5432/postgres
```
Copy it rather than assembling it — the `aws-N` prefix varies by project.

**Step 3 [CLI] — convert it for this codebase.** Two edits:
1. scheme `postgresql://` → **`postgresql+psycopg://`**
2. **percent-encode the password**: `@`→`%40`, `#`→`%23`, `/`→`%2F`, `:`→`%3A`, `?`→`%3F`

### 6.2 Phase 2 — schema and data into Supabase

**Step 4 [CLI] — migrate.** From the repo root:

```bash
export AGRI_DATABASE_URL="postgresql+psycopg://postgres.<ref>:<encoded-pw>@aws-N-ap-southeast-1.pooler.supabase.com:5432/postgres"
cd apps/api && .venv/bin/alembic upgrade head && cd -
```

An exported environment variable outranks `apps/api/.env` (pydantic-settings precedence), so
your local Docker setup is untouched.

> **Do not trust the log.** Alembic has printed `Running upgrade` for every revision and
> exited 0 having created **zero tables** — see §9, row "silent no-op". Verify in SQL.

**Step 5 [HUMAN] — verify in the Supabase SQL editor:**

```sql
select uuid_generate_v7();                       -- a v7 uuid → bootstrap migration worked
select extname, nspname from pg_extension
  join pg_namespace n on n.oid = extnamespace;   -- postgis, pgcrypto, vector in "extensions"
select count(*) from information_schema.tables
  where table_schema='public' and table_type='BASE TABLE';
```

**Expect 51** — one *lower* than Docker's 52. Both hold the same 50 domain tables plus
`alembic_version`; Docker additionally counts `spatial_ref_sys` in `public` because
`initdb/01-extensions.sql` creates PostGIS with no `WITH SCHEMA`. Under the bootstrap
migration it lands in `extensions` and drops out of the count. Both figures are *measured*.
(`scripts/progress.py:379` asserts a **floor** of 49, not equality — 51 and 52 both pass.
The 49 is stale, not wrong. Do not "fix" it.)

**Step 6 [CLI] — seed once** (skip only if Q7 said no), with the same variable exported:

```bash
make seed
```

Expect **several minutes** — 1,000 farmers and two seasons of history over a pooled
connection. `make seed` also lands the external records, knowledge chunks and policy events,
so no separate `make ingest` is needed for a first bootstrap.

**Step 7 [HUMAN] — confirm the numbers the demo asserts:**

```sql
select count(*) from farmer;                    -- 1000
select round(sum(area_sqm)/4046.86) from plot;  -- 2412
```

**Step 8 [CLI] — disarm the shell:**

```bash
unset AGRI_DATABASE_URL
```

So you never later run tests, `make seed-reset`, or a stray migration against the pilot
database. **Do this before moving on.**

### 6.3 Phase 3 — Render (FastAPI)

**Step 9 [HUMAN] — create the Web Service.**

| Setting | Value | Why |
|---|---|---|
| Repository / branch | the branch from Q2 | |
| Runtime | **Docker** | |
| Dockerfile path | `./Dockerfile` | |
| **Root directory** | **blank (repo root)** | Non-negotiable. `ingestion/weather.py:40` and `agmarknet.py:33` resolve fixtures as `parents[4]/"seed"/"generated"` **at runtime**. An `apps/api`-only image builds clean, starts, passes health, and fails on the first weather or market question |
| Region | **Singapore** | |
| Instance type | **Starter or above** (per Q4) | free sleeps after 15 min |
| Health Check Path | `/api/v1/health` | |
| Pre-Deploy Command | `cd apps/api && alembic upgrade head` | keeps schema and code in step on every push. **`upgrade`, never `seed`** |

**Step 10 [HUMAN] — environment variables:**

| Key | Value |
|---|---|
| `AGRI_DATABASE_URL` | the converted session-pooler URI from step 3 |
| `AGRI_JWT_SECRET` | **fresh**: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` — never the dev default |
| `AGRI_ENVIRONMENT` | per Q1 (`demo` keeps the demo logins; `production` hides them) |
| `AGRI_DEBUG` | `false` |
| `AGRI_USE_FIXTURES` | per Q3 — `false` for a live LLM |
| `AGRI_ANTHROPIC_API_KEY` | per Q3 |
| `AGRI_LLM_PROVIDER` | `nvidia`, or `none` if you have no NVIDIA key |
| `AGRI_NVIDIA_API_KEY` | per Q3 |
| `AGRI_ROUTER_MODEL` | `openai/gpt-oss-20b` (only if overriding the default) |
| `AGRI_CORS_ORIGINS` | placeholder `["http://localhost:3000"]` — corrected at step 13 |

> `AGRI_CORS_ORIGINS` is a `list[str]`, parsed by pydantic-settings as **JSON**. It must be a
> bracketed, double-quoted array. A bare comma-separated string **raises at startup**.

**Do not set** `AGRI_DEV_TOKEN` anywhere in the cloud (see step 12).

**Step 11 [CLI] — deploy, then prove it end to end:**

```bash
curl -s https://<service>.onrender.com/api/v1/health | python3 -m json.tool
```

Expected:
```json
{
  "status": "ok",
  "environment": "demo",
  "use_fixtures": false,
  "checks": { "database": "ok", "postgis": "3.4.3", "vector": "0.8.6" }
}
```
The handler runs `select 1` plus two `pg_extension` lookups, so a 200 with `"database": "ok"`
proves **Render → Supabase over the pooler, with the `extensions` search path**, end to end.
`"status": "degraded"` with `"postgis": "missing"` means the search path or the bootstrap
migration did not take — go to §9. → record the URL.

### 6.4 Phase 4 — Vercel (Next.js)

**Step 12 [HUMAN] — import the repo.**

| Setting | Value |
|---|---|
| **Root Directory** | **`apps/web`** — the Next.js app is self-contained (own `package.json`, no workspace deps) |
| Framework preset | Next.js (auto-detected) |
| Branch | the same branch as Render (Q2) |
| Env var | `NEXT_PUBLIC_API_URL = https://<service>.onrender.com` |

`NEXT_PUBLIC_` is correct and not a leak — `app/login/page.tsx:27` reads it client-side, and
it is a public hostname.

> **Never set `AGRI_DEV_TOKEN` on Vercel.** `lib/session.ts:36` falls back to it when no
> session cookie is present, so a static CEO token in production would hand **every anonymous
> visitor CEO scope**. That fallback exists for `make dev-env` and must stay local.

The session cookie is `httpOnly`, `sameSite=lax`, and `secure` whenever `NODE_ENV==="production"`
(`app/api/auth/login/route.ts:45`) — so the deployment must be served over HTTPS, which
Vercel does by default. → record the URL.

### 6.5 Phase 5 — close the loop

**Step 13 [HUMAN] — set the real CORS origin.** Back in Render:

```
AGRI_CORS_ORIGINS=["https://<your-app>.vercel.app"]
```

Add a custom domain as a **second array element** if Q6 said so:
`["https://<app>.vercel.app","https://app.yourdomain.in"]`. Redeploy Render.

Vercel preview deployments will *not* be in this list and therefore cannot call the API. That
is the intended default for a pilot; if previews must work, that is a deliberate decision to
record, not a bug to patch.

---

## 7. Phase 6 — verification against the invariants

A homepage that renders proves almost nothing. Check these, in order, and record pass/fail.

| # | Check | Passes when | What it actually proves |
|---|---|---|---|
| V1 | `GET /api/v1/health` | `"status":"ok"`, database ok, postgis + vector versions present | Render→Supabase, pooler, `extensions` search path |
| V2 | Sign in as `ceo@demo.agrivardhak` / `agrivardhak` | dashboard renders; cookie `agrivardhak_session` set by the Vercel route handler, `httpOnly` + `secure` | Vercel→Render, CORS, JWT secret, login path |
| V3 | Open a Decision Packet, expand the evidence drill-down | evidence resolves | PostGIS geography columns resolve under the `extensions` search path in real queries (blocker B2) |
| V4 | Ask the assistant a question | a **narrated** answer, not the keyword fallback | LLM keys live and `AGRI_USE_FIXTURES=false`. If every question comes back as a Decision Packet, the router fell back — check `fell_back` on the routing event **first** (ADR-0020) |
| V5 | Ask a weather or market question | real numbers, no 500 | `seed/generated/` shipped in the image (`parents[4]` resolved) — the failure the repo-root build context exists to prevent |
| V6 | Sign in as `farmer@demo.agrivardhak` | every `/fpo/*` and `/decisions` route returns **403** | **INV-5**, the information boundary |
| V7 | Approve a recommendation | state advances only with an `Approval` row; no path writes `EXECUTED` without one | **INV-1**, human-in-the-loop |
| V8 | Farmer directory listing | sorts in **dictionary** order, not ASCII | the one accepted behavioural difference — Supabase forces `en_US.UTF-8` where Docker uses `--locale=C`. Audited: it cannot reach an `EvidenceSnapshot`, so **INV-2 holds** |
| V9 | If `AGRI_ENVIRONMENT=production` | `/api/v1/auth/demo-accounts` → **404**, login page shows no seeded credentials | Q1's consequence, working as designed |

Demo passwords: all seeded accounts share `agrivardhak`
(`ceo@`, `officer@`, `admin@`, `farmer@` `demo.agrivardhak`).

---

## 8. Phase 7 — hardening (mandatory before any real farmer record)

- **Backups.** Enable Supabase daily backups; enable **PITR before the first real record
  exists**. The seed is reproducible; real user data is not.
- **Secrets.** `AGRI_JWT_SECRET` and the database password live only in Render's environment
  and your password manager — never in a file, never in git (NFR-403). Rotating the JWT
  secret invalidates every live session; do it on any suspected exposure.
- **`make seed-reset` is a loaded gun.** It truncates every table. It must never appear in a
  Render command field. Consider gating it behind `AGRI_ENVIRONMENT == "local"`.
- **Migration review.** Render's pre-deploy runs `alembic upgrade head` against live data on
  every push. From the first real user onward, every migration is reviewed for destructive
  DDL — append-only tables (DR-04) make some column changes irreversible **by design**.
- **Demo accounts.** With real users, `AGRI_ENVIRONMENT=production` hides them from the login
  page but the rows still exist with a known password. Deactivate or delete them.
- **Consent (INV-9).** Real farmer data requires an explicit, per-purpose, revocable consent
  record before collection — not after.

---

## 9. Troubleshooting — failures already seen or specifically predicted

| Symptom | Cause | Fix |
|---|---|---|
| `alembic upgrade head` prints `Running upgrade` for every revision, **exits 0, and creates zero tables** — not even `alembic_version` | A `SET search_path` executed **after** `connect()`. On a SQLAlchemy 2.0 connection that implicitly opens a transaction; Alembic's `begin_transaction()` nests inside it, its commit does not commit the outer transaction, and closing the connection rolls everything back | The search path must be a **libpq connection option**, never a `SET` statement. Both call sites import `SEARCH_PATH_OPTION` from `db/base.py`. If someone "simplified" that, revert. **Always verify with SQL, not with the log.** |
| `CREATE TABLE` fails: `function uuid_generate_v7() does not exist` | The bootstrap migration did not run — the chain lost its base, or you pointed at a database stamped by something else | Confirm `a0000000boot_extensions_and_uuidv7.py` has `down_revision = None` and that `b8effdc6a2cb.down_revision == "a0000000boot"`. `apps/api/tests/test_deployment.py` asserts both |
| `type "geography" does not exist` / geometry errors on plot queries | PostGIS is in `extensions` and the search path is missing (blocker B2) | Check `connect_args` on the engine (`db/session.py:24`) and that Render's `AGRI_DATABASE_URL` is the one the app actually reads |
| Render cannot reach the database; connection times out | You used the **direct** connection — IPv6-only; Render egress is IPv4 (B3) | Use the **session pooler on 5432** |
| `prepared statement "..." already exists` / psycopg errors under load | You used the **transaction** pooler on 6543 | Session pooler, port 5432 |
| Auth fails with a password containing `@`, `#` or `/` | The URI password was not percent-encoded | `@`→`%40`, `#`→`%23`, `/`→`%2F` |
| Render service crashes at startup, before any request | `AGRI_CORS_ORIGINS` set as a bare comma-separated string | It is parsed as **JSON**: `["https://app.vercel.app"]` |
| Browser console: CORS blocked | The Vercel origin is not in `AGRI_CORS_ORIGINS`, or you are on a **preview** deployment | Step 13. Preview hostnames are excluded by design |
| Sign-in appears to succeed, then every page says signed out | Cookie dropped — `secure` cookie over plain HTTP, or a domain mismatch | Serve over HTTPS (Vercel default). Check `NEXT_PUBLIC_API_URL` has no trailing slash |
| Anonymous visitors land straight in the CEO dashboard | `AGRI_DEV_TOKEN` was set on Vercel; `lib/session.ts:36` falls back to it | **Delete that variable immediately and rotate `AGRI_JWT_SECRET`** — every token minted with the old secret stays valid until it does |
| App is up; weather/market questions 500 | The image was built with root directory `apps/api`, so `parents[4]/seed/generated` does not resolve | Root directory **blank**; `.dockerignore` must **not** exclude `seed/generated/` (~23 MB, it is application data) |
| Every question returns a Decision Packet regardless of what was asked | The router model was retired by the provider; a 410 does not raise, it falls back to keywords (ADR-0020) | Check `fell_back` on the routing event, then update `AGRI_ROUTER_MODEL` |
| Assistant answers are flat/unnarrated | `AGRI_USE_FIXTURES=true`, or no Anthropic key | Set `false` **and** supply the key — it is an LLM kill-switch, not a data switch |
| Retrieval feels keyword-ish in production | The image has no sentence encoder (Q9) — lexical fallback, by design | Accept, or take Q9 option (b) with its own ADR note |
| Vercel build fails on types | `tsc` was not green locally | §5.1. Vercel runs `next build`, which typechecks |
| Table count is 51, not 52 | Expected — `spatial_ref_sys` lives in `extensions` on Supabase | Not a bug. §6.2 step 5 |
| First request of the day takes ~50 s | Render free tier slept | Starter tier, or wake it before the demo |
| The whole project is unreachable after a quiet week | Supabase free tier paused it | Resume in the dashboard; upgrade for a pilot |

---

## 10. State tracker — update as you go, commit after each phase

```
[ ] P0.1  i18n work resolved (Q2)              [ ] P3.1  Render service created
[ ] P0.2  make check green                     [ ] P3.2  Render env vars set (JWT fresh)
[ ] P0.3  make test green                      [ ] P3.3  /api/v1/health → status ok
[ ] P0.4  db-reset → upgrade → seed → test     [ ] P4.1  Vercel imported, root=apps/web
[ ] P0.5  merged / branch chosen, committed    [ ] P4.2  NEXT_PUBLIC_API_URL set
[ ] P1.1  Supabase project (Singapore)         [ ] P5.1  AGRI_CORS_ORIGINS → real origin
[ ] P1.2  session-pooler URI stored            [ ] P5.2  Render redeployed
[ ] P2.1  alembic upgrade head                 [ ] V1..V9 verification matrix (§7)
[ ] P2.2  SQL verify: uuid_v7, extensions, 51  [ ] H1..H6 hardening (§8, if real users)
[ ] P2.3  make seed → 1000 farmers, 2412 acres [ ] PROGRESS.md regenerated, §3 filled in
[ ] P2.4  unset AGRI_DATABASE_URL
```

---

## 11. Rollback and teardown

- **Bad code deploy.** Render → *Rollback* to the previous deploy; Vercel → *Instant
  Rollback* to the previous production deployment. Both are one click and do not touch the
  database.
- **Bad migration.** `alembic downgrade -1` **only if** the revision has a real `downgrade()`.
  The bootstrap revision's `downgrade()` drops only `uuid_generate_v7()` — it deliberately
  does not drop PostGIS from under a live database. Append-only tables (DR-04) mean some
  changes have no reversal: restore from a Supabase backup instead.
- **Database is wrong / experiment failed.** Because this is schema + re-seed rather than a
  binary restore, the cheapest recovery for a *synthetic* database is a fresh Supabase
  project → `alembic upgrade head` → `make seed`, then repoint `AGRI_DATABASE_URL`. Never do
  this against a database holding real farmer data.
- **Full teardown.** Delete the Vercel project, the Render service, the Supabase project, in
  that order (so nothing tries to call a dead API mid-teardown). Rotate any key that was
  pasted into a console.

---

## 12. What this deployment deliberately does not include

Per the design spec §8 — if the user asks for any of these, it is new scope with its own ADR:
no CI/CD beyond Render and Vercel's git triggers; no Render Cron Job (fetchers stay local,
fixtures stay committed); no staging Supabase project (the bootstrap migration makes one
cheap to add — that is most of the point of choosing it over a hand-run SQL script); no CDN
tuning, no rate limiting, no WAF.

---

## 13. Repo obligations when the deployment lands

Per `CLAUDE.md` §8, closing this out means:

1. **`make progress`** — regenerate `PROGRESS.md`.
2. **Update the design spec header** — `docs/superpowers/specs/2026-08-29-supabase-vercel-render-deployment-design.md`
   currently says "§5 runbook not yet run — no cloud resource exists yet". Once it has run,
   say so, with the date and the resulting URLs.
3. **A new ADR only if you deviated** from ADR-0019 — a different region, a different tier
   topology, PostgREST, vector extras in the image. Record the deviation and why; do not
   silently diverge from an accepted ADR.
4. **Fill in §3 of this file and commit it.** The next session's first question is "what did
   we already decide?", and this table is the answer.
