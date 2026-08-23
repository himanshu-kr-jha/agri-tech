# Brand Interview — AgriVardhak

**Date**: 2026-08-23
**Reference**: Krishi·OS FPO Command Center (see `site-dna.md`)

| # | Question | Answer |
|---|---|---|
| 1 | Palette & font fidelity | **Exact clone.** Take the reference tokens verbatim — `#F9F9F6` paper, `#1A3826` forest primary, `#132A1D` sidebar, `#C7A03D` gold accent, `#DDE3DF` hairline. Fonts: Fraunces (titles + all numbers), Inter Tight (all UI), JetBrains Mono (codes/IDs). |
| 2 | Dark mode | **Drop it.** Ship light-only, matching the reference. Every `dark:` variant in the repo is removed rather than left inconsistent. |
| 3 | Shell | **Sidebar for FPO, farmer stays simple.** FPO console gets the 260px dark sidebar + sticky org header. Farmer portal keeps its single-column, 17px, phone-first layout — restyled with the same tokens, no sidebar. |
| 4 | Scope | **Everything.** Tokens, fonts, shell, all 8 FPO screens, farmer `today`, login, and the `packet` / `approval` / `invariants` / `sign-out` components. |

## Constraints carried from CLAUDE.md that override the reference

- **Confidence chips stay.** Every AI-derived number keeps its confidence chip (TS convention).
  The reference has no equivalent, so this is an addition to the DNA, styled in its language.
- **`SYNTHETIC — DEMO ONLY` labelling stays visible.** The `DemoDataBadge` must remain
  legible, not decorative — rule 5 in the project instructions.
- **Units are never dropped.** The reference's "486 acres" pattern (serif number + smaller
  muted unit) is a good fit and becomes the house pattern for every value.
- **Ubiquitous language.** Nav and headings use `Decisions`, `Farmers`, `Risk`, `Market`,
  `Impact` — no renaming to match the reference's vocabulary.
- **No `SOON` badges.** The reference uses them because 17 of 18 routes are unbuilt. Every
  AgriVardhak route listed in the nav is real, so the badge has no honest use here.
