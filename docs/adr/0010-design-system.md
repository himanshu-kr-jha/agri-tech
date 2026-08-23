# ADR-0010 — A cloned design system: paper, hairlines, and a serif for every number

Date: 2026-08-23 · Status: Accepted

## Context

The web tier shipped on the stock Next.js template: Geist, neutral greys, `dark:` variants on
every element, `rounded-xl` cards with hover borders. It was legible and anonymous. For a
product whose entire claim is *"this number is trustworthy, and here is where it came from"*,
anonymity is a cost — a dashboard that looks like every other dashboard invites the reader to
skim it like every other dashboard.

We had a reference to work from: the Krishi·OS FPO Command Center preview
(`cultivate-core.preview.emergentagent.com`), a console for the same audience — an FPO
administrator in Uttar Pradesh. Its design language was extracted in full and recorded in
`ui-clone-workspace/site-dna.md`: tokens, type scale, interaction rules, and the animation tier.

Three properties of that reference are what made it worth adopting rather than admiring:

1. **No box-shadows anywhere.** Depth is carried entirely by 1px hairlines at 70% opacity.
   A dense console with shadows on every card reads as a pile of floating objects; the same
   console with hairlines reads as a printed ledger, which is closer to what this is.
2. **A serif carries every number.** Fraunces on the KPI values and titles, Inter Tight on
   everything functional. This directly serves our TypeScript convention that *every number
   rendered to a user gets a unit and, where AI-derived, a confidence chip* — the serif marks
   which strings on the page are claims about the world.
3. **The accent appears once per screen.** Gold `#C7A03D` is a 2px inset rail on the active
   nav item and nothing else. That discipline is what makes it possible for us to spend the
   accent on the things that actually need attention — an unapproved recommendation, a
   cross-domain override — without it competing with decoration.

## Decision

Adopt the reference's design system verbatim, in shadcn HSL-triplet token form, with three
deliberate departures.

**Tokens** live in `apps/web/src/app/globals.css` as bare HSL channels (`145 37% 16%`) rather
than finished colours, so that every utility can take an alpha modifier. `border-border/70` is
the single most-used value in the UI and it needs the channels.

**Fonts**: Fraunces (variable, `opsz` axis loaded) for titles and quantities, Inter Tight for
UI, JetBrains Mono for identifiers. Loaded through `next/font/google`, self-hosted at build.

**Shell**: the FPO console gets a 260px `#132A1D` sidebar plus a sticky organization header.
The farmer portal deliberately does *not* — it keeps its single-column, 17px, phone-first
layout. It shares the palette and the serif; it does not share the information architecture,
because it is read outdoors on a shared phone by someone who is not doing console work.

**Light only.** Every `dark:` variant was removed from the web tier.

### Departures from the reference

| # | Reference does | We do | Why |
|---|---|---|---|
| 1 | No confidence indicator exists | `ConfidenceChip` beside every AI-derived number, as a hairline-ringed mono chip | UI-02. The chip appears many times per screen, so it is a ring, not a filled pill — three saturated blocks per row would read as an error state. |
| 2 | Marks 17 of 18 nav items `SOON` | No `SOON` badges at all | Every route in our nav is built. The badge would have no honest use. |
| 3 | Statuses as filled colour pills | Hairline micro-caps; only `EXECUTED` gets a fill | `EXECUTED` is the one status meaning something irreversible happened. Colouring proposals like outcomes teaches the reader to stop seeing the difference — which is INV-1 eroding in the UI. |

The IPM ladder (INV-8) inherits the same discipline: the chemical rung is the only warm colour
on the ladder, so it can never render as a peer of the cultural and biological rungs above it.

## Consequences

**Easier.** There is now one vocabulary — `panel`, `kpi-tile`, `eyebrow`, `title-panel`,
`btn-primary` — and a set of primitives in `components/ui.tsx` that encode the rules. A page
that reaches past them for raw Tailwind is visible in review as drift. Removing `dark:`
halved the class strings on most elements.

**Harder.** Dark mode is now a project, not a toggle: the design reads depth from hairlines on
warm paper, and inverted that language says nothing. Restoring it would mean designing a second
system, not flipping tokens.

**Accepted.** The icon set (`components/icons.tsx`) is hand-drawn rather than pulled from
Lucide. Twelve glyphs did not justify a build dependency, but it does mean a new icon is a
small authoring task rather than an import.

**Accepted.** Adopting another product's visual language wholesale is a real choice. The
reference is a preview of a different product for the same audience, and the tokens are
generic (a forest green, a warm off-white, a gold). We did not copy its content, its
information architecture, or its vocabulary — our ubiquitous language is unchanged.

## Alternatives considered

**Keep the neutral template and only fix spacing.** Cheapest, and it leaves the product
looking like scaffolding at exactly the moment its credibility is the deliverable.

**Take the structure, invent our own palette.** Defensible, and the option we offered first.
Rejected because the reference's palette is already tuned for this audience and inventing a
second green would have cost design time we would rather spend on the decision surfaces.

**Install shadcn/ui properly and consume its components.** Rejected for MVP scope: it pulls in
`tailwind-merge`, `class-variance-authority`, Radix primitives and a `components.json`
workflow, to replace roughly 200 lines of CSS we now own outright. The token *convention* was
worth taking; the dependency tree was not.
