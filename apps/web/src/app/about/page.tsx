/**
 * About us.
 *
 * Drawn entirely from the project's own decision log (`context.md` §§1-3) — the hackathon
 * brief, why a farmer-facing app was rejected, the FPO-centric pivot, the product thesis,
 * and the approve-before-execute loop (INV-1). No invented company or team facts.
 * Static content, no per-request data — safe to prerender.
 */

import type { Metadata } from "next";
import Link from "next/link";

import { Footer } from "@/components/footer";
import { IconLeaf } from "@/components/icons";
import { translator } from "@/lib/i18n";
import { currentLocale } from "@/lib/locale";

export const metadata: Metadata = {
  title: "About us",
  description: "Why AgriVardhak exists, the problem it attacks, and how a decision moves through it.",
};

export default async function AboutPage() {
  const t = translator(await currentLocale());

  return (
    <div className="flex min-h-screen flex-col">
      <main className="mx-auto w-full max-w-2xl px-6 py-12 md:px-10 md:py-16">
        <Link href="/" className="mb-8 flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <IconLeaf size={16} />
        </Link>

        <p className="eyebrow">{t("about.eyebrow")}</p>
        <h1 className="title-page mt-2 text-[2rem]">{t("about.title")}</h1>
        <p className="mt-4 text-[15px] leading-relaxed text-muted-foreground">
          {t("about.intro")}
        </p>

        <section className="panel mt-10">
          <h2 className="title-section text-lg">{t("about.origin.title")}</h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            {t("about.origin.body")}
          </p>
        </section>

        <section className="panel mt-6">
          <h2 className="title-section text-lg">{t("about.problem.title")}</h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            {t("about.problem.body")}
          </p>
        </section>

        <section className="panel mt-6">
          <h2 className="title-section text-lg">{t("about.mission.title")}</h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            {t("about.mission.body")}
          </p>
        </section>

        <section className="panel mt-6">
          <h2 className="title-section text-lg">{t("about.loop.title")}</h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            {t("about.loop.body")}
          </p>
        </section>

        <section className="panel mt-6">
          <h2 className="title-section text-lg">{t("about.contact.title")}</h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            {t("about.contact.body")}
          </p>
          <a
            href="mailto:agritechbuzz@gmail.com"
            className="mt-3 inline-block text-sm text-primary underline underline-offset-4 hover:text-primary/80"
          >
            agritechbuzz@gmail.com
          </a>
        </section>
      </main>

      <Footer />
    </div>
  );
}
