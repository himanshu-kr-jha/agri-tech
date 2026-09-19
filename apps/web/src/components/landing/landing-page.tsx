/**
 * The public landing page — shown to anyone who is not signed in at `/`.
 *
 * This is the one page in the product built for a reader who isn't yet a user: a judge or
 * funder opening the link cold, or the CEO of a collective deciding whether this is
 * serious. It leads with where the product is going rather than what shipped last week,
 * because the thing being described is an ecosystem — market linkage, advisory,
 * entitlements, risk, and a human-approved decision — and no single screenshot shows that.
 *
 * Composition only. Every section is its own file, and the only thing this one does is
 * fetch the totals once and resolve the copy once, so a section never fetches for itself
 * and the page makes exactly one call.
 *
 * Section order is an argument: what we do (hero), what exists today (stats), who we are
 * (about), what the ecosystem covers (pillars), what it looks like on the ground (strip),
 * and one way in (CTA). The footer comes from the `(public)` layout.
 */

import { AboutSection } from "@/components/landing/about-section";
import { CtaBand } from "@/components/landing/cta-band";
import { HERO_SLIDES, STRIP_CLIPS } from "@/components/landing/content";
import { FieldStrip } from "@/components/landing/field-strip";
import { HeroCarousel } from "@/components/landing/hero-carousel";
import { Pillars } from "@/components/landing/pillars";
import { StatsBand } from "@/components/landing/stats-band";
import { translator } from "@/lib/i18n";
import { currentLocale } from "@/lib/locale";
import { platformStats } from "@/lib/public-stats";

export async function LandingPage() {
  const locale = await currentLocale();
  const t = translator(locale);
  const stats = await platformStats();

  return (
    <main className="flex flex-col">
      {/* The two client components are handed strings, not the translator: `t` is a
          function, and functions do not serialize across the server/client boundary. */}
      <HeroCarousel
        slides={HERO_SLIDES.map((slide) => ({
          clip: slide.clip,
          eyebrow: t(slide.eyebrow),
          headline: t(slide.headline),
        }))}
        labels={{
          carousel: t("landing.hero.carouselLabel"),
          pause: t("landing.hero.pause"),
          play: t("landing.hero.play"),
          goToSlide: t("landing.hero.goToSlide"),
        }}
      />

      <StatsBand stats={stats} locale={locale} />

      <AboutSection locale={locale} />

      <Pillars locale={locale} />

      <FieldStrip
        eyebrow={t("landing.strip.eyebrow")}
        items={STRIP_CLIPS.map((item) => ({ clip: item.clip, caption: t(item.caption) }))}
      />

      <CtaBand locale={locale} />
    </main>
  );
}
