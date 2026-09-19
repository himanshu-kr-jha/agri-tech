/**
 * About us, as the landing page tells it.
 *
 * Deliberately not the same copy as `/about`. That page is the full account — origin,
 * problem, mission, the approval loop. This is the three sentences someone reads while
 * deciding whether to click anything, and the three commitments that distinguish the
 * product: it is built for the collective, it shows its evidence, and a person decides.
 */

import { ABOUT_POINTS } from "@/components/landing/content";
import { translator } from "@/lib/i18n";
import type { Locale } from "@/lib/locale";

export function AboutSection({ locale }: { locale: Locale }) {
  const t = translator(locale);

  return (
    <section className="border-t border-border/70">
      <div className="mx-auto w-full max-w-7xl px-6 py-16 md:px-10 md:py-24">
        <div className="grid gap-12 md:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] md:gap-20">
          <div>
            <p className="eyebrow">{t("landing.about.eyebrow")}</p>
            <h2 className="title-page mt-3 text-[1.75rem] md:text-[2.25rem]">
              {t("landing.about.title")}
            </h2>
          </div>

          <div>
            <p className="text-[15px] leading-relaxed text-muted-foreground">
              {t("landing.about.body")}
            </p>

            <dl className="mt-10 space-y-8">
              {ABOUT_POINTS.map(({ icon: Glyph, title, body }) => (
                <div key={title} className="flex gap-5">
                  <span className="mt-0.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary/[0.07] text-primary">
                    <Glyph size={22} />
                  </span>
                  <div>
                    <dt className="title-panel">{t(title)}</dt>
                    <dd className="mt-2 text-sm leading-relaxed text-muted-foreground">
                      {t(body)}
                    </dd>
                  </div>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </div>
    </section>
  );
}
