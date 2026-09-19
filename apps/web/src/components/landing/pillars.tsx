/**
 * The five pillars.
 *
 * This section is the argument that AgriVardhak is an ecosystem rather than an advisory
 * app. Advice on its own moves nothing: a farmer who knows the right answer and still
 * cannot reach a buyer, claim an entitlement or carry the risk is exactly where they
 * started. The five move together or the income does not move.
 *
 * Five cards on a three-column grid leaves two on the last row rather than a lonely one,
 * which is why the count is five and not six — the fifth is the one that cannot be cut.
 */

import { PILLARS } from "@/components/landing/content";
import { translator } from "@/lib/i18n";
import type { Locale } from "@/lib/locale";

export function Pillars({ locale }: { locale: Locale }) {
  const t = translator(locale);

  return (
    <section className="border-t border-border/70 bg-muted/35">
      <div className="mx-auto w-full max-w-7xl px-6 py-16 md:px-10 md:py-24">
        <p className="eyebrow">{t("landing.pillars.eyebrow")}</p>
        <h2 className="title-page mt-3 max-w-2xl text-[1.75rem] md:text-[2.25rem]">
          {t("landing.pillars.title")}
        </h2>
        <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-muted-foreground">
          {t("landing.pillars.intro")}
        </p>

        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {PILLARS.map(({ icon: Glyph, title, body }) => (
            <article key={title} className="panel flex flex-col gap-4 p-7">
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/[0.07] text-primary">
                <Glyph size={24} />
              </span>
              <h3 className="title-panel">{t(title)}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">{t(body)}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
