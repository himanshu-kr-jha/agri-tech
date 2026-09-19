/**
 * Terms of use.
 *
 * Structure adapted from a reference ToS the user supplied (acceptance, conduct, accounts,
 * assumption-of-risk, IP, changes, contact) — the substance is rewritten for what AgriVardhak
 * actually is: a decision-support platform, not a gym. The "no warranty" section is grounded
 * in INV-1 (human approval required) and INV-8 (IPM-first, cited chemical guidance only),
 * both already enforced elsewhere in the product. Static content, no per-request data — safe
 * to prerender.
 */

import type { Metadata } from "next";

import { translator } from "@/lib/i18n";
import { currentLocale } from "@/lib/locale";

export const metadata: Metadata = {
  title: "Terms of Use",
  description: "The terms governing access to and use of the AgriVardhak platform.",
};

export default async function TermsPage() {
  const t = translator(await currentLocale());

  return (
    <main className="mx-auto w-full max-w-2xl px-6 py-12 md:px-10 md:py-16">
      <p className="eyebrow">{t("terms.eyebrow")}</p>
      <h1 className="title-page mt-2 text-[2rem]">{t("terms.title")}</h1>
      <p className="mt-4 text-[15px] leading-relaxed text-muted-foreground">
        {t("terms.intro")}
      </p>

      <section className="panel mt-10">
        <h2 className="title-section text-lg">{t("terms.acceptance.title")}</h2>
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
          {t("terms.acceptance.body")}
        </p>
      </section>

      <section className="panel mt-6">
        <h2 className="title-section text-lg">{t("terms.use.title")}</h2>
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
          {t("terms.use.body")}
        </p>
      </section>

      <section className="panel mt-6">
        <h2 className="title-section text-lg">{t("terms.accounts.title")}</h2>
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
          {t("terms.accounts.body")}
        </p>
      </section>

      <section className="panel mt-6">
        <h2 className="title-section text-lg">{t("terms.warranty.title")}</h2>
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
          {t("terms.warranty.body")}
        </p>
      </section>

      <section className="panel mt-6">
        <h2 className="title-section text-lg">{t("terms.ip.title")}</h2>
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
          {t("terms.ip.body")}
        </p>
      </section>

      <section className="panel mt-6">
        <h2 className="title-section text-lg">{t("terms.changes.title")}</h2>
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
          {t("terms.changes.body")}
        </p>
      </section>

      <section className="panel mt-6">
        <h2 className="title-section text-lg">{t("terms.contact.title")}</h2>
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
          {t("terms.contact.body")}
        </p>
        <a
          href="mailto:agritechbuzz@gmail.com"
          className="mt-3 inline-block text-sm text-primary underline underline-offset-4 hover:text-primary/80"
        >
          agritechbuzz@gmail.com
        </a>
      </section>
    </main>
  );
}
