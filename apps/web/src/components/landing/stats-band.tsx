/**
 * The three-tile band — UI-12.
 *
 * Read the labels carefully before changing them. Each is a verb: farmers *modelled*,
 * crop cycles *analysed*, acres *mapped*. Those are true statements about what the
 * platform holds. "1,000 Farmers" on its own would be a claim about customers, which is a
 * different claim and not one we can make. The footnote names the dataset. Between them
 * they do the work `UI-04`'s DEMO DATA badge does elsewhere in the product — see ADR-0026
 * for why the badge itself is the wrong instrument on a public page.
 *
 * Server component: it renders numbers it is handed, and fetches nothing. The fetch, its
 * cache window and its fallback all live in `lib/public-stats.ts`, so this file can be
 * rendered from a test with any figures at all.
 */

import { STAT_TILES } from "@/components/landing/content";
import type { PlatformStats } from "@/lib/api";
import { translator } from "@/lib/i18n";
import type { Locale } from "@/lib/locale";

export function StatsBand({ stats, locale }: { stats: PlatformStats; locale: Locale }) {
  const t = translator(locale);

  return (
    <section className="mx-auto w-full max-w-7xl px-6 py-16 md:px-10 md:py-24">
      <p className="eyebrow">{t("landing.stats.eyebrow")}</p>

      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        {STAT_TILES.map(({ icon: Glyph, label, field }) => (
          <div key={field} className="kpi-tile flex flex-col items-start gap-5 p-7">
            {/* The reference's large circular icon, in forest at 8% rather than a tinted
                blue — and a tint, not a fill, so the tile keeps its hairline weight. */}
            <span className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/[0.07] text-primary">
              <Glyph size={28} />
            </span>
            <div>
              {/*
               * `translate="no"`: the runtime DOM translator skips pure-number nodes, but
               * "1,000" carries a comma and is not pure. Belt and braces — the alternative
               * failure is a Hindi visitor seeing a machine-mangled figure.
               *
               * Fraunces, per the design law that every number in this product is serif.
               * `.font-mono` would also be skipped by the translator, which is exactly the
               * kind of reason that quietly turns a type system into a lookup table.
               */}
              <p translate="no" className="kpi-value mt-0 text-[2.75rem] leading-none">
                {stats[field].toLocaleString("en-IN")}
              </p>
              <p className="kpi-label mt-3">{t(label)}</p>
            </div>
          </div>
        ))}
      </div>

      <p className="mt-5 text-xs text-muted-foreground">{t("landing.stats.footnote")}</p>
    </section>
  );
}
