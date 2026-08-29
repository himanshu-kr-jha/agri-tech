# ADR-0018 — Deployment topology and the Supabase extension boundary

Date: 2026-08-29 · Status: Accepted

## Context

The MVP ran on `docker compose`: one Postgres container whose `infra/initdb/01-extensions.sql`
installed PostGIS, pgcrypto and `uuid_generate_v7()` before the first migration, one FastAPI
process, one Next.js process. A live pilot — real FPO users, not a demo link — has to run on
managed infrastructure, and three assumptions baked into the local setup do not survive the move.

**Extensions.** Every table's primary key is `server_default=text("uuid_generate_v7()")`, and
that function exists only because a container entrypoint script ran. A managed Postgres never
runs `initdb/`. On Supabase, `alembic upgrade head` against a fresh project fails on the first
`CREATE TABLE`: the schema is not self-sufficient.

**Extension schema.** Supabase installs extensions into an `extensions` schema, not `public`.
GeoAlchemy2 emits an unqualified `geography(POLYGON,4326)` for `plot.boundary`
(`domain/models/land.py:56`), which does not resolve when PostGIS lives outside the search path.
Docker's `01-extensions.sql` puts PostGIS in `public`, so the same schema has to work against
two different extension locations.

**Connectivity.** Supabase's direct connection is IPv6-only; Render's egress is IPv4.

Underneath all three sits the question Supabase invites: it makes direct browser→Postgres access
easy, so should the web tier keep going through FastAPI at all?

## Decision

**Vercel (Next.js) → Render (FastAPI, Docker, built from the repo root) → Supabase (Postgres),
Render and Supabase both in Singapore.**

1. **The web tier still never touches Postgres.** No Supabase anon or service key is given to
   Vercel. ADR-0001 makes FastAPI the single enforcement point for authorization, provenance
   resolution and the INV-5 information boundary; PostgREST would relocate that boundary into RLS
   policies and client code, which is the failure INV-5 names.

2. **Extensions move from `initdb/` into a base Alembic revision**
   (`a0000000boot_extensions_and_uuidv7`, `down_revision = None`). `CREATE SCHEMA IF NOT EXISTS
   extensions` then `CREATE EXTENSION ... WITH SCHEMA extensions` — a no-op relocation risk on
   neither host, because `IF NOT EXISTS` leaves an extension already living in `public` exactly
   where it is. `uuid_generate_v7()` is created in `public` with a function-level
   `SET search_path = public, extensions`, because its body calls `gen_random_bytes`, whose schema
   differs between the two hosts. `alembic upgrade head` is now sufficient on any empty Postgres.

3. **`search_path = public, extensions` is set as a libpq connection option in code**, from one
   constant (`db/base.py:SEARCH_PATH_OPTION`) used by both the runtime engine and `alembic/env.py`
   — not as a hand-run `ALTER ROLE`, and specifically **not** as a `SET` statement after connect.

4. **Supavisor session pooler, port 5432** — IPv4-reachable and prepared-statement-safe, unlike
   transaction mode on 6543. `pool_recycle=300` on the engine, against a pooler that reaps idle
   connections.

5. **Schema + re-seed, not `pg_dump`.** `seed/generated/` is 23 MB of committed fixtures and the
   whole database is reproducible from the repo, so the pilot database is bootstrapped by
   `alembic upgrade head` + one hand-run `make seed`. `make seed` is never wired into a deploy
   hook; Render's pre-deploy command is `alembic upgrade head` and nothing else.

6. **The Docker build context is the repo root**, because `ingestion/weather.py:40` and
   `agmarknet.py:33` resolve fixtures as `parents[4] / "seed" / "generated"` at *runtime*. An
   `apps/api`-only image builds clean, starts, passes its health check, and fails on the first
   weather or market question.

## Consequences

**Easier.** A new environment is `createdb` + `alembic upgrade head` — a staging project costs
nothing to add. The schema is finally self-contained: no environment depends on a container
entrypoint. Local Docker is unaffected; the bootstrap migration is idempotent against a database
where `01-extensions.sql` already ran, and Postgres ignores a `search_path` entry naming a schema
that does not exist.

**Harder.** Three tiers, three consoles, three sets of secrets, and a circular dependency at setup
(Vercel needs Render's URL; Render's CORS needs Vercel's domain) that forces the runbook ordering.
Render's pre-deploy `upgrade head` runs against live data from the first real user onward, so every
future migration needs review for destructive DDL — append-only tables (DR-04) make some column
changes irreversible by design.

**Accepted.** One expected behavioural difference: Supabase forces `en_US.UTF-8` where Docker uses
`--locale=C`, so `ORDER BY farmer.full_name` sorts in dictionary rather than ASCII order. Audited
against INV-2 and it cannot reach an `EvidenceSnapshot` — `gather.py` has no SQL `ORDER BY`, the
intelligence modules sort in Python with explicit keys, and `content_hash` is
`json.dumps(sort_keys=True)`. Also accepted: paid tiers on both Supabase and Render, because a free
Supabase project pauses after 7 days idle and a free Render service sleeps after 15 minutes — both
read to a pilot user as an outage.

## Alternatives considered

**Supabase client from Next.js, dropping FastAPI from the read path.** Rejected: it moves the INV-5
boundary into RLS policies and client code, and provenance resolution and `ContextScope` would have
to be reimplemented in SQL. ADR-0001's single enforcement point is the whole point.

**Keep `01-extensions.sql` and run it by hand in the Supabase SQL editor once.** Rejected: a live
pilot must not depend on a one-off console statement nobody wrote down, and it leaves the schema
non-reproducible for the next environment.

**`ALTER ROLE ... SET search_path` in the Supabase dashboard.** Rejected for the same reason, and
it would not apply to the Alembic connection under a different role.

**`SET search_path` executed after `connect()` in `alembic/env.py`.** Tried, and it failed in the
worst available way: on a SQLAlchemy 2.0 connection that statement implicitly opens a transaction,
so Alembic's `begin_transaction()` nests inside it, its commit does not commit the outer
transaction, and closing the connection rolls the whole migration back. It printed `Running
upgrade` for all six revisions and **exited 0 with zero tables created** — not even
`alembic_version`. Caught only by querying the database afterwards. Hence "connection option, not
`SET` statement", recorded on `SEARCH_PATH_OPTION`.

**`pg_dump` from Docker, restore into Supabase.** Rejected: buys nothing that `make seed` does not,
and adds binary-restore failure modes (index collation, extension schema mismatch, ownership).

**Transaction pooler (6543) or the direct IPv6 connection.** Rejected: the direct connection is
unreachable from Render's IPv4 egress; transaction mode forbids prepared statements, which
psycopg uses.

**Mumbai for Supabase, closer to the users.** Rejected: Render has no Mumbai region, and the
orchestrator makes many database round trips per decision packet against one browser round trip.
Co-locating Render and Supabase in Singapore puts the latency on one HTTP hop instead of every
query.

## References

- Design and runbook: `docs/superpowers/specs/2026-08-29-supabase-vercel-render-deployment-design.md`
- ADR-0001 (stack; FastAPI as the only database tier), ADR-0009 (identifiers — `uuid_generate_v7`)
- INV-2 (frozen evidence), INV-5 (information boundary)
