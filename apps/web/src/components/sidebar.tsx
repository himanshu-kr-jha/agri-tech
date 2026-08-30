"use client";

/**
 * The console spine.
 *
 * A client component for one reason only: it needs `usePathname` to know which item is
 * current. Everything else about the shell stays on the server.
 *
 * The active item is marked with a 2px gold rail *inset* on its left edge rather than a
 * filled background. That is the design's one use of the accent colour, and keeping it to
 * a single 2px line per screen is what stops the gold reading as decoration.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  IconAlert,
  IconAsk,
  IconDashboard,
  IconDatabase,
  IconDecisions,
  IconFarmers,
  IconImpact,
  IconLeaf,
  IconMarket,
  IconRisk,
} from "@/components/icons";

/**
 * ``labelKey`` rather than a label. This is a client component — it cannot read the locale
 * cookie, which lives on the server — so the shell resolves the strings and passes them in.
 * Keeping the *keys* here means the navigation's shape and order stay in one place instead
 * of being reassembled by whoever renders it.
 */
type NavItem = { href: string; labelKey: NavKey; icon: typeof IconAsk };

export type NavKey =
  | "con.nav.dashboard"
  | "con.nav.assistant"
  | "con.nav.decisions"
  | "con.nav.risk"
  | "con.nav.farmers"
  | "con.nav.market"
  | "con.nav.discrepancies"
  | "con.nav.knowledge"
  | "con.nav.impact";

export type GroupKey = "con.nav.group.decide" | "con.nav.group.collective";

/** Every string the shell has to resolve for this component. */
export type NavLabels = Record<NavKey | GroupKey, string>;

/**
 * Grouped the way the work is actually sequenced: you ask, you decide, then you look at
 * what the collective is made of. Not alphabetically, and not by which screen was built first.
 */
const NAV_GROUPS: { label: GroupKey | null; items: NavItem[] }[] = [
  {
    label: null,
    items: [{ href: "/dashboard", labelKey: "con.nav.dashboard", icon: IconDashboard }],
  },
  {
    label: "con.nav.group.decide" as GroupKey,
    items: [
      { href: "/assistant", labelKey: "con.nav.assistant", icon: IconAsk },
      { href: "/decisions", labelKey: "con.nav.decisions", icon: IconDecisions },
      { href: "/risk", labelKey: "con.nav.risk", icon: IconRisk },
    ],
  },
  {
    label: "con.nav.group.collective" as GroupKey,
    items: [
      { href: "/farmers", labelKey: "con.nav.farmers", icon: IconFarmers },
      { href: "/market", labelKey: "con.nav.market", icon: IconMarket },
      { href: "/discrepancies", labelKey: "con.nav.discrepancies", icon: IconAlert },
      { href: "/knowledge", labelKey: "con.nav.knowledge", icon: IconDatabase },
      { href: "/impact", labelKey: "con.nav.impact", icon: IconImpact },
    ],
  },
];

export function Sidebar({ labels }: { labels: NavLabels }) {
  const pathname = usePathname();

  return (
    <aside className="hidden w-[260px] shrink-0 flex-col bg-sidebar text-sidebar-foreground md:flex">
      <Link
        href="/dashboard"
        className="flex items-center gap-3 px-5 py-5 transition-opacity hover:opacity-90"
      >
        <span className="flex h-9 w-9 items-center justify-center rounded-md bg-accent/15 text-accent">
          <IconLeaf size={18} />
        </span>
        <span className="leading-tight">
          <span className="block font-serif text-[15px] tracking-tight">AgriVardhak</span>
          <span className="block text-[9px] font-medium uppercase tracking-[0.15em] text-sidebar-foreground/40">
            FPO Console
          </span>
        </span>
      </Link>

      <nav className="flex-1 space-y-6 px-3 py-2">
        {NAV_GROUPS.map((group, i) => (
          <div key={group.label ?? `group-${i}`} className="space-y-0.5">
            {group.label && <p className="nav-group-label mb-2">{labels[group.label]}</p>}
            {group.items.map((item) => {
              const active =
                pathname === item.href || pathname.startsWith(`${item.href}/`);
              const Glyph = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`nav-item ${active ? "nav-item-active" : ""}`}
                >
                  <Glyph size={16} />
                  {labels[item.labelKey]}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      {/*
       * The invariant, stated where staff see it every day rather than in a doc nobody
       * opens. INV-1 is the product's central promise; a console that never mentions it
       * trains people to expect the software to act on its own.
       */}
      <p className="border-t border-sidebar-foreground/10 px-5 py-4 text-[11px] leading-relaxed text-sidebar-foreground/35">
        AgriVardhak recommends.
        <br />A human approves before anything executes.
      </p>
    </aside>
  );
}

/**
 * The same nav, horizontally, for narrow screens where a 260px spine would eat the page.
 */
export function MobileNav({ labels }: { labels: NavLabels }) {
  const pathname = usePathname();
  const items = NAV_GROUPS.flatMap((g) => g.items);

  return (
    <nav className="flex gap-1 overflow-x-auto bg-sidebar px-3 py-2 md:hidden">
      {items.map((item) => {
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={`nav-item shrink-0 ${active ? "nav-item-active" : ""}`}
          >
            {labels[item.labelKey]}
          </Link>
        );
      })}
    </nav>
  );
}
