# ADR-0024 — The public surface is a route group with a top nav

Date: 2026-09-19 · Status: Accepted

## Context

Six pages are readable without an account: the landing page, About us, the FAQ, Privacy,
Terms and Sign in. Each had hand-rolled its own shell — a `flex min-h-screen flex-col`
column, a bare logo square, a language toggle and a `<Footer />` — and none of them linked
to the other five. A visitor who reached the privacy policy had no way back except the
browser's back button.

The console's left sidebar is not the answer. It is a 260px dark spine built for a working
tool you return to daily, it belongs to the `(fpo)` route group, and it was never mounted
on a public page. A marketing surface needs a horizontal bar that fits four links and a
sign-in button.

The design system also had to be confronted rather than ignored. `ui-clone-workspace/site-dna.md`
describes this product as "quiet institutional software dressed as fine print", classifies
its animation as "Tier 1 — CSS transitions only", forbids box-shadows, and permits gold
exactly once per screen. The landing page is the one surface that has to sell a vision to
someone who has never heard of the product, which is a different job from the one the
ledger aesthetic was designed for.

## Decision

- A `(public)` route group. Its layout owns the header, the column and the `Footer`; the
  six pages own only their content. `(public)`, not `(marketing)` — `/login` and `/terms`
  are in it and neither is marketing.
- One `PublicHeader` (server) wrapping a `PublicNav` (client, for `usePathname`), carrying
  Home · About us · Privacy policy · FAQ, plus the language toggle and a Sign-in button.
- **The landing page is the one place imagery and movement are allowed.** Full-bleed video,
  a 700ms slide, large tinted icon circles. Everything behind the login keeps the ledger.
- The exception is scoped by *register*, not by permission: the landing page still uses the
  same tokens, the same Fraunces/Inter Tight pairing, the same hairline borders, and still
  no box-shadows. It spends the page's single gold on the carousel's active indicator.
- The `(fpo)` and `(farmer)` groups are untouched.

## Consequences

**Easier.** Adding a public page is one file. The `Footer`'s full-bleed contract — it only
resolves when its parent is viewport-width — is now stated and satisfied in exactly one
place instead of being re-derived six times. Every public page can reach every other one.

**Harder.** Six directories moved, which makes one large move-only diff. Route-group
layouts do not appear in Next's generated `LayoutRoutes` union, so the layout is hand-typed
`{ children: React.ReactNode }`, as `(fpo)` and `(farmer)` already are.

**Accepted.** The guard must stay out of the group layout. `/login` lives in this group, so
a `currentUser()` redirect at the layout level would bounce a signed-in visitor off the page
they were just sent to. The two pages that redirect do it themselves, and the layout carries
a comment saying so.
