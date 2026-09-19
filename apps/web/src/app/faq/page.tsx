/**
 * FAQ — pre-empts the objections a judge or funder is most likely to raise, each traceable
 * to an invariant already built into the product rather than generic startup copy.
 *
 * Static content, no per-request data — safe to prerender.
 */

import type { Metadata } from "next";
import Link from "next/link";

import { FaqAccordion } from "@/components/faq-accordion";
import { Footer } from "@/components/footer";
import { IconLeaf } from "@/components/icons";
import { translator, type StringKey } from "@/lib/i18n";
import { currentLocale } from "@/lib/locale";

export const metadata: Metadata = {
  title: "FAQ",
  description: "Answers to the questions judges and funders ask most about AgriVardhak.",
};

const QUESTIONS: { q: StringKey; a: StringKey }[] = [
  { q: "faq.q1", a: "faq.a1" },
  { q: "faq.q2", a: "faq.a2" },
  { q: "faq.q3", a: "faq.a3" },
  { q: "faq.q4", a: "faq.a4" },
  { q: "faq.q5", a: "faq.a5" },
];

export default async function FaqPage() {
  const t = translator(await currentLocale());

  return (
    <div className="flex min-h-screen flex-col">
      <main className="mx-auto w-full max-w-2xl px-6 py-12 md:px-10 md:py-16">
        <Link href="/" className="mb-8 flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <IconLeaf size={16} />
        </Link>

        <p className="eyebrow">{t("faq.eyebrow")}</p>
        <h1 className="title-page mt-2 text-[2rem]">{t("faq.title")}</h1>

        <FaqAccordion
          items={QUESTIONS.map(({ q, a }) => ({ q: t(q), a: t(a) }))}
          qLabel={t("faq.qLabel")}
          aLabel={t("faq.aLabel")}
        />
      </main>

      <Footer />
    </div>
  );
}
