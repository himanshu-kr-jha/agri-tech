/**
 * The components that carry the product's invariants into the UI.
 *
 * Any surface showing an AI-derived number MUST use these. That is how UI-02 and UI-04 stay
 * true without every page author remembering the rule — if a number is rendered bare, it is
 * a review finding, not a style preference.
 *
 * See docs/ARCHITECTURE.md §8 and docs/SRS.md §3.1.
 */

import type { ReactNode } from "react";

// --------------------------------------------------------------------------- types

export type SourceType =
  | "FIELD_OFFICER"
  | "FARMER_SELF_REPORT"
  | "AI_INFERENCE"
  | "EXTERNAL_SOURCE"
  | "ORG_RECORD"
  | "FIXTURE";

export type VerificationStatus = "UNVERIFIED" | "VERIFIED" | "DISPUTED" | "SUPERSEDED";

export interface Provenance {
  sourceType: SourceType;
  sourceLabel?: string;
  observedAt: string;
  confidence: number;
  verificationStatus: VerificationStatus;
  isStale?: boolean;
  hasOpenDiscrepancy?: boolean;
}

// --------------------------------------------------------------------------- confidence

/**
 * UI-02: every AI-derived number renders with its confidence.
 *
 * Bands are deliberately coarse. A number presented as "confidence 0.7314" implies a
 * precision the underlying decay model does not have.
 */
export function ConfidenceChip({ value, className = "" }: { value: number; className?: string }) {
  const pct = Math.round(value * 100);
  const band = value >= 0.8 ? "high" : value >= 0.55 ? "medium" : "low";
  const styles: Record<string, string> = {
    high: "bg-emerald-50 text-emerald-800 ring-emerald-600/20 dark:bg-emerald-950 dark:text-emerald-200 dark:ring-emerald-400/30",
    medium:
      "bg-amber-50 text-amber-800 ring-amber-600/20 dark:bg-amber-950 dark:text-amber-200 dark:ring-amber-400/30",
    low: "bg-rose-50 text-rose-800 ring-rose-600/20 dark:bg-rose-950 dark:text-rose-200 dark:ring-rose-400/30",
  };
  return (
    <span
      className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset ${styles[band]} ${className}`}
      title={`Confidence ${pct}% (${band})`}
    >
      {pct}%
    </span>
  );
}

// --------------------------------------------------------------------------- provenance

const SOURCE_LABEL: Record<SourceType, string> = {
  FIELD_OFFICER: "Field officer",
  FARMER_SELF_REPORT: "Farmer reported",
  AI_INFERENCE: "AI inferred",
  EXTERNAL_SOURCE: "External source",
  ORG_RECORD: "Organization record",
  FIXTURE: "Demo fixture",
};

/**
 * UI-02: hover any consequential value to see where it came from.
 *
 * This is the visible half of INV-3. A field-verified observation and a three-month-old
 * self-report must not look identical on screen, because they are not worth the same.
 */
export function ProvenancePopover({
  provenance,
  children,
}: {
  provenance: Provenance;
  children: ReactNode;
}) {
  const { sourceType, sourceLabel, observedAt, confidence, verificationStatus, isStale } =
    provenance;
  const observed = new Date(observedAt).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });

  return (
    <span className="group relative inline-flex items-center gap-1">
      <span className={isStale ? "text-neutral-500 dark:text-neutral-400" : ""}>{children}</span>
      <ConfidenceChip value={confidence} />
      {isStale && <StaleBadge />}
      {provenance.hasOpenDiscrepancy && <DiscrepancyBadge />}
      <span
        role="tooltip"
        className="pointer-events-none invisible absolute left-0 top-full z-50 mt-1 w-64 rounded-lg border border-neutral-200 bg-white p-3 text-xs shadow-lg group-hover:visible dark:border-neutral-700 dark:bg-neutral-900"
      >
        <span className="block font-medium">{sourceLabel ?? SOURCE_LABEL[sourceType]}</span>
        <span className="mt-1 block text-neutral-600 dark:text-neutral-400">
          Observed {observed}
        </span>
        <span className="mt-1 block text-neutral-600 dark:text-neutral-400">
          {verificationStatus === "VERIFIED"
            ? "Verified"
            : verificationStatus === "DISPUTED"
              ? "Disputed — awaiting verification"
              : "Not yet verified"}
        </span>
        {isStale && (
          <span className="mt-1 block text-amber-700 dark:text-amber-300">
            Stale — older than this attribute&apos;s freshness window
          </span>
        )}
      </span>
    </span>
  );
}

export function StaleBadge() {
  return (
    <span
      className="inline-flex items-center rounded px-1 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-700 ring-1 ring-inset ring-amber-600/30 dark:text-amber-300"
      title="This value is older than its freshness window"
    >
      stale
    </span>
  );
}

/**
 * INV-4 / UI-10: conflicts are surfaced at the point of use, not hidden in an admin screen.
 */
export function DiscrepancyBadge({ onClick }: { onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center rounded px-1 py-0.5 text-[10px] font-medium uppercase tracking-wide text-rose-700 ring-1 ring-inset ring-rose-600/30 hover:bg-rose-50 dark:text-rose-300 dark:hover:bg-rose-950"
      title="Sources disagree about this value — no value has been chosen"
    >
      conflict
    </button>
  );
}

// --------------------------------------------------------------------------- demo data

/**
 * UI-04 / C-2: synthetic data is labelled everywhere it appears, including in exports.
 *
 * Labelling it honestly is a credibility signal, not a blemish — a judge who finds an
 * unlabelled invented number stops trusting every other number on the screen.
 */
export function DemoDataBadge({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-flex items-center rounded bg-violet-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-violet-700 ring-1 ring-inset ring-violet-600/20 dark:bg-violet-950 dark:text-violet-300 ${className}`}
      title="Synthetic demonstration data — not a real observation"
    >
      demo data
    </span>
  );
}

// --------------------------------------------------------------------------- approval

/**
 * INV-1 made visible: AI recommends, a human approves, and only then does anything execute.
 *
 * When the viewer lacks approval authority the control is disabled *with an explanation*
 * (UI-07) rather than hidden — hiding it makes the boundary invisible and the product feel
 * arbitrary. Note this is presentation only: the server enforces the same rule (FR-707).
 */
export function ApprovalGate({
  canApprove,
  reason,
  children,
}: {
  canApprove: boolean;
  reason?: string;
  children: ReactNode;
}) {
  if (canApprove) return <>{children}</>;
  return (
    <span
      className="inline-flex cursor-not-allowed opacity-50"
      title={reason ?? "Your role does not include approval authority for this decision"}
      aria-disabled="true"
    >
      {children}
    </span>
  );
}

// --------------------------------------------------------------------------- formatting

/** ADR-0009: money is paise on the wire; rupees only at the edge. */
export function formatInr(paise: number, { indianGrouping = true } = {}): string {
  const rupees = paise / 100;
  return rupees.toLocaleString(indianGrouping ? "en-IN" : "en-US", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: rupees % 1 === 0 ? 0 : 2,
  });
}

/** ADR-0009: area is square metres canonical; acres for display. */
export function sqmToAcres(sqm: number): number {
  return sqm / 4046.8564224;
}

export function formatArea(sqm: number, unit: "acre" | "hectare" = "acre"): string {
  const value = unit === "acre" ? sqmToAcres(sqm) : sqm / 10000;
  return `${value.toLocaleString("en-IN", { maximumFractionDigits: 2 })} ${unit === "acre" ? "ac" : "ha"}`;
}

export function formatMass(kg: number): string {
  if (kg >= 1000) {
    return `${(kg / 1000).toLocaleString("en-IN", { maximumFractionDigits: 1 })} t`;
  }
  return `${kg.toLocaleString("en-IN", { maximumFractionDigits: 1 })} kg`;
}
