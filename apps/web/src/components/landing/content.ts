import {
  IconAcres,
  IconApproval,
  IconBook,
  IconCollective,
  IconCycle,
  IconDatabase,
  IconDecisions,
  IconFarmers,
  IconRisk,
  IconScale,
  IconSeal,
} from "@/components/icons";
import type { StringKey } from "@/lib/i18n";

/**
 * What the landing page is made of — as data, not as five hand-written blocks.
 *
 * Every string here is a `StringKey`, never prose. That is what makes `tsc` the guard: a
 * key that does not exist in `strings.json` is a compile error, and a key that exists is
 * guaranteed to have both an English and a Hindi rendering. Writing copy inline would put
 * the Hindi reader on the runtime translation path (ADR-0023) with no compile-time warning.
 *
 * `clip` values are the basenames `scripts/build_hero_media.py` emits. Rename in both
 * places or neither.
 */

export type HeroSlide = { clip: string; eyebrow: StringKey; headline: StringKey };

/**
 * Three slides, from the three clean HD clips.
 *
 * The other two clips are 768×432 and carry burned-in comp watermarks, so they play small
 * in `FieldStrip` further down the page rather than full-bleed here, where both the
 * softness and the mark would be unmissable. See ADR-0025.
 *
 * The order is the season: the plot, the market, the settlement.
 */
export const HERO_SLIDES: readonly HeroSlide[] = [
  {
    clip: "hero-01-paddy",
    eyebrow: "landing.hero.plot.eyebrow",
    headline: "landing.hero.plot.headline",
  },
  {
    clip: "hero-02-grading",
    eyebrow: "landing.hero.market.eyebrow",
    headline: "landing.hero.market.headline",
  },
  {
    clip: "hero-03-harvest",
    eyebrow: "landing.hero.harvest.eyebrow",
    headline: "landing.hero.harvest.headline",
  },
] as const;

export type StripClip = { clip: string; caption: StringKey };

export const STRIP_CLIPS: readonly StripClip[] = [
  { clip: "strip-01-advisory", caption: "landing.strip.advisory" },
  { clip: "strip-02-officer", caption: "landing.strip.officer" },
] as const;

/** Every glyph in `icons.tsx` shares one signature; this names it once. */
export type IconComponent = typeof IconFarmers;

export type StatTile = { icon: IconComponent; label: StringKey; field: StatField };
export type StatField = "farmers_modelled" | "crop_cycles_analysed" | "acres_mapped";

/**
 * Three tiles, and the count of collectives is deliberately not among them.
 *
 * Every figure here is a true statement about what the platform has modelled — which is
 * what the verb in each label carries. A tile reading "1 FPO" would be a claim about
 * customers, and a different kind of claim entirely.
 */
export const STAT_TILES: readonly StatTile[] = [
  { icon: IconFarmers, label: "landing.stats.farmers", field: "farmers_modelled" },
  { icon: IconCycle, label: "landing.stats.cycles", field: "crop_cycles_analysed" },
  { icon: IconAcres, label: "landing.stats.acres", field: "acres_mapped" },
] as const;

export type Point = { icon: IconComponent; title: StringKey; body: StringKey };

export const ABOUT_POINTS: readonly Point[] = [
  {
    icon: IconCollective,
    title: "landing.about.point1.title",
    body: "landing.about.point1.body",
  },
  {
    icon: IconDatabase,
    title: "landing.about.point2.title",
    body: "landing.about.point2.body",
  },
  {
    icon: IconDecisions,
    title: "landing.about.point3.title",
    body: "landing.about.point3.body",
  },
] as const;

/** The five pillars — market, knowledge, entitlement, risk, and the decision itself. */
export const PILLARS: readonly Point[] = [
  { icon: IconScale, title: "landing.pillars.market.title", body: "landing.pillars.market.body" },
  {
    icon: IconBook,
    title: "landing.pillars.advisory.title",
    body: "landing.pillars.advisory.body",
  },
  { icon: IconSeal, title: "landing.pillars.schemes.title", body: "landing.pillars.schemes.body" },
  { icon: IconRisk, title: "landing.pillars.risk.title", body: "landing.pillars.risk.body" },
  {
    icon: IconApproval,
    title: "landing.pillars.human.title",
    body: "landing.pillars.human.body",
  },
] as const;
