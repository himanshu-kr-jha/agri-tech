/**
 * Decision history — M15e, FR-710, SAF-10.
 *
 * Every question ever asked, with what it recommended and what a human did about it. This
 * list exists so a farmer can contest a decision that affected them — not only so the FPO
 * can defend itself. That framing decides what belongs here: the questions and their
 * outcomes, never a ranking of who the system was "right" about.
 */

import Link from "next/link";

import { ApiError, api } from "@/lib/api";
import { ConfidenceChip } from "@/components/invariants";

export const dynamic = "force-dynamic";

export default async function DecisionsPage() {
  let data;
  try {
    data = await api.decisions();
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 0;
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <h1 className="text-2xl font-semibold">Decisions</h1>
        <p className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200">
          {status === 403
            ? "The decision history is organization-internal."
            : "Could not reach the API. Run `make api`."}
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Decisions</h1>
        <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
          Every question asked, its answer, and the evidence frozen at the moment it was
          given. Open one to approve, reject, or see why it said what it said.
        </p>
      </header>

      {data.decisions.length === 0 ? (
        <p className="rounded-lg border border-neutral-200 p-6 text-sm text-neutral-500 dark:border-neutral-800">
          Nothing asked yet.{" "}
          <Link href="/assistant" className="underline underline-offset-2">
            Ask the first question
          </Link>
          .
        </p>
      ) : (
        <ul className="divide-y divide-neutral-100 rounded-xl border border-neutral-200 dark:divide-neutral-900 dark:border-neutral-800">
          {data.decisions.map((decision) => (
            <li key={decision.id}>
              <Link
                href={`/decisions/${decision.id}`}
                className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-3 hover:bg-neutral-50 dark:hover:bg-neutral-900"
              >
                <span className="min-w-0 flex-1 text-sm font-medium">{decision.question}</span>
                <ConfidenceChip value={decision.overall_confidence} />
                <span className="text-xs text-neutral-500">
                  {decision.recommendations} recommendation
                  {decision.recommendations === 1 ? "" : "s"}
                </span>
                <span className="text-xs text-neutral-400">
                  {new Date(decision.generated_at).toLocaleString("en-IN", {
                    timeZone: "Asia/Kolkata",
                    day: "numeric",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
