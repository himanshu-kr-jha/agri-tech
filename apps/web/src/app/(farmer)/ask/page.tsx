/**
 * The farmer's own assistant — INV-5, UI-05.
 *
 * Narrow on purpose. Four things it can answer, all of them about this farmer's own farm,
 * and one thing it will not: anything belonging to the collective. The refusal matters more
 * than the breadth — it is the part that shows the information boundary is real, and it is
 * only convincing because the assistant can say in the same breath what it *can* see.
 *
 * One language at a time, chosen with the switch in the header and remembered for a year.
 * This tree used to set Hindi and English on the same line; two languages competing for the
 * same glance is harder to read than either alone, whichever one you have.
 */

import { Suspense } from "react";

import { ChatPanel } from "@/components/chat";
import { translator } from "@/lib/i18n";
import { currentLocale } from "@/lib/locale";

export const dynamic = "force-dynamic";

export default async function FarmerAssistantPage() {
  const t = translator(await currentLocale());
  const examples = [
    t("ask.example.yield"),
    t("ask.example.today"),
    t("ask.example.schemes"),
    t("ask.example.shared"),
  ];

  return (
    <main className="mx-auto max-w-2xl px-5 py-8">
      <header className="mb-7">
        <h1 className="font-serif text-2xl tracking-tight text-foreground">{t("ask.title")}</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-muted-foreground">
          {t("ask.intro")}
        </p>
        <div className="mt-3">
        </div>
      </header>

      <Suspense fallback={<p className="text-sm text-muted-foreground">{t("ask.loading")}</p>}>
        <ChatPanel examples={examples} placeholder={t("ask.placeholder")} />
      </Suspense>
    </main>
  );
}
