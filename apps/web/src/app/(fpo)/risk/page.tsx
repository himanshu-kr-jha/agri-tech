/**
 * Risk register — M15d, UI-08, FR-552, FR-554.
 *
 * Sorted by exposure, not by probability. A 90%-likely problem affecting nine acres is not
 * the top of this list; a 30%-likely one affecting nine hundred is. Sorting by likelihood is
 * the mistake that puts "April is hot in Prayagraj" above "1,868 tonnes harvest into the
 * annual price floor".
 *
 * Every row names who is exposed. A hazard with no exposure attached is a weather report.
 */

import { ApiError, api, type RiskEntry } from "@/lib/api";
import { DemoDataBadge, formatInr } from "@/components/invariants";

export const dynamic = "force-dynamic";

const BAND: Record<string, string> = {
  HIGH: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200",
  MEDIUM: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
  LOW: "bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300",
};

const DOMAIN_LABEL: Record<string, string> = {
  WEATHER: "weather",
  CLIMATE: "climate",
  MARKET: "market",
  CROP_HEALTH: "crop health",
  POLICY: "policy",
  SUPPLY_CHAIN: "supply chain",
  GLOBAL: "global",
};

function exposureScore(entry: RiskEntry): number {
  return (
    (entry.value_at_risk_paise ?? 0) / 100 +
    (entry.farmers_affected ?? 0) * 1000 +
    (entry.area_affected_acres ?? 0) * 100
  );
}

export default async function RiskPage() {
  let data;
  try {
    data = await api.riskRegister();
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 0;
    return (
      <main className="mx-auto max-w-4xl px-6 py-12">
        <h1 className="text-2xl font-semibold">Risk register</h1>
        <p className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200">
          {status === 403
            ? "The risk register is organization-internal."
            : "Could not reach the API. Run `make api`."}
        </p>
      </main>
    );
  }

  const entries = [...data.entries].sort((a, b) => exposureScore(b) - exposureScore(a));

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <header className="mb-6">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">Risk register</h1>
          <DemoDataBadge />
        </div>
        <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
          Ordered by how much is exposed, not by how likely it is. Weather figures are
          frequencies from 30 years of record — how often the window has been hit, not a
          forecast that it will be.
        </p>
      </header>

      {entries.length === 0 ? (
        <p className="rounded-lg border border-neutral-200 p-6 text-sm text-neutral-500 dark:border-neutral-800">
          Nothing on the register yet. It fills in when the assistant is asked a question that
          runs the risk module.
        </p>
      ) : (
        <ul className="space-y-3">
          {entries.map((entry) => (
            <li
              key={entry.id}
              className="rounded-xl border border-neutral-200 p-4 dark:border-neutral-800"
            >
              <div className="flex flex-wrap items-baseline gap-2">
                <h2 className="font-medium">{entry.title}</h2>
                <span className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-xs text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400">
                  {DOMAIN_LABEL[entry.domain] ?? entry.domain.toLowerCase()}
                </span>
                <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${BAND[entry.likelihood]}`}>
                  {entry.likelihood.toLowerCase()} likelihood
                </span>
                <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${BAND[entry.impact]}`}>
                  {entry.impact.toLowerCase()} impact
                </span>
              </div>

              <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-neutral-600 dark:text-neutral-400">
                {entry.farmers_affected != null && (
                  <span>
                    <strong className="tabular-nums">{entry.farmers_affected.toLocaleString("en-IN")}</strong>{" "}
                    farmers
                  </span>
                )}
                {entry.area_affected_acres != null && (
                  <span>
                    <strong className="tabular-nums">
                      {entry.area_affected_acres.toLocaleString("en-IN")}
                    </strong>{" "}
                    acres
                  </span>
                )}
                {entry.value_at_risk_paise != null && (
                  <span>
                    <strong>{formatInr(entry.value_at_risk_paise)}</strong> at stake
                  </span>
                )}
                {typeof entry.detail?.probability === "number" && (
                  <span>
                    <strong className="tabular-nums">
                      {Math.round((entry.detail.probability as number) * 100)}%
                    </strong>{" "}
                    of years in the record
                  </span>
                )}
              </p>

              {entry.recommended_action && (
                <p className="mt-2 border-t border-neutral-100 pt-2 text-sm dark:border-neutral-900">
                  <span className="text-neutral-500">What would reduce it: </span>
                  {entry.recommended_action}
                </p>
              )}

              <p className="mt-2 text-xs text-neutral-400">
                {entry.owner_role && `owned by ${entry.owner_role.replace(/_/g, " ").toLowerCase()}`}
                {entry.review_on &&
                  ` · review by ${new Date(entry.review_on).toLocaleDateString("en-IN", {
                    day: "numeric",
                    month: "short",
                  })}`}
                {entry.evidence?.length ? ` · ${entry.evidence.length} sources` : ""}
              </p>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
