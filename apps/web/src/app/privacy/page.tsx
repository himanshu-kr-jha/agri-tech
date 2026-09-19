/**
 * Privacy Policy — FR-1101–1106.
 *
 * Written from the consent model the product already implements (Consent entity, four
 * named purposes, revocation, anonymized-research aggregation), not invented boilerplate —
 * only the section headings follow a standard Privacy Policy numbering; the underlying facts
 * are unchanged. Static content, no per-request data — safe to prerender.
 */

import type { Metadata } from "next";
import Link from "next/link";

import { Footer } from "@/components/footer";
import { IconLeaf } from "@/components/icons";
import { translator } from "@/lib/i18n";
import { currentLocale } from "@/lib/locale";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description:
    "How AgriVardhak collects, uses, and protects farmer and organization data, and how AI is used to generate recommendations.",
};

export default async function PrivacyPage() {
  const t = translator(await currentLocale());

  return (
    <div className="flex min-h-screen flex-col">
      <main className="mx-auto w-full max-w-2xl px-6 py-12 md:px-10 md:py-16">
        <Link href="/" className="mb-8 flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <IconLeaf size={16} />
        </Link>

        <p className="eyebrow">{t("privacy.eyebrow")}</p>
        <h1 className="title-page mt-2 text-[2rem]">{t("privacy.title")}</h1>
        <p className="mt-4 text-[15px] leading-relaxed text-muted-foreground">
          {t("privacy.intro")}
        </p>

        <section className="panel mt-10">
          <h2 className="title-section text-lg">{t("privacy.consent.title")}</h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            {t("privacy.consent.body")}
          </p>
          <ul className="mt-4 space-y-3 text-sm leading-relaxed text-foreground">
            <li>{t("privacy.consent.serviceDelivery")}</li>
            <li>{t("privacy.consent.orgAnalytics")}</li>
            <li>{t("privacy.consent.modelImprovement")}</li>
            <li>{t("privacy.consent.anonymizedResearch")}</li>
          </ul>
        </section>

        <section className="panel mt-6">
          <h2 className="title-section text-lg">{t("privacy.revocation.title")}</h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            {t("privacy.revocation.body")}
          </p>
        </section>

        <section className="panel mt-6">
          <h2 className="title-section text-lg">{t("privacy.sensitive.title")}</h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            {t("privacy.sensitive.body")}
          </p>
        </section>

        <section className="panel mt-6">
          <h2 className="title-section text-lg">{t("privacy.export.title")}</h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            {t("privacy.export.body")}
          </p>
        </section>

        <section className="panel mt-6">
          <h2 className="title-section text-lg">{t("privacy.ai.title")}</h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            {t("privacy.ai.body")}
          </p>
        </section>

        <section className="panel mt-6">
          <h2 className="title-section text-lg">{t("privacy.contact.title")}</h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            {t("privacy.contact.body")}
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
