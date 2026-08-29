/**
 * The assistant — M15c, FR-807. The screen the whole product is arranged around.
 *
 * A CEO asks a question and gets an answer shaped to the question. One that proposes
 * committing a season returns a Decision Packet, with evidence frozen and a human approval
 * gate in front of it. One that asks what is true returns cited claims and writes nothing.
 * The distinction is the point: freezing an evidence snapshot for "which farmers need
 * attention" would devalue the snapshot for the decisions that need one.
 *
 * The examples are not a convenience. The first question someone asks a system like this
 * decides what they think it is, and these four are chosen to show the range of shapes — a
 * decision, a lookup, a scan of the register, a priority list — rather than four variations
 * on the same answer.
 */

import { Suspense } from "react";

import { ChatPanel } from "@/components/chat";
import { DemoDataBadge } from "@/components/invariants";
import { PageHeader } from "@/components/ui";

export const dynamic = "force-dynamic";

const EXAMPLES = [
  "What should we do this season to maximize sustainable farmer income?",
  "Which farmers require attention?",
  "What are the biggest risks facing our FPO this month?",
  "What should I prioritize today?",
];

export default function AssistantPage() {
  return (
    <main className="max-w-4xl px-6 py-10 md:px-10">
      <PageHeader
        eyebrow="Assistant"
        title="Ask the collective"
        subtitle="Every answer arrives with its evidence. Anything it proposes waits for a human before it happens."
        aside={<DemoDataBadge />}
      />

      <Suspense fallback={<p className="text-sm text-muted-foreground">Loading…</p>}>
        <ChatPanel
          examples={EXAMPLES}
          placeholder="What should we do this season?"
        />
      </Suspense>
    </main>
  );
}
