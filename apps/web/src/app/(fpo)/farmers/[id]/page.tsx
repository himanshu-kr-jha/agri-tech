/**
 * Farmer 360 — the bottom of the drill-down (FR-806).
 *
 * This is the screen where the provenance layer becomes visible. Every plot area and crop
 * health reading renders with where it came from, how confident we are, and whether anyone
 * disagrees — because a CEO deciding on this farmer's crop needs to know whether they are
 * looking at a field-officer measurement from Tuesday or a self-report from March.
 */

import Link from "next/link";
import { notFound } from "next/navigation";

import { ApiError, TRACT_LABEL, api } from "@/lib/api";
import {
  ConfidenceChip,
  DemoDataBadge,
  DiscrepancyBadge,
  StaleBadge,
  formatMass,
} from "@/components/invariants";

export const dynamic = "force-dynamic";

export default async function FarmerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  let data;
  try {
    data = await api.farmer(id);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    const status = error instanceof ApiError ? error.status : 0;
    return (
      <main className="mx-auto max-w-4xl px-6 py-12">
        <p className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200">
          {status === 403
            ? "You may not view this farmer. Farmers see only their own record; organization staff see their members."
            : "Could not reach the API. Run `make api`."}
        </p>
      </main>
    );
  }

  const { farmer, plots, crop_cycles: cycles, lot_contributions: contributions } = data;
  const active = cycles.filter((c) => c.status === "GROWING");
  const past = cycles.filter((c) => c.status !== "GROWING");

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <Link
        href="/farmers"
        className="text-sm text-neutral-500 underline-offset-2 hover:underline"
      >
        ← All farmers
      </Link>

      <header className="mb-8 mt-3">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">{farmer.name}</h1>
          {farmer.is_synthetic && <DemoDataBadge />}
        </div>
        <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
          {[farmer.village, farmer.block, farmer.tract ? TRACT_LABEL[farmer.tract] : null]
            .filter(Boolean)
            .join(" · ")}
        </p>
      </header>

      <Section title="Plots" count={plots.length}>
        <ul className="divide-y divide-neutral-100 dark:divide-neutral-900">
          {plots.map((plot) => (
            <li key={plot.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
              <span className="w-16 shrink-0 font-medium">{plot.label}</span>
              <span className="tabular-nums">{plot.area_acres.toFixed(2)} ac</span>
              {plot.provenance && (
                <>
                  <ConfidenceChip value={plot.provenance.confidence} />
                  {plot.provenance.is_stale && <StaleBadge />}
                  {plot.provenance.has_open_discrepancy && <DiscrepancyBadge />}
                  <span className="text-xs text-neutral-500">
                    {plot.provenance.source_type.replace(/_/g, " ").toLowerCase()},{" "}
                    {new Date(plot.provenance.observed_at).toLocaleDateString("en-IN", {
                      day: "numeric",
                      month: "short",
                      year: "numeric",
                    })}
                  </span>
                </>
              )}
              <span className="ml-auto text-xs text-neutral-500">
                {[plot.soil_type, plot.irrigation_source].filter(Boolean).join(" · ")}
              </span>
            </li>
          ))}
        </ul>
      </Section>

      {active.length > 0 && (
        <Section title="Growing now" count={active.length}>
          <CycleTable cycles={active} showHealth />
        </Section>
      )}

      {contributions.length > 0 && (
        <Section title="Contributed to lots" count={contributions.length}>
          <ul className="divide-y divide-neutral-100 dark:divide-neutral-900">
            {contributions.map((item, index) => (
              <li key={index} className="flex items-center gap-3 py-2.5">
                <span className="font-medium">{item.crop}</span>
                <span className="tabular-nums">{formatMass(item.quantity_kg)}</span>
                {item.grade && (
                  <span className="text-xs text-neutral-500">Grade {item.grade}</span>
                )}
                <span className="ml-auto text-xs text-neutral-500">{item.lot}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {past.length > 0 && (
        <Section title="Past seasons" count={past.length}>
          <CycleTable cycles={past.slice(0, 12)} />
        </Section>
      )}
    </main>
  );
}

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-8">
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        {title} <span className="font-normal">({count})</span>
      </h2>
      <div className="rounded-xl border border-neutral-200 px-4 dark:border-neutral-800">
        {children}
      </div>
    </section>
  );
}

function CycleTable({
  cycles,
  showHealth = false,
}: {
  cycles: {
    id: string;
    crop: string;
    variety: string;
    season: string;
    status: string;
    area_acres: number;
    crop_health_pct: number | null;
    health_confidence: number | null;
    health_is_stale: boolean | null;
  }[];
  showHealth?: boolean;
}) {
  return (
    <ul className="divide-y divide-neutral-100 dark:divide-neutral-900">
      {cycles.map((cycle) => (
        <li key={cycle.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
          <span className="w-20 shrink-0 font-medium">{cycle.crop}</span>
          <span className="text-xs text-neutral-500">{cycle.variety}</span>
          <span className="text-xs text-neutral-500">{cycle.season}</span>
          <span className="tabular-nums">{cycle.area_acres.toFixed(2)} ac</span>
          {showHealth &&
            (cycle.crop_health_pct !== null ? (
              <span className="flex items-center gap-1.5">
                <span>health {Math.round(cycle.crop_health_pct)}%</span>
                {cycle.health_confidence !== null && (
                  <ConfidenceChip value={cycle.health_confidence} />
                )}
                {cycle.health_is_stale && <StaleBadge />}
              </span>
            ) : (
              <span className="text-xs text-amber-700 dark:text-amber-300">
                no health reading — a field visit would raise this forecast&apos;s confidence
              </span>
            ))}
          <span className="ml-auto text-xs text-neutral-500">
            {cycle.status.toLowerCase().replace(/_/g, " ")}
          </span>
        </li>
      ))}
    </ul>
  );
}
