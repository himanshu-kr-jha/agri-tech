/**
 * The closing call to action.
 *
 * One destination, `/login`, where the demo-account picker does the real work of showing
 * the product. The page deliberately offers no second action here: a landing page that
 * ends in three equally-weighted buttons ends in none.
 *
 * Forest ground rather than paper, so it reads as the end of the page and seats against
 * the footer's matching green.
 */

import Link from "next/link";

import { IconArrowUpRight } from "@/components/icons";
import { translator } from "@/lib/i18n";
import type { Locale } from "@/lib/locale";

export function CtaBand({ locale }: { locale: Locale }) {
  const t = translator(locale);

  return (
    <section className="relative left-1/2 w-screen -translate-x-1/2 bg-sidebar text-sidebar-foreground">
      <div className="mx-auto w-full max-w-7xl px-6 py-20 md:px-10 md:py-28">
        <p className="eyebrow text-sidebar-foreground/60">{t("landing.cta.eyebrow")}</p>
        <h2 className="title-page mt-3 max-w-2xl text-[1.75rem] text-sidebar-foreground md:text-[2.5rem]">
          {t("landing.cta.title")}
        </h2>
        <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-sidebar-foreground/70">
          {t("landing.cta.body")}
        </p>

        <Link
          href="/login"
          className="mt-9 inline-flex items-center gap-2 rounded-md bg-background px-6 py-3 text-sm font-medium text-primary transition-[background-color] duration-150 hover:bg-background/90"
        >
          {t("landing.cta.button")}
          <IconArrowUpRight size={16} />
        </Link>
      </div>
    </section>
  );
}
