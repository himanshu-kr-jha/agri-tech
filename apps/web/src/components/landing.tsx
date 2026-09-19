/**
 * The public landing page — shown to anyone who is not signed in at `/`.
 *
 * This is the one page in the product built for a reader who isn't yet a user: a judge
 * or funder opening the link cold. It states the thesis plainly (no "AI-powered", no
 * "smart" — see docs/GLOSSARY.md) and sends them to `/login`, where the demo-account
 * picker does the actual work of showing the product.
 */

import Link from "next/link";

import { Footer } from "@/components/footer";
import { IconLeaf } from "@/components/icons";
import { LanguageToggle } from "@/components/language-toggle";
import { translator } from "@/lib/i18n";
import { currentLocale } from "@/lib/locale";

export async function LandingPage() {
  const t = translator(await currentLocale());

  return (
    <div className="flex min-h-screen flex-col pb-24 md:pb-0">
      <main className="mx-auto flex w-full max-w-4xl flex-col px-6 py-12 md:px-10 md:py-20">
        <div className="mb-10 flex items-center justify-between">
          <span className="flex h-11 w-11 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <IconLeaf size={20} />
          </span>
          <LanguageToggle />
        </div>

        <section>
          <p className="eyebrow">{t("landing.eyebrow")}</p>
          <h1 className="title-page mt-3 max-w-2xl text-[2.5rem] md:text-[3rem]">
            {t("landing.hero.title")}
          </h1>
          <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-muted-foreground">
            {t("landing.hero.subtitle")}
          </p>

          <div className="mt-8 hidden items-center gap-3 md:flex">
            <Link href="/login" className="btn-primary px-5 py-2.5">
              {t("landing.hero.ctaPrimary")}
            </Link>
            <Link href="/faq" className="btn-ghost px-5 py-2.5">
              {t("landing.hero.ctaSecondary")}
            </Link>
          </div>
        </section>

        <section className="panel mt-14 max-w-2xl">
          <p className="title-panel">{t("landing.thesis")}</p>
        </section>
      </main>

      <Footer />

      {/* Sticky mobile CTA — most traffic to a link like this is a phone, and the primary
          action should never require scrolling back up to find it. The outer `pb-24` clears
          it on mobile so it never covers the footer's last row; desktop has no fixed bar,
          hence `md:pb-0`. */}
      <div className="fixed inset-x-0 bottom-0 border-t border-border/70 bg-card/95 p-4 backdrop-blur md:hidden">
        <Link
          href="/login"
          aria-label={t("landing.mobileCta.label")}
          className="btn-primary w-full py-3"
        >
          {t("landing.hero.ctaPrimary")}
        </Link>
      </div>
    </div>
  );
}
