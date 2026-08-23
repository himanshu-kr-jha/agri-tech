/**
 * Impact panel — M20, FR-1201…1203, SAF-12.
 *
 * The honest version of a metrics dashboard. It shows what could *not* be attributed as
 * prominently as what could, because a panel that reports only successes is measuring the
 * selection, not the impact — and any FPO board that has seen one vendor dashboard already
 * knows that.
 *
 * On a fresh install every number here is zero, and that is the correct thing to show. The
 * loop closes when advice is followed and outcomes are recorded; claiming impact before then
 * would be the exact dishonesty this screen exists to avoid.
 */

import { ApiError, api } from "@/lib/api";
import { DemoDataBadge } from "@/components/invariants";

export const dynamic = "force-dynamic";

const STRENGTH_NOTE: Record<string, string> = {
  HIGH: "Followed faithfully, moved materially, no confounder we track",
  MODERATE: "Followed and moved, but less decisively",
  UNCERTAIN: "Moved inside ordinary variation, or had no baseline",
  CONFOUNDED: "Something else would explain it equally well",
};

export default async function ImpactPage() {
  let data;
  try {
    data = await api.impact();
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 0;
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <h1 className="text-2xl font-semibold">Impact</h1>
        <p className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200">
          {status === 403 ? "Organization-internal." : "Could not reach the API. Run `make api`."}
        </p>
      </main>
    );
  }

  const nothingYet = data.interventions === 0;

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <header className="mb-6">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">Impact</h1>
          <DemoDataBadge />
        </div>
        <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
          What the decision loop has actually recorded — including what it could not honestly
          claim.
        </p>
      </header>

      {nothingYet ? (
        <div className="rounded-xl border border-neutral-200 p-6 dark:border-neutral-800">
          <p className="text-sm">
            Nothing to report yet. Impact is measured from recommendations that were approved,
            executed, and whose outcomes were recorded against a baseline.
          </p>
          <p className="mt-2 text-sm text-neutral-500">
            An empty panel is the correct answer here. Filling it with activity counts — how
            many questions were asked, how many packets generated — would be reporting our own
            busyness as the collective&apos;s benefit.
          </p>
        </div>
      ) : (
        <>
          <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Actions executed" value={data.interventions} />
            <Stat label="Attributed" value={data.attributions} />
            <Stat
              label="Could not attribute"
              value={data.unattributable}
              detail="advice not followed"
            />
            <Stat
              label="Forecast error"
              value={
                data.mean_absolute_error != null
                  ? `${Math.round(data.mean_absolute_error * 100)}%`
                  : "—"
              }
              detail={`${data.predictions_scored} scored`}
            />
          </section>

          <section className="mt-8">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
              Attribution strength
            </h2>
            <ul className="mt-2 divide-y divide-neutral-100 rounded-xl border border-neutral-200 dark:divide-neutral-900 dark:border-neutral-800">
              {Object.entries(STRENGTH_NOTE).map(([strength, note]) => (
                <li key={strength} className="flex items-baseline gap-3 px-4 py-2.5 text-sm">
                  <span className="w-24 shrink-0 font-medium">{strength.toLowerCase()}</span>
                  <span className="tabular-nums">{data.attribution_strength[strength] ?? 0}</span>
                  <span className="text-xs text-neutral-500">{note}</span>
                </li>
              ))}
            </ul>
          </section>

          <section className="mt-8">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
              Adherence
            </h2>
            <p className="mb-2 mt-0.5 text-xs text-neutral-400">
              Whether the recommendation was actually followed. Advice nobody took tells us
              nothing about the advice (INV-7).
            </p>
            <ul className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
              {Object.entries(data.adherence).map(([key, count]) => (
                <li key={key}>
                  <span className="text-neutral-500">{key.toLowerCase()}</span>{" "}
                  <span className="font-medium tabular-nums">{count}</span>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}

      <p className="mt-8 border-t border-neutral-100 pt-4 text-xs text-neutral-500 dark:border-neutral-900">
        {data.note}
      </p>
    </main>
  );
}

function Stat({
  label,
  value,
  detail,
}: {
  label: string;
  value: number | string;
  detail?: string;
}) {
  return (
    <div className="rounded-xl border border-neutral-200 p-4 dark:border-neutral-800">
      <div className="text-xs font-medium uppercase tracking-wide text-neutral-500">{label}</div>
      <div className="mt-2 text-2xl font-semibold tabular-nums">{value}</div>
      {detail && <div className="mt-0.5 text-xs text-neutral-500">{detail}</div>}
    </div>
  );
}
