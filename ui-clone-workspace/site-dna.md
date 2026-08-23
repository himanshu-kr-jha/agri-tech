# Site DNA: Krishi·OS — FPO Command Center

**Source URL**: https://cultivate-core.preview.emergentagent.com/ (redirects to `/dashboard`)
**Crawled**: 2026-08-23
**Login**: none required — the preview auto-authenticates as "Ramesh Prajapati · FPO Admin"
**Animation Tier**: **1 — Simple** (CSS transitions + one `fade-up` keyframe; no GSAP, ScrollTrigger, Lenis, Lottie, or Three.js detected)

---

## 1. Identity & Vibe

Quiet institutional software dressed as fine print. A cream paper ground with a faint dot
grid, hairline-bordered white cards with **no shadows**, and a deep forest-green sidebar
that reads as a spine rather than a chrome panel. The voice comes from the type pairing:
**Fraunces** (a warm, slightly quirky serif) for every number and title, **Inter Tight**
for all UI text, with wide-tracked micro-caps as labels. It feels like a ledger or an
annual report, not a SaaS dashboard — restrained, dense, and confident. Gold appears
exactly once per screen as an accent (the active-nav rail), never as decoration.

---

## 2. Design System Tokens

Authored in the **shadcn/ui HSL-triplet convention** (`--token: H S% L%`, consumed as
`hsl(var(--token) / alpha)`).

### Colors

| Token | HSL | Hex | Role |
|---|---|---|---|
| `--background` | `60 20% 97%` | `#F9F9F6` | Page ground (warm off-white paper) |
| `--foreground` | `150 12% 12%` | `#1B221F` | Body text |
| `--card` | `0 0% 100%` | `#FFFFFF` | Card / panel surface |
| `--card-foreground` | `150 12% 12%` | `#1B221F` | Text on cards |
| `--popover` / `--popover-foreground` | `0 0% 100%` / `150 12% 12%` | | Overlays |
| `--primary` | `145 37% 16%` | `#1A3826` | Forest green — all serif titles, KPI numbers, chart bar 1 |
| `--primary-foreground` | `0 0% 100%` | `#FFFFFF` | Text on green |
| `--secondary` | `132 8% 57%` | `#899A8C` | Eyebrow / micro-cap labels |
| `--secondary-foreground` | `145 37% 16%` | `#1A3826` | |
| `--muted` | `132 10% 93%` | `#EBEFEC` | Subtle fills |
| `--muted-foreground` | `145 8% 45%` | `#6A7C71` | Secondary body copy, KPI labels |
| `--accent` | `43 55% 51%` | `#C7A03D` | Gold — active-nav rail, chart bar 3. Used sparingly. |
| `--accent-foreground` | `150 12% 12%` | `#1B221F` | |
| `--destructive` | `0 66% 42%` | `#B32525` | Errors |
| `--destructive-foreground` | `0 0% 100%` | | |
| `--border` | `140 10% 88%` | `#DDE3DF` | Hairlines — almost always at `/0.7` or `/0.6` alpha |
| `--input` | `140 10% 88%` | `#DDE3DF` | |
| `--ring` | `145 37% 16%` | `#1A3826` | Focus ring |
| `--sidebar` | `145 37% 12%` | `#132A1D` | Sidebar ground (darker than primary) |
| `--sidebar-foreground` | `60 20% 97%` | `#F9F9F6` | Sidebar text |

### Chart palette
| Token | HSL | Hex |
|---|---|---|
| `--chart-1` | `145 37% 16%` | `#1A3826` |
| `--chart-2` | `132 20% 45%` | `#5C8A69` |
| `--chart-3` | `43 55% 51%` | `#C7A03D` |
| `--chart-4` | `25 35% 45%` | `#9B6B4A` |
| `--chart-5` | `200 30% 40%` | `#478299` |

### Dark mode
**None.** No `.dark` rule set exists — the site is light-only.

### Typography

| Family | Usage | Observed weights |
|---|---|---|
| **Fraunces** (`font-optical-sizing: auto`) | Page titles, panel titles, KPI values, org name — every "important" string | 400, 500 |
| **Inter Tight** | All UI: nav, body, labels, buttons, inputs, table text | 400, 500, 600 |
| **JetBrains Mono** | Numeric/code fragments (sparse — 4 nodes on the dashboard) | 400 |

Type scale as measured:

| Element | Family | Size / line-height | Weight | Letter-spacing | Transform | Color |
|---|---|---|---|---|---|---|
| Page H1 | Fraunces | 48px / 1.05 (`text-4xl md:text-5xl`) | 400 | −1.2px (`tracking-tight`) | none | `primary` |
| Page eyebrow | Inter Tight | 11px / 16.5px | 600 | 2.42px (`0.22em`) | uppercase | `secondary` |
| Page subtitle | Inter Tight | 15px / 24.4px (`leading-relaxed`) | 400 | normal | none | `muted-foreground` |
| Panel title | Fraunces | 18px (`text-lg`) | 400 | tight | none | `primary` |
| Panel eyebrow | Inter Tight | 10–11px | 500/600 | `0.18em`–`0.22em` | uppercase | `secondary` / `muted-foreground` |
| KPI label (`.kpi-label`) | Inter Tight | 10px | 500 | `0.18em` | uppercase | `muted-foreground` |
| KPI value (`.kpi-value`) | Fraunces | 30px / 36px | 500 | −0.75px | none | `primary` |
| Org name (header) | Fraunces | 17px | 400 | −0.425px | none | `primary` |
| Reg number | Inter Tight | 11px | 400 | 2.2px (`0.2em`) | uppercase | `muted-foreground` |
| Nav item | Inter Tight | 13.5px | 400/500 | normal | none | `sidebar-foreground` |
| "SOON" badge | Inter Tight | 9px | 500 | 1.35px (`0.15em`) | uppercase | `white/40` |
| Search input | Inter Tight | 14px | 400 | normal | none | `foreground` |

**The rule**: serif for identity and quantity, sans for everything functional, micro-caps
with heavy tracking as the only "label" device.

### Spacing & geometry
- `--radius: 0.5rem`; cards actually render at **6px** (`calc(var(--radius) - 2px)`).
- Main content padding: **40px**. Panel padding: **24px**. KPI tile padding: **20px** (`1.25rem`).
- Sidebar width: **260px**. Header height: **65px**.
- Content grid: 12-col; KPI row is a 6-across strip; below it a `1fr / 2fr` split
  (Crop Distribution ~497px vs Farmers by Village ~795px), then `2fr / 1fr` (Timeline vs Pending).

### Visual effects
- **No box-shadows anywhere** except one inset rail. Depth is expressed purely by hairlines.
- Borders are `1px solid hsl(var(--border) / 0.7)` — never full-opacity.
- Header is translucent: `background: rgba(249,249,246,0.85)` with a `border-bottom` hairline (backdrop blur).

---

## 3. Animation System

### Libraries detected
None. No animation library is loaded — this is plain CSS transitions plus Tailwind's
`animate-*` utilities. **Build with CSS transitions + IntersectionObserver only. Do not
introduce GSAP.**

### Global defaults
- Transition duration: **150ms**
- Easing: **`cubic-bezier(0, 0, 0.2, 1)`** (`ease-out`)
- Transitioned properties are named explicitly (`transform, border-color`), never `all`.

### Extracted CSS

```css
/* Paper ground — two offset dot grids */
.paper-noise {
  background-color: hsl(var(--background));
  background-image:
    radial-gradient(hsl(var(--muted-foreground) / 0.06) 1px, transparent 1px),
    radial-gradient(hsl(var(--muted-foreground) / 0.04) 1px, transparent 1px);
  background-size: 20px 20px, 10px 10px;
  background-position: 0 0, 5px 5px;
}

/* KPI tile */
.kpi-tile {
  position: relative;
  border-radius: calc(var(--radius) - 2px);
  border: 1px solid hsl(var(--border) / 0.7);
  background-color: hsl(var(--card));
  padding: 1.25rem;
  transition-property: transform, border-color;
  transition-duration: 150ms;
  transition-timing-function: cubic-bezier(0, 0, 0.2, 1);
}
.kpi-tile:hover {
  transform: translateY(-1px);
  border-color: hsl(var(--primary) / 0.3);
}

.kpi-label {
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  color: hsl(var(--muted-foreground));
}

.kpi-value {
  margin-top: 0.5rem;
  font-family: Fraunces, ui-serif, Georgia, serif;
  font-optical-sizing: auto;
  font-size: 1.875rem;
  line-height: 2.25rem;
  font-weight: 500;
  letter-spacing: -0.025em;
  color: hsl(var(--primary));
}
```

Keyframes present: `fade-up` (the only bespoke one), plus library boilerplate
(`enter`, `exit`, `accordion-up/down`, `pulse`, and Sonner toast keyframes).

### Interaction states
| Element | Rest | Hover / Active |
|---|---|---|
| KPI tile | white, `border/0.7` | `translateY(-1px)`, `border: primary/0.3`, 150ms ease-out |
| Nav item (active) | `bg: rgba(249,249,246,0.09)`, radius 6px | `box-shadow: inset 2px 0 0 0 #C7A03D` (gold rail) |
| Nav item (idle) | transparent, muted sidebar text | subtle white wash |
| Inverted KPI tile | `bg: primary`, white label + value | used for the one "alert" tile (Pending Actions) |

### Scroll motion map
Effectively empty — the page is static on scroll. No parallax, no pinning, no scrubbing,
no scroll-triggered entrances observed between scroll positions 0 and 700.

---

## 4. Page Structure — Dashboard

### Shell
```
body.paper-noise
├── aside            260px, bg #132A1D, full height, no border
│   ├── brand block  gold-tinted rounded square mark + "Krishi·OS" / "FPO INFRASTRUCTURE" (9px caps)
│   ├── nav group    "Dashboard" (active, gold rail)
│   ├── nav group    "FPO"        — Overview, Farmers, Farms, Crops, Operations
│   ├── nav group    "ECOSYSTEM"  — Knowledge & Research, Services Marketplace, Financial
│   │                  Facilitation, Women & Youth, Policy & Intelligence, Marketplace,
│   │                  Traceability, Export & Compliance
│   └── nav group    "SYSTEM"     — Analytics, Documents, Notifications, Settings
│       Group headings: 10px uppercase, 0.18em tracking, white/40
│       Unbuilt items carry a right-aligned "SOON" badge (9px caps, white/40)
└── main
    ├── header       65px sticky, bg/85 + blur, hairline bottom
    │   ├── left     org name (Fraunces 17px) + district + season · then REG number caps
    │   ├── center   search field, pill, hairline border, ⌘K chip
    │   └── right    bell icon · avatar circle (initials) + name/role stack
    └── content      padding 40px
```

### Section 1: Page header
- Eyebrow `FPO COMMAND CENTER` → H1 `Digital infrastructure / for your FPO` (2 lines, Fraunces 48px)
- Subtitle capped at `max-w-xl`
- Right-aligned status chip: green dot + `Season active · Kharif 2026`, hairline border, 12px

### Section 2: KPI strip
Six `.kpi-tile`s in a row: Total Members 312 · Active Farmers 287 · Villages Covered 8 ·
Cultivated Area 486 acres · Active Crops 4 · Pending Actions 0.
Each: micro-cap label + small outline icon top-right, serif value, 12px muted caption below.
The last tile is **inverted** (green fill, white type) to mark it as the attention slot.
Units render as a smaller muted suffix beside the number (`486` + `acres`).

### Section 3: Two charts
- **Crop Distribution** — eyebrow `PORTFOLIO`, serif title, `By acres` right-aligned meta.
  Donut/legend with square dots, values right-aligned in a two-column legend.
- **Farmers by Village** — eyebrow `MEMBERSHIP`, `8 villages` meta. Vertical bar chart,
  dashed horizontal gridlines, dark green bars, village names as 11px axis labels.

### Section 4: Timeline + Pending
- **Recent FPO Activity** (2fr) — eyebrow `TIMELINE`. Each row: small outline icon in a
  gutter, uppercase mono-ish date (11px, tracked), bold-ish title, muted one-line description.
- **Pending Actions** (1fr) — eyebrow `REQUIRES ATTENTION`, `All ↗` link top-right,
  empty state reads *"Nothing pending — well done."*

### Empty/meta patterns worth copying
- Every panel header is: `EYEBROW` (micro-caps) → **Serif title** → optional right-aligned
  12px muted meta on the same baseline as the title.
- Empty states are a single muted sentence, no illustration, no button.

---

## 5. Technical Notes
- Stack signature: React SPA + Tailwind + shadcn/ui + Sonner toasts. Recharts-style charts.
- Fonts served from Google Fonts: Fraunces, Inter Tight, JetBrains Mono.
- Light-only; no theme toggle.
- Navigation is mostly non-functional — 17 of 18 nav items are `SOON` placeholders. Only
  `/dashboard` is implemented, so this DNA is drawn from a single route.
