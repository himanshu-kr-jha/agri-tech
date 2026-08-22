# ADR-0001 — Next.js + FastAPI + PostgreSQL as the stack

Date: 2026-08-22 · Status: Accepted

## Context

48–72 hours, 3–5 people, and a system whose distinguishing work is agronomic/statistical
computation plus LLM orchestration — not CRUD. We need geospatial plot boundaries, vector
search over scheme and news text, strict typing on the intelligence layer, and a UI that
renders confidence and provenance on nearly every number.

## Decision

- **Web:** Next.js 15 (App Router) + TypeScript + Tailwind + shadcn/ui.
- **API/AI:** Python 3.12 + FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic.
- **Data:** PostgreSQL 16 with PostGIS and pgvector — one store for relational, geospatial and
  embedding workloads.
- The web tier never touches the database; all access goes through the API.

## Consequences

**Easier.** Python owns the schema and the intelligence modules, where the type discipline
matters most (`mypy --strict`). Pydantic models generate both the OpenAPI document and the
TypeScript client types, so the contract cannot drift. One database means no cross-store
consistency problem for the evidence snapshot, and PostGIS/pgvector avoid two extra services.

**Harder.** Two languages means two toolchains, two CI lanes, and a generated-types step that
must stay in the loop. Server Components cannot call Python directly; every read is an HTTP hop.

**Accepted.** The single API enforcement point is worth the hop: authorization, provenance
resolution and the information boundary each have exactly one place to be correct.

## Alternatives considered

- **Full TypeScript (tRPC + Prisma).** One language, faster CRUD. Rejected: the intelligence
  modules are the product, and Python's numeric/agronomic ecosystem plus Pydantic's schema
  discipline matter more than saving a toolchain. Prisma's PostGIS story is also weak.
- **Django + DRF.** Free admin panel for data entry is genuinely attractive under time
  pressure. Rejected: Django's ORM and forms pull toward CRUD-shaped thinking, and the admin
  would tempt us to skip the provenance layer for direct table edits — which would break INV-3.
- **Separate vector DB / message broker.** Rejected: two more services to run at the demo, for
  a workload Postgres handles at this scale (ADR-0007).
