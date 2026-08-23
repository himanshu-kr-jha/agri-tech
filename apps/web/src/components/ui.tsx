/**
 * The layout primitives every screen is built from.
 *
 * Extracted so that the design language lives in one file rather than in fourteen sets of
 * hand-written class strings. The rules these encode — micro-caps eyebrow above a serif
 * title, hairline borders instead of shadows, a smaller muted unit beside every number —
 * are the whole design. A page that reaches past these for raw Tailwind is usually a page
 * that is about to drift.
 *
 * See ui-clone-workspace/site-dna.md for where each rule came from.
 */

import type { ReactNode } from "react";

// --------------------------------------------------------------------------- page header

/**
 * The top of every screen: eyebrow, serif title, optional subtitle, optional right rail.
 *
 * The subtitle is capped at `max-w-xl` deliberately. Long measure at 15px is the fastest
 * way to make a dense console feel like a document nobody finishes.
 */
export function PageHeader({
  eyebrow,
  title,
  subtitle,
  aside,
}: {
  eyebrow: string;
  title: ReactNode;
  subtitle?: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <header className="mb-10 flex flex-wrap items-end justify-between gap-6">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1 className="title-page mt-1.5">{title}</h1>
        {subtitle && (
          <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-muted-foreground">
            {subtitle}
          </p>
        )}
      </div>
      {aside && <div className="flex items-center gap-3">{aside}</div>}
    </header>
  );
}

// --------------------------------------------------------------------------- panel

export function Panel({
  children,
  className = "",
  as: Tag = "section",
  ...rest
}: {
  children: ReactNode;
  className?: string;
  as?: "section" | "div" | "article";
  "aria-label"?: string;
}) {
  return (
    <Tag className={`panel ${className}`} {...rest}>
      {children}
    </Tag>
  );
}

/**
 * A panel's own header. Same eyebrow-over-serif rhythm as the page header, one size down,
 * with meta sitting on the title's baseline rather than below it.
 */
export function PanelHeader({
  eyebrow,
  title,
  meta,
}: {
  eyebrow: string;
  title: ReactNode;
  meta?: ReactNode;
}) {
  return (
    <div className="mb-5 flex items-start justify-between gap-4">
      <div>
        <p className="eyebrow-sm">{eyebrow}</p>
        <h2 className="title-panel mt-0.5">{title}</h2>
      </div>
      {meta && <div className="shrink-0 pt-4 text-xs text-muted-foreground">{meta}</div>}
    </div>
  );
}

// --------------------------------------------------------------------------- kpi tile

/**
 * The number tile.
 *
 * `unit` renders as a smaller muted suffix rather than being folded into the value string,
 * because the TypeScript convention in CLAUDE.md is that every rendered number carries its
 * unit — and a unit that is part of the number can't be styled down or read out separately.
 *
 * `invert` is the attention slot: green fill, white type. At most one per screen. Two
 * inverted tiles and neither one is urgent any more.
 */
export function KpiTile({
  label,
  value,
  unit,
  caption,
  icon,
  invert = false,
  chip,
}: {
  label: string;
  value: ReactNode;
  unit?: string | null;
  caption?: ReactNode;
  icon?: ReactNode;
  invert?: boolean;
  chip?: ReactNode;
}) {
  return (
    <div className={`kpi-tile flex h-full flex-col ${invert ? "kpi-tile-invert" : ""}`}>
      <div className="flex items-start justify-between gap-2">
        <span className="kpi-label">{label}</span>
        <span className={invert ? "text-primary-foreground/60" : "text-muted-foreground/70"}>
          {chip ?? icon}
        </span>
      </div>
      <div className="kpi-value flex items-baseline gap-1.5 tabular-nums">
        <span>{value}</span>
        {unit && (
          <span
            className={`font-sans text-[13px] font-normal tracking-normal ${
              invert ? "text-primary-foreground/70" : "text-muted-foreground"
            }`}
          >
            {unit}
          </span>
        )}
      </div>
      {caption && (
        <p
          className={`mt-auto pt-3 text-xs leading-snug ${
            invert ? "text-primary-foreground/70" : "text-muted-foreground"
          }`}
        >
          {caption}
        </p>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- chip

export function Chip({
  children,
  tone = "neutral",
  className = "",
}: {
  children: ReactNode;
  tone?: "neutral" | "accent" | "alert";
  className?: string;
}) {
  const dot =
    tone === "alert"
      ? "bg-destructive"
      : tone === "accent"
        ? "bg-accent"
        : "bg-chart-2";
  return (
    <span className={`chip ${className}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} aria-hidden="true" />
      {children}
    </span>
  );
}

// --------------------------------------------------------------------------- empty state

/**
 * Empty states are one muted sentence. No illustration, no button, no shrug emoji.
 *
 * In this product an empty list is frequently the *correct and good* answer — nothing is
 * waiting on you — and dressing it up as a failure state teaches the wrong reflex.
 */
export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="py-2 text-sm leading-relaxed text-muted-foreground">{children}</p>;
}

// --------------------------------------------------------------------------- hairline row

/** A list row separated by hairlines rather than cards. Used for dense tabular content. */
export function Row({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`border-b border-border/60 py-3.5 last:border-0 ${className}`}>{children}</div>
  );
}

// --------------------------------------------------------------------------- error panel

export function ErrorPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="panel border-destructive/25 bg-destructive/[0.03]">
      <p className="eyebrow-sm text-destructive/80">{title}</p>
      <p className="mt-2 text-sm leading-relaxed text-foreground/80">{children}</p>
    </div>
  );
}
