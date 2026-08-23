/**
 * One decision, with its frozen evidence and its approval gate — M15e, M15g, INV-1, INV-2.
 *
 * The replay strip at the bottom is the part worth pausing on. It rebuilds the answer from
 * the stored snapshot alone and reports whether it still matches. "Explainable forever" is
 * a claim most systems make and none can check; here it is a row on the page that can say
 * no.
 */

import Link from "next/link";
import { notFound } from "next/navigation";

import { ApprovalCard } from "@/components/approval";
import { PacketView } from "@/components/packet";
import { ApiError, api } from "@/lib/api";

export const dynamic = "force-dynamic";

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
      <main className="mx-auto max-w-3xl px-6 py-12">
        <p className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200">
          Could not load this decision. Run `make api`.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <Link href="/decisions" className="text-sm text-neutral-500 underline-offset-2 hover:underline">
        ← All decisions
      </Link>

      <header className="mb-8 mt-3">
        <h1 className="text-xl font-semibold leading-snug tracking-tight">{data.question}</h1>
        <p className="mt-1 text-sm text-neutral-500">
          {new Date(data.generated_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}
        </p>
      </header>

      <PacketView packet={data.packet} />

      <section className="mt-10 border-t border-neutral-200 pt-8 dark:border-neutral-800">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Approval
        </h2>
        <p className="mb-3 mt-0.5 text-xs text-neutral-400">
          Nothing here has happened. Each recommendation waits for a human with the right role.
        </p>
        <div className="space-y-3">
          {data.recommendations.map((recommendation) => (
            <ApprovalCard key={recommendation.id} recommendation={recommendation} />
          ))}
        </div>
      </section>

      <section className="mt-10 border-t border-neutral-200 pt-8 dark:border-neutral-800">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Frozen evidence
        </h2>
        <dl className="mt-2 space-y-1.5 text-sm">
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
                <span className="text-emerald-700 dark:text-emerald-300">
                  Rebuilt from the snapshot alone and identical — this answer is still
                  reproducible.
                </span>
              ) : (
                <span className="text-amber-700 dark:text-amber-300">
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
    <div className="flex flex-wrap gap-x-3">
      <dt className="w-32 shrink-0 text-neutral-500">{label}</dt>
      <dd className="min-w-0 flex-1">{children}</dd>
    </div>
  );
}
