/**
 * The icon set.
 *
 * Hand-drawn rather than pulled from a package on purpose: the UI needs about a dozen
 * glyphs, all in one stroke style, and an icon library would be a build dependency for
 * something this small. Every icon here is a 24×24 viewBox, 1.5 stroke, round caps — the
 * outline weight the design language expects. Anything heavier fights the hairlines.
 *
 * Icons are decoration. They sit beside a label, never replace one, so they are
 * `aria-hidden` by default.
 */

import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Icon({ size = 16, children, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

export function IconAsk(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5Z" />
    </Icon>
  );
}

export function IconDashboard(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
    </Icon>
  );
}

export function IconDecisions(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
      <rect x="8" y="2" width="8" height="4" rx="1" />
      <path d="m9 14 2 2 4-4" />
    </Icon>
  );
}

export function IconRisk(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />
      <path d="M12 8v4" />
      <path d="M12 16h.01" />
    </Icon>
  );
}

export function IconMarket(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="m22 7-8.5 8.5-5-5L2 17" />
      <path d="M16 7h6v6" />
    </Icon>
  );
}

export function IconFarmers(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </Icon>
  );
}

export function IconImpact(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M7 20h10" />
      <path d="M12 20V9" />
      <path d="M12 9c0-3 2-6 6-6 0 4-2.5 6-6 6Z" />
      <path d="M12 13c0-2.5-2-5-5-5 0 3.5 2 5 5 5Z" />
    </Icon>
  );
}

export function IconFarm(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3 21V10l9-6 9 6v11" />
      <path d="M9 21v-6h6v6" />
    </Icon>
  );
}

export function IconSearch(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </Icon>
  );
}

export function IconBell(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.7 21a2 2 0 0 1-3.4 0" />
    </Icon>
  );
}

export function IconArrowUpRight(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M7 17 17 7" />
      <path d="M8 7h9v9" />
    </Icon>
  );
}

export function IconCheck(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="m4 12 5 5L20 6" />
    </Icon>
  );
}

export function IconAlert(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </Icon>
  );
}

export function IconClock(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </Icon>
  );
}

export function IconEye(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </Icon>
  );
}

export function IconDatabase(props: IconProps) {
  return (
    <Icon {...props}>
      <ellipse cx="12" cy="5" rx="8" ry="3" />
      <path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
      <path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
    </Icon>
  );
}

export function IconChevronDown(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="m6 9 6 6 6-6" />
    </Icon>
  );
}

/** The brand mark. A leaf on a stem — the only filled shape in the whole UI. */
export function IconLeaf({ size = 18, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z" />
      <path d="M2 21c0-3 1.85-5.36 5.08-6" />
    </svg>
  );
}

/* ---------------------------------------------------------------------------------------
 * Landing page (ADR-0024).
 *
 * The public page renders these at `size={28}` rather than the console's 16 — a marketing
 * surface needs a glyph you can read across a room. The 1.5 stroke was chosen for 16px but
 * holds at 28; going heavier to "balance" the larger size is what makes an icon set look
 * like two icon sets.
 * ------------------------------------------------------------------------------------ */

/** A closed loop. Crop cycles — the product's own noun, so it gets its own mark. */
export function IconCycle(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M21 12a9 9 0 0 0-9-9 9 9 0 0 0-6.4 2.6L3 8" />
      <path d="M3 3v5h5" />
      <path d="M3 12a9 9 0 0 0 9 9 9 9 0 0 0 6.4-2.6L21 16" />
      <path d="M21 21v-5h-5" />
    </Icon>
  );
}

/** Parcelled land seen from above. Acres mapped — plots, not a generic grid. */
export function IconAcres(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="3" y="5" width="18" height="14" rx="1.5" />
      <path d="M9 5v14" />
      <path d="M15 5v14" />
      <path d="M3 12h18" />
    </Icon>
  );
}

/** A hub with four members. The collective as a shape: nobody at the edge, one centre. */
export function IconCollective(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="2.5" />
      <circle cx="5" cy="6" r="2" />
      <circle cx="19" cy="6" r="2" />
      <circle cx="5" cy="18" r="2" />
      <circle cx="19" cy="18" r="2" />
      <path d="M6.6 7.5 10 10.4" />
      <path d="M17.4 7.5 14 10.4" />
      <path d="M6.6 16.5 10 13.6" />
      <path d="M17.4 16.5 14 13.6" />
    </Icon>
  );
}

/** A balance. Market linkage is a comparison — what a buyer nets against what they quote. */
export function IconScale(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 4v17" />
      <path d="M7 21h10" />
      <path d="M4.5 7h15" />
      <path d="M4.5 7 2 13h5L4.5 7Z" />
      <path d="M19.5 7 17 13h5l-2.5-6Z" />
    </Icon>
  );
}

/** An open book. Advisory — knowledge that someone reads, not a notification. */
export function IconBook(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 7v14" />
      <path d="M12 7a5 5 0 0 0-5-3H3v13h4a5 5 0 0 1 5 4" />
      <path d="M12 7a5 5 0 0 1 5-3h4v13h-4a5 5 0 0 0-5 4" />
    </Icon>
  );
}

/** A document with a rosette. Schemes and entitlements — a sanctioned paper. */
export function IconSeal(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h3" />
      <path d="M14 3v5h5" />
      <path d="M14 3l5 5" />
      <circle cx="17" cy="16" r="3" />
      <path d="m15 18.6-.5 3.4 2.5-1.5 2.5 1.5-.5-3.4" />
    </Icon>
  );
}

/** A stamp over a line. Approval — INV-1's whole promise in one glyph. */
export function IconApproval(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="10" r="6" />
      <path d="m9 10 2 2 4-4" />
      <path d="M5 20h14" />
    </Icon>
  );
}
