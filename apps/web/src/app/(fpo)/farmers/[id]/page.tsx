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
  DiscrepancyBadge,
  StaleBadge,
  formatMass,
} from "@/components/invariants";
import { ErrorPanel } from "@/components/ui";

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
      <main className="max-w-5xl px-6 py-10 md:px-10">
        <ErrorPanel title={status === 403 ? "Not visible to you" : "API unreachable"}>
          {status === 403
            ? "You may not view this farmer. Farmers see only their own record; organization staff see their members."
            : "Could not reach the API. Run `make api`."}
        </ErrorPanel>
      </main>
    );
  }

  const { farmer, plots, crop_cycles: cycles, lot_contributions: contributions } = data;
  const active = cycles.filter((c) => c.status === "GROWING");
  const past = cycles.filter((c) => c.status !== "GROWING");

  return (
    <main className="max-w-5xl px-6 py-10 md:px-10">
      <Link
        href="/farmers"
        className="text-xs uppercase tracking-[0.14em] text-muted-foreground underline-offset-4 transition-colors hover:text-foreground"
      >
        ← All farmers
      </Link>

      <header className="mb-10 mt-4">
        <p className="eyebrow">Member</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-3">
          <h1 className="title-section text-[2rem]">{farmer.name}</h1>
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          {[farmer.village, farmer.block, farmer.tract ? TRACT_LABEL[farmer.tract] : null]
            .filter(Boolean)
            .join(" · ")}
        </p>
      </header>

      <Section title="Plots" count={plots.length}>
        <ul>
          {plots.map((plot) => (
            <li
              key={plot.id}
              className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-border/60 py-3 last:border-0"
            >
              <span className="w-16 shrink-0 font-medium">{plot.label}</span>
              <span className="tabular-nums">
                <span className="font-serif text-[15px] text-primary">
                  {plot.area_acres.toFixed(2)}
                </span>
                <span className="ml-1 text-xs text-muted-foreground">ac</span>
              </span>
              {plot.provenance && (
                <>
                  <ConfidenceChip value={plot.provenance.confidence} />
                  {plot.provenance.is_stale && <StaleBadge />}
                  {plot.provenance.has_open_discrepancy && <DiscrepancyBadge />}
                  <span className="text-xs text-muted-foreground">
                    {plot.provenance.source_type.replace(/_/g, " ").toLowerCase()},{" "}
                    {new Date(plot.provenance.observed_at).toLocaleDateString("en-IN", {
                      day: "numeric",
                      month: "short",
                      year: "numeric",
                    })}
                  </span>
                </>
              )}
              <span className="ml-auto text-xs text-muted-foreground">
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
          <ul>
            {contributions.map((item, index) => (
              <li
                key={index}
                className="flex items-center gap-3 border-b border-border/60 py-3 last:border-0"
              >
                <span className="font-medium">{item.crop}</span>
                <span className="font-serif text-[15px] tabular-nums text-primary">
                  {formatMass(item.quantity_kg)}
                </span>
                {item.grade && (
                  <span className="text-xs text-muted-foreground">Grade {item.grade}</span>
                )}
                <span className="ml-auto font-mono text-xs text-muted-foreground">{item.lot}</span>
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
    <section className="mb-6">
      <div className="mb-3 flex items-baseline gap-2.5">
        <h2 className="title-panel">{title}</h2>
        <span className="text-xs text-muted-foreground">({count})</span>
      </div>
      <div className="panel py-1">{children}</div>
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
    <ul>
      {cycles.map((cycle) => (
        <li
          key={cycle.id}
          className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-border/60 py-3 last:border-0"
        >
          <span className="w-20 shrink-0 font-medium">{cycle.crop}</span>
          <span className="text-xs text-muted-foreground">{cycle.variety}</span>
          <span className="text-xs uppercase tracking-[0.12em] text-muted-foreground">
            {cycle.season}
          </span>
          <span className="tabular-nums">
            <span className="font-serif text-[15px] text-primary">
              {cycle.area_acres.toFixed(2)}
            </span>
            <span className="ml-1 text-xs text-muted-foreground">ac</span>
          </span>
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
              <span className="flex items-center gap-2 text-xs text-muted-foreground">
                <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
                no health reading — a field visit would raise this forecast&apos;s confidence
              </span>
            ))}
          <span className="ml-auto text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            {cycle.status.toLowerCase().replace(/_/g, " ")}
          </span>
        </li>
      ))}
    </ul>
  );
}
