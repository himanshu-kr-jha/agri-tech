/**
 * Open data conflicts — INV-4, UI-10, FR-304.
 *
 * The screen exists because of what it refuses to do. When two sources disagree about a
 * plot's area beyond tolerance, the system does not quietly pick 1.8 acres and move on; it
 * records a `DataDiscrepancy`, lowers the confidence of everything downstream, and puts the
 * disagreement here where a human can settle it.
 *
 * So the design rule for this page is the inverse of every other list: **do not present a
 * resolution.** The best-supported claim is shown, but it is shown as one row among the
 * competing rows, never promoted to a headline figure — because promoting it is exactly the
 * silent resolution the invariant forbids. The reader's job is to notice the spread.
 *
 * This was reachable from the dashboard's "unresolved data conflicts" tile long before it
 * existed; that tile 404'd. The API endpoint had been there the whole time.
 */

import type { Metadata } from "next";

import { ApiError, api, type Discrepancy, type DiscrepancyClaim } from "@/lib/api";
import { ConfidenceChip, sqmToAcres } from "@/components/invariants";
import { Chip, EmptyState, ErrorPanel, PageHeader, Panel } from "@/components/ui";
import { translator } from "@/lib/i18n";
import { currentLocale } from "@/lib/locale";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Discrepancies" };

const SOURCE_LABEL: Record<string, string> = {
  FIELD_OFFICER: "Field officer",
  FARMER_SELF_REPORT: "Farmer reported",
  AI_INFERENCE: "AI inferred",
  EXTERNAL_SOURCE: "External source",
  ORG_RECORD: "Organization record",
  FIXTURE: "Cached source",
};

const ATTRIBUTE_LABEL: Record<string, string> = {
  area_sqm: "Plot area",
  crop_health_pct: "Crop health",
  yield_kg: "Yield",
  quantity_kg: "Quantity",
};

/**
 * Values arrive in canonical units (ADR-0009: area in m², mass in kg). Render them the way
 * the rest of the console does, so a reader comparing this page to the farmer 360 is
 * comparing the same numbers.
 */
function display(value: number, unit: string): { figure: string; unit: string } {
  switch (unit) {
    case "sqm":
      return {
        figure: sqmToAcres(value).toLocaleString("en-IN", { maximumFractionDigits: 2 }),
        unit: "ac",
      };
    case "kg":
      return {
        figure: value.toLocaleString("en-IN", { maximumFractionDigits: 1 }),
        unit: "kg",
      };
    case "pct":
      return { figure: Math.round(value).toString(), unit: "%" };
    default:
      return {
        figure: value.toLocaleString("en-IN", { maximumFractionDigits: 2 }),
        unit,
      };
  }
}

function ClaimRow({
  claim,
  isBestSupported,
}: {
  claim: DiscrepancyClaim;
  isBestSupported: boolean;
}) {
  const shown = display(claim.value, claim.unit);
  return (
    <li className="flex flex-wrap items-baseline gap-x-4 gap-y-1.5 border-b border-border/60 py-3 last:border-0">
      <span className="w-44 shrink-0 text-sm text-foreground">
        {SOURCE_LABEL[claim.source_type] ?? claim.source_type.replace(/_/g, " ").toLowerCase()}
      </span>
      <span className="w-28 shrink-0 tabular-nums">
        <span className="font-serif text-[17px] text-primary">{shown.figure}</span>
        <span className="ml-1 text-xs text-muted-foreground">{shown.unit}</span>
      </span>
      <ConfidenceChip value={claim.confidence} />
      <span className="font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">
        {new Date(claim.observed_at).toLocaleDateString("en-IN", {
          day: "numeric",
          month: "short",
          year: "numeric",
        })}
      </span>
      {isBestSupported && (
        <span className="ml-auto text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
          best supported
        </span>
      )}
    </li>
  );
}

function DiscrepancyCard({ item }: { item: Discrepancy }) {
  const claims = [...item.claims].sort((a, b) => b.confidence - a.confidence);
  const overBy = item.spread_pct - item.tolerance_pct;

  return (
    <Panel>
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
        <div>
          <p className="eyebrow-sm">
            {item.subject_type} · {item.claims.length} sources disagree
          </p>
          <h2 className="title-panel mt-0.5">
            {ATTRIBUTE_LABEL[item.attribute] ?? item.attribute.replace(/_/g, " ")}
          </h2>
        </div>
        <div className="flex items-baseline gap-2">
          <span className="font-serif text-[26px] tabular-nums text-primary">
            {item.spread_pct.toFixed(0)}%
          </span>
          <span className="text-xs text-muted-foreground">
            spread · tolerance {item.tolerance_pct.toFixed(0)}%
          </span>
        </div>
      </div>

      <ul>
        {claims.map((claim) => (
          <ClaimRow
            key={claim.observation_id}
            claim={claim}
            isBestSupported={claim.value === item.best_supported_value}
          />
        ))}
      </ul>

      <p className="mt-4 border-t border-border/60 pt-3 text-xs leading-relaxed text-muted-foreground">
        {overBy > 0
          ? `${overBy.toFixed(0)} points outside tolerance. `
          : "Inside tolerance, held open for review. "}
        No value has been chosen. Every figure derived from this subject carries{" "}
        {item.effective_confidence !== null
          ? `a reduced confidence of ${Math.round(item.effective_confidence * 100)}%`
          : "reduced confidence"}{" "}
        until someone with the record in front of them decides.
      </p>

      <p className="mt-2 font-mono text-[11px] text-muted-foreground/70">
        {item.subject_type} {item.subject_id}
      </p>
    </Panel>
  );
}

export default async function DiscrepanciesPage() {
  const t = translator(await currentLocale());
  let data;
  try {
    data = await api.discrepancies();
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 0;
    return (
      <main className="px-6 py-10 md:px-10">
        <PageHeader eyebrow="INV-4" title="Data conflicts" />
        <ErrorPanel title={status === 403 ? "Organization-internal" : "API unreachable"}>
          {status === 403
            ? "Data conflicts are organization-internal. A farmer sees their own record, not the reconciliation queue."
            : "Could not reach the API. Run `make api`."}
        </ErrorPanel>
      </main>
    );
  }

  const { discrepancies, total } = data;

  return (
    <main className="max-w-5xl px-6 py-10 md:px-10">
      <PageHeader
        eyebrow="INV-4"
        title={t("con.conflicts.title")}
        subtitle={t("con.conflicts.sub")}
        aside={
          <>
            <Chip tone={total > 0 ? "accent" : "neutral"}>
              {total === 1 ? "1 open conflict" : `${total} open conflicts`}
            </Chip>
          </>
        }
      />

      {discrepancies.length === 0 ? (
        <Panel>
          <EmptyState>
            No open conflicts. Every consequential value currently has one supported answer —
            which is a real state, not an empty screen.
          </EmptyState>
        </Panel>
      ) : (
        <div className="space-y-3">
          {discrepancies.map((item) => (
            <DiscrepancyCard key={item.id} item={item} />
          ))}
        </div>
      )}
    </main>
  );
}
