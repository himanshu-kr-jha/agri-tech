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
import { EmptyState, ErrorPanel, PageHeader, Panel } from "@/components/ui";
import { translator } from "@/lib/i18n";
import { currentLocale } from "@/lib/locale";

export const dynamic = "force-dynamic";

export default async function DecisionsPage() {
  const t = translator(await currentLocale());
  let data;
  try {
    data = await api.decisions();
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 0;
    return (
      <main className="px-6 py-10 md:px-10">
        <PageHeader eyebrow={t("con.decisions.eyebrow")} title={t("con.decisions.title")} />
        <ErrorPanel title={status === 403 ? "Organization-internal" : "API unreachable"}>
          {status === 403
            ? "The decision history is organization-internal."
            : "Could not reach the API. Run `make api`."}
        </ErrorPanel>
      </main>
    );
  }

  return (
    <main className="max-w-5xl px-6 py-10 md:px-10">
      <PageHeader
        eyebrow={t("con.decisions.eyebrow")}
        title={t("con.decisions.h1")}
        subtitle={t("con.decisions.sub")}
      />

      {data.decisions.length === 0 ? (
        <Panel>
          <EmptyState>
            Nothing asked yet.{" "}
            <Link href="/assistant" className="text-primary underline underline-offset-4">
              Ask the first question
            </Link>
            .
          </EmptyState>
        </Panel>
      ) : (
        <Panel className="p-0">
          <ul>
            {data.decisions.map((decision) => (
              <li key={decision.id} className="border-b border-border/60 last:border-0">
                <Link
                  href={`/decisions/${decision.id}`}
                  className="flex flex-wrap items-baseline gap-x-4 gap-y-1.5 px-6 py-4 transition-colors hover:bg-muted/40"
                >
                  <span className="min-w-0 flex-1 text-sm font-medium text-foreground">
                    {decision.question}
                  </span>
                  <ConfidenceChip value={decision.overall_confidence} />
                  <span className="text-xs text-muted-foreground">
                    {decision.recommendations} recommendation
                    {decision.recommendations === 1 ? "" : "s"}
                  </span>
                  <span className="font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground/70">
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
        </Panel>
      )}
    </main>
  );
}
