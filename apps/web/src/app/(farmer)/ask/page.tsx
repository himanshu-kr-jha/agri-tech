/**
 * The farmer's own assistant — INV-5, UI-05.
 *
 * Narrow on purpose. Four things it can answer, all of them about this farmer's own farm,
 * and one thing it will not: anything belonging to the collective. The refusal matters more
 * than the breadth — it is the part that shows the information boundary is real, and it is
 * only convincing because the assistant can say in the same breath what it *can* see.
 *
 * Bilingual labels rather than a language toggle, matching the rest of this tree: a farmer
 * reading on a phone outdoors should not have to find a setting first.
 */

import { Suspense } from "react";

import { ChatPanel } from "@/components/chat";
import { DemoDataBadge } from "@/components/invariants";

export const dynamic = "force-dynamic";

const EXAMPLES = [
  "How can I increase the yield of my crops?",
  "What should I do on my farm today?",
  "What schemes may apply to me?",
  "What has the FPO shared with members?",
];

export default function FarmerAssistantPage() {
  return (
    <main className="mx-auto max-w-2xl px-5 py-8">
      <header className="mb-7">
        <h1 className="font-serif text-2xl tracking-tight text-foreground">
          पूछिए · Ask
        </h1>
        <p className="mt-2 text-[15px] leading-relaxed text-muted-foreground">
          अपने खेत के बारे में पूछिए · Ask about your own farm. Answers come from what is
          recorded about your plots and crops, and every one shows where it came from.
        </p>
        <div className="mt-3">
          <DemoDataBadge />
        </div>
      </header>

      <Suspense fallback={<p className="text-sm text-muted-foreground">Loading…</p>}>
        <ChatPanel examples={EXAMPLES} placeholder="मेरी फसल कैसी है? · How is my crop?" />
      </Suspense>
    </main>
  );
}
