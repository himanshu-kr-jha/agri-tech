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
  // Hairline rings rather than filled pills: a chip appears beside nearly every number on
  // these screens, and three saturated blocks per row would read as an error state.
  const styles: Record<string, string> = {
    high: "text-primary ring-primary/25",
    medium: "text-accent-foreground/80 ring-accent/50 bg-accent/[0.07]",
    low: "text-destructive ring-destructive/30 bg-destructive/[0.04]",
  };
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[11px] font-medium tabular-nums ring-1 ring-inset ${styles[band]} ${className}`}
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
  FIXTURE: "Cached source",
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
      <span className={isStale ? "text-muted-foreground" : ""}>{children}</span>
      <ConfidenceChip value={confidence} />
      {isStale && <StaleBadge />}
      {provenance.hasOpenDiscrepancy && <DiscrepancyBadge />}
      <span
        role="tooltip"
        className="pointer-events-none invisible absolute left-0 top-full z-50 mt-1.5 w-64 rounded-md border border-border/70 bg-popover p-3.5 text-xs group-hover:visible"
      >
        <span className="eyebrow-sm block">{sourceLabel ?? SOURCE_LABEL[sourceType]}</span>
        <span className="mt-2 block text-muted-foreground">Observed {observed}</span>
        <span className="mt-1 block text-muted-foreground">
          {verificationStatus === "VERIFIED"
            ? "Verified"
            : verificationStatus === "DISPUTED"
              ? "Disputed — awaiting verification"
              : "Not yet verified"}
        </span>
        {isStale && (
          <span className="mt-1 block text-warning">
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
      className="inline-flex items-center rounded px-1 py-0.5 text-[10px] font-medium uppercase tracking-[0.14em] text-warning ring-1 ring-inset ring-warning/30"
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
      className="inline-flex items-center rounded px-1 py-0.5 text-[10px] font-medium uppercase tracking-[0.14em] text-destructive ring-1 ring-inset ring-destructive/30 transition-colors hover:bg-destructive/[0.06]"
      title="Sources disagree about this value — no value has been chosen"
    >
      conflict
    </button>
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
/**
 * Render a paise value according to the unit it is actually in.
 *
 * This exists because of a bug it now prevents: a buyer-selection recommendation carries
 * `recommended_value` in **paise per kilogram**, and the briefing rendered it as a rupee
 * total — producing "Rs 0.0 lakh · ₹18.54" next to each other, both wrong in different ways.
 *
 * The API always sends the unit alongside the number. Ignoring it is how a price becomes a
 * total, and money in this system is integer paise precisely so that nobody has to guess.
 */
export function formatValue(paise: number | null, unit: string | null): string | null {
  if (paise == null) return null;
  switch (unit) {
    case "paise_per_kg":
      return `₹${(paise / 100).toFixed(2)}/kg`;
    case "probability":
      return `${Math.round(paise)}%`;
    case null:
    case undefined:
      return formatInr(paise);
    default:
      // Every other unit the modules emit is a paise total: paise_margin_low,
      // paise_foregone, paise_at_risk, paise_shortfall, paise_per_year.
      return formatInr(paise);
  }
}

export function formatInr(paise: number, { indianGrouping = true } = {}): string {
  const rupees = paise / 100;
  return rupees.toLocaleString(indianGrouping ? "en-IN" : "en-US", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: rupees % 1 === 0 ? 0 : 2,
  });
}

/**
 * Role enums into something a person would say out loud.
 *
 * `FPO_CEO` had been rendering as "Fpo Ceo" via a bare CSS `capitalize`, and as "fpo ceo"
 * where the string was lowercased. Neither is a thing anyone calls that job. Acronyms in
 * this domain are load-bearing — FPO, PACS and SHG are three different legal forms — so they
 * stay uppercase and the rest reads as a sentence.
 */
const ROLE_ACRONYMS = new Set(["FPO", "PACS", "SHG", "CEO", "AI"]);

export function formatRole(role: string): string {
  const words = role.split("_").filter(Boolean);
  return words
    .map((word, i) => {
      if (ROLE_ACRONYMS.has(word.toUpperCase())) return word.toUpperCase();
      const lower = word.toLowerCase();
      return i === 0 ? lower[0].toUpperCase() + lower.slice(1) : lower;
    })
    .join(" ");
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
