/**
 * The farmer's own assistant — INV-5, UI-05.
 *
 * Narrow on purpose. Four things it can answer, all of them about this farmer's own farm,
 * and one thing it will not: anything belonging to the collective. The refusal matters more
 * than the breadth — it is the part that shows the information boundary is real, and it is
 * only convincing because the assistant can say in the same breath what it *can* see.
 *
 * **This page stays in English while the rest of the tree follows the switch**, and that is
 * a deliberate exception rather than an oversight. Every answer the assistant produces is
 * assembled from deterministic module output that is written in English — the claims, the
 * units, the refusals. Putting a Hindi shell around English answers does not make the page
 * Hindi; it makes it half-translated, which reads worse than either language alone and
 * promises a Hindi experience the reply cannot keep.
 *
 * The one line that does follow the switch is the note saying so. A reader who has chosen
 * Hindi is owed that explanation in Hindi — and it also tells them the thing worth knowing,
 * which is that they may still *ask* in Hindi.
 *
 * When the assistant can answer in Hindi, delete the exception, not the note.
 */

import { Suspense } from "react";

import { ChatPanel } from "@/components/chat";
import { translator } from "@/lib/i18n";
import { currentLocale } from "@/lib/locale";

export const dynamic = "force-dynamic";

export default async function FarmerAssistantPage() {
  // The reader's language, used for exactly one line: the note explaining why this page is
  // not in it.
  const reader = translator(await currentLocale());
  // Everything else is English, to match the answers.
  const t = translator("en");
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
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
          {reader("ask.englishOnly")}
        </p>
      </header>

      <Suspense fallback={<p className="text-sm text-muted-foreground">{t("ask.loading")}</p>}>
        <ChatPanel examples={examples} placeholder={t("ask.placeholder")} />
      </Suspense>
    </main>
  );
}
