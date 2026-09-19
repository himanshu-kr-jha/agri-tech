/**
 * One decision, with its frozen evidence and its approval gate — M15e, M15g, INV-1, INV-2.
 *
 * The replay strip at the bottom is the part worth pausing on. It rebuilds the answer from
 * the stored snapshot alone and reports whether it still matches. "Explainable forever" is
 * a claim most systems make and none can check; here it is a row on the page that can say
 * no.
 */

import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ApprovalCard } from "@/components/approval";
import { PacketView } from "@/components/packet";
import { ApiError, api } from "@/lib/api";
import { ErrorPanel } from "@/components/ui";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Decision" };

export default async function DecisionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  let data;
  let replay: Awaited<ReturnType<typeof api.replay>> | null = null;
  try {
    data = await api.decision(id);
    replay = await api.replay(id).catch(() => null);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    return (
      <main className="max-w-4xl px-6 py-10 md:px-10">
        <ErrorPanel title="Could not load">
          Could not load this decision. Run `make api`.
        </ErrorPanel>
      </main>
    );
  }

  const pending = data.recommendations.filter((r) =>
    ["SUGGESTED", "REVIEWED"].includes(r.status),
  ).length;

  return (
    <main className="max-w-4xl px-6 py-10 md:px-10">
      <Link
        href="/decisions"
        className="text-xs uppercase tracking-[0.14em] text-muted-foreground underline-offset-4 transition-colors hover:text-foreground"
      >
        ← All decisions
      </Link>

      <header className="mb-10 mt-4">
        <p className="eyebrow">Decision packet</p>
        <h1 className="title-section mt-1.5 text-[2rem] leading-tight">{data.question}</h1>
        <p className="mt-2 font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
          {new Date(data.generated_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}
        </p>
      </header>

      <PacketView packet={data.packet} />

      <section className="mt-10 border-t border-border/70 pt-8">
        <p className="eyebrow-sm">INV-1</p>
        <h2 className="title-panel mt-0.5">Approval</h2>
        {/*
          The copy has to follow the data. A historical packet whose recommendations were all
          approved and executed last season was still being captioned "Nothing here has
          happened", which is the opposite of true and undermines the one sentence on this
          page that has to be believed.
        */}
        <p className="mb-4 mt-1 text-xs text-muted-foreground">
          {pending === 0
            ? "Every recommendation here has been decided. Nothing executed without a human approving it first."
            : pending === data.recommendations.length
              ? "Nothing here has happened. Each recommendation waits for a human with the right role."
              : `${pending} of ${data.recommendations.length} still waiting on a human with the right role. Nothing executes before that.`}
        </p>
        <div className="space-y-3">
          {data.recommendations.map((recommendation) => (
            <ApprovalCard key={recommendation.id} recommendation={recommendation} />
          ))}
        </div>
      </section>

      <section className="mt-10 border-t border-border/70 pt-8">
        <p className="eyebrow-sm">INV-2</p>
        <h2 className="title-panel mt-0.5">Frozen evidence</h2>
        <dl className="mt-4 space-y-2.5 text-sm">
          <Row label="Content hash">
            <span className="break-all font-mono text-xs">
              {data.evidence_snapshot.content_hash}
            </span>
          </Row>
          <Row label="Captured">
            {data.evidence_snapshot.captured_at
              ? new Date(data.evidence_snapshot.captured_at).toLocaleString("en-IN", {
                  timeZone: "Asia/Kolkata",
                })
              : "—"}
          </Row>
          <Row label="Module versions">
            <span className="font-mono text-xs">
              {Object.entries(data.evidence_snapshot.module_versions)
                .map(([module, version]) => `${module.replace(/_intelligence$/, "")} ${version}`)
                .join(" · ")}
            </span>
          </Row>
          {replay && (
            <Row label="Replay">
              {replay.identical ? (
                <span className="text-primary">
                  Rebuilt from the snapshot alone and identical — this answer is still
                  reproducible.
                </span>
              ) : (
                <span className="text-destructive">
                  Rebuilt from the snapshot and it differs:{" "}
                  {Object.entries(replay.matches_original)
                    .filter(([, ok]) => !ok)
                    .map(([section]) => section)
                    .join(", ")}
                  . A coefficient changed without a version bump.
                </span>
              )}
            </Row>
          )}
        </dl>
      </section>
    </main>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1">
      <dt className="w-36 shrink-0 text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        {label}
      </dt>
      <dd className="min-w-0 flex-1 leading-relaxed">{children}</dd>
    </div>
  );
}
