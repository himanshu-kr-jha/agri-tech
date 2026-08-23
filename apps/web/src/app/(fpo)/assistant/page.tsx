/**
 * The assistant — M15c, FR-807. The screen the whole product is arranged around.
 *
 * A CEO types a question and gets a Decision Packet: situation, impact, recommendation,
 * expected outcome, confidence, evidence, actions — with every number carrying where it came
 * from, and with the system's own disagreements shown rather than resolved behind the scenes.
 *
 * The question box offers examples not as a convenience but because the first question a
 * person asks a system like this decides what they think it is. "What should we do this
 * season to maximize sustainable farmer income?" tells them it reasons about the collective;
 * a blank box tells them it is a chatbot.
 */

import { Suspense } from "react";

import { AskForm } from "./ask-form";
import { DemoDataBadge } from "@/components/invariants";
import { PageHeader } from "@/components/ui";

export const dynamic = "force-dynamic";

const EXAMPLES = [
  "What should we do this season to maximize sustainable farmer income?",
  "Who should we sell the paddy to?",
  "What is the risk to this harvest?",
  "Which schemes can our members claim?",
];

export default function AssistantPage() {
  return (
    <main className="max-w-4xl px-6 py-10 md:px-10">
      <PageHeader
        eyebrow="Decision packet"
        title="Ask the collective"
        subtitle="Every answer arrives with its evidence frozen. Nothing it proposes happens until a human approves it."
        aside={<DemoDataBadge />}
      />

      <Suspense
        fallback={<p className="text-sm text-muted-foreground">Loading…</p>}
      >
        <AskForm examples={EXAMPLES} />
      </Suspense>
    </main>
  );
}
