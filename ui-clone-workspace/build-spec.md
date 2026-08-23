# Build Spec — Krishi·OS DNA → AgriVardhak

Phases 3 and 4, merged: the target was an existing Next.js 16 app, not a fresh `index.html`,
so the "build prompt" is the diff itself. This file records the mapping so the next person can
tell what was extracted from where.

**Animation tier: 1.** The reference loads no animation library. Everything is CSS transitions
at `150ms cubic-bezier(0, 0, 0.2, 1)` on explicitly named properties. **Do not add GSAP,
Lenis, or Framer Motion to this app** — matching the library is a rule of the clone, and here
the matched library is "none".

## Foundation

| Reference artefact | Landed in |
|---|---|
| 24 HSL tokens + chart ramp + `--radius` | `apps/web/src/app/globals.css` `:root` |
| Tailwind v4 bridge (`@theme inline`) | same file — `--color-*`, `--font-*`, `--radius-md` |
| Fraunces / Inter Tight / JetBrains Mono | `apps/web/src/app/layout.tsx` via `next/font/google` |
| `.paper-noise` two-layer dot grid | `globals.css`, applied to `<body>` |
| `.kpi-tile`, `.kpi-label`, `.kpi-value` | `globals.css`, verbatim from the extraction |
| Nav rail (`inset 2px 0 0 0` gold) | `globals.css` `.nav-item-active` |

Classes added beyond the reference, following its grammar: `.panel`, `.eyebrow`,
`.eyebrow-sm`, `.title-page/-section/-panel`, `.chip`, `.btn-primary`, `.btn-ghost`,
`.kpi-tile-invert`.

## Components

| Reference pattern | Primitive |
|---|---|
| Eyebrow → serif H1 → subtitle → right rail | `PageHeader` in `components/ui.tsx` |
| Panel with eyebrow → serif title → baseline meta | `Panel` + `PanelHeader` |
| KPI tile with unit suffix and inverted variant | `KpiTile` |
| Hairline status chip with dot | `Chip` |
| One-sentence muted empty state | `EmptyState` |
| Outline icon set (Lucide-weight, hand-drawn) | `components/icons.tsx` |
| 260px sidebar + mobile fallback | `components/sidebar.tsx` |

## Screens

| File | Treatment |
|---|---|
| `app/(fpo)/layout.tsx` | Sidebar + sticky org header (name, district, type, avatar, sign out) |
| `app/(farmer)/layout.tsx` | No sidebar. Same palette and serif, 17px body, single column |
| `dashboard/page.tsx` | KPI strip → briefing panels → provenance footer. Briefing "waiting on you" carries the gold rail |
| `decisions/`, `decisions/[id]` | Hairline list; detail is packet → INV-1 approval → INV-2 frozen evidence |
| `farmers/`, `farmers/[id]` | Hairline table, serif figures with muted unit suffix; provenance inline |
| `market/page.tsx` | Offer table — serif price, mono for distance/terms/rejection |
| `risk/page.tsx` | Exposure figures as serif+unit pairs; likelihood/impact as hairline micro-caps |
| `impact/page.tsx` | KPI row + attribution strength + adherence |
| `login/` | Centred, brand mark, serif title, demo-account cards with gold rail on the selected one |
| `components/packet.tsx` | Serif section titles; override banner on gold rail; IPM ladder colour discipline |
| `components/approval.tsx` | Status micro-caps; only `EXECUTED` filled |
| `components/invariants.tsx` | Confidence/stale/conflict/demo badges retoned to hairline rings |

## Verification

`tsc --noEmit`, `eslint`, `vitest` (8/8), and `next build` all pass. `/login` was rendered and
screenshotted. The authenticated console could not be rendered: Docker is not running, so
Postgres is down and the API returns 500 — unrelated to this change.
