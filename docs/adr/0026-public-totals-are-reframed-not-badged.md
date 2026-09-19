# ADR-0026 — Platform totals are public, and reframed rather than badged

Date: 2026-09-19 · Status: Accepted

## Context

The landing page needs live numbers, and the only numbers the platform holds are synthetic:
one seeded organization, 1,000 farmers, 7,258 crop cycles, 2,412 acres, every row flagged
`is_synthetic`. There was no unauthenticated endpoint to read them from.

Two rules pull against each other here. `CLAUDE.md` §8.5 says never present unsourced
figures, and UI-04 required a visible `DEMO DATA` marker on any value derived from seed
data. But a `DEMO DATA` chip on a public marketing page is the wrong instrument: it reads
as "this product is a mock-up", which is a stronger and less accurate claim than the honest
one, and it corrects a misreading the page should not have invited in the first place.

Publishing the count of collectives would also mean printing a large "1".

## Decision

- A new unauthenticated `GET /api/v1/public/platform-stats`, public by omitting the
  `CurrentScope` dependency — the same mechanism `/health` and `/auth/demo-accounts` use.
  Aggregates only; no organization, farmer or decision is identifiable in the response.
- **The verb carries the honesty.** Tiles read *Farmers modelled*, *Crop cycles analysed*,
  *Acres mapped* — true statements about a dataset, where a bare "1,000 Farmers" would be a
  claim about customers. A muted line beneath names the dataset: *Prayagraj pilot dataset.*
  Together these do UI-04's job on this surface, and UI-04 is amended in the same change to
  scope the chip to values presented as facts about an identifiable party.
- **The organization count is not a tile.** It is in the payload, not on the page.
- Acres are converted in the API, not the browser. Storage is square metres (ADR-0009) and
  the web tier does no unit arithmetic — a React component dividing by 4046.86 is how acres
  and hectares get mixed up.
- Checked-in fallback constants in `lib/public-stats.ts`, so the front door renders even
  when the API does not answer, with a 2s timeout bounding the wait.

## Consequences

**Easier.** The page states something true without a chip that overstates. The numbers stay
current by themselves. The API is the single place the synthetic/real distinction is decided,
via `is_synthetic` in the payload, rather than a UI assumption.

**Harder.** The English and the Python are bound only by a test.
`test_the_published_totals_match_the_demo_context` compares the endpoint to the figures
`lib/public-stats.ts` hard-codes; there is no compile-time bond across the two languages,
and that test is the whole bond.

**Accepted — and this needs a gate before it matters.** The moment a non-synthetic
organization is onboarded, this endpoint begins publishing that organization's real totals
to an anonymous caller. That sits adjacent to INV-9, the farmer owning their data. Before
any real org lands, the query must either aggregate only over `is_synthetic` rows or move
behind a per-organization opt-in. The caveat is repeated in `api/public.py`'s docstring,
which is where someone will actually be reading when it stops being hypothetical.

## On the caching, which is not what it looks like

The landing page is `force-dynamic`, because it reads the session cookie to redirect
signed-in visitors. That reads as though it would defeat the stats cache. It does not:
Next applies the no-store rule only to fetches carrying no explicit config of their own
(`patch-fetch.js`, `noFetchConfigAndForceDynamic`), and `getPublic()` passes
`next.revalidate`. So the page renders per request while the totals are read once an hour.

Two things would silently break that, neither of which fails loudly:

1. `export const fetchCache = …` on the page or the `(public)` layout. Unlike `dynamic`,
   that field *is* honoured, and would turn an hourly read into a query per cold view.
2. Routing the call through `api.ts`'s `get<T>()`, which attaches a bearer token. Any fetch
   carrying an `authorization` or `cookie` header is classed uncacheable. This is the real
   reason `getPublic<T>()` exists as a sibling rather than a reuse.

**Rejected.** `use cache` + `cacheLife`: it requires `cacheComponents: true`, which removes
`dynamic`/`revalidate`/`fetchCache` app-wide and demands Suspense around every request-time
API — and this app reads `cookies()` on every page. A whole-app migration to cache one
number. `unstable_cache` works and is not gated, but is deprecated in Next 16 in favour of
the option we just rejected.
