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
 *
 * `fixed inset-y-0 left-0` rather than a normal flex-row sibling: it stays put — never
 * scrolls with page content — and, being fixed rather than sticky, keeps rendering on top of
 * whatever is behind it at any scroll position, including the footer once a page is short
 * enough (or scrolled far enough) for the footer to reach that screen region. The content
 * column carries `md:pl-[260px]` to stay clear of it; the footer deliberately does not, so
 * the menu overlaps its left edge rather than being pushed aside by it.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

import type { StringKey } from "@/lib/i18n";
import { translator } from "@/lib/i18n";
import type { Locale } from "@/lib/locale";
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

type NavItem = { href: string; label: StringKey; icon: typeof IconAsk };

/**
 * Grouped the way the work is actually sequenced: you ask, you decide, then you look at
 * what the collective is made of. Not alphabetically, and not by which screen was built first.
 *
 * Labels are dictionary keys, not strings: this is static chrome, so it renders in the
 * reader's language on the server and never costs a translation call (ADR-0023).
 */
const NAV_GROUPS: { label: StringKey | null; items: NavItem[] }[] = [
  {
    label: null,
    items: [{ href: "/dashboard", label: "nav.dashboard", icon: IconDashboard }],
  },
  {
    label: "nav.group.decide",
    items: [
      { href: "/assistant", label: "nav.ask", icon: IconAsk },
      { href: "/decisions", label: "nav.decisions", icon: IconDecisions },
      { href: "/risk", label: "nav.risk", icon: IconRisk },
    ],
  },
  {
    label: "nav.group.collective",
    items: [
      { href: "/farmers", label: "nav.farmers", icon: IconFarmers },
      { href: "/market", label: "nav.market", icon: IconMarket },
      { href: "/discrepancies", label: "nav.conflicts", icon: IconAlert },
      { href: "/knowledge", label: "nav.published", icon: IconDatabase },
      { href: "/impact", label: "nav.impact", icon: IconImpact },
    ],
  },
];

export function Sidebar({ locale }: { locale: Locale }) {
  const pathname = usePathname();
  const t = translator(locale);

  return (
    <aside className="fixed inset-y-0 left-0 z-50 hidden w-[260px] flex-col bg-sidebar text-sidebar-foreground md:flex">
      <Link
        href="/dashboard"
        className="flex items-center gap-3 px-5 py-5 transition-opacity hover:opacity-90"
      >
        <span className="flex h-9 w-9 items-center justify-center rounded-md bg-accent/15 text-accent">
          <IconLeaf size={18} />
        </span>
        <span className="leading-tight">
          <span translate="no" className="block font-serif text-[15px] tracking-tight">
            AgriVardhak
          </span>
          <span className="block text-[9px] font-medium uppercase tracking-[0.15em] text-sidebar-foreground/40">
            {t("console.label")}
          </span>
        </span>
      </Link>

      <nav className="flex-1 space-y-6 px-3 py-2">
        {NAV_GROUPS.map((group, i) => (
          <div key={group.label ?? `group-${i}`} className="space-y-0.5">
            {group.label && <p className="nav-group-label mb-2">{t(group.label)}</p>}
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
                  {t(item.label)}
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
       *
       * Styled off the footer's own tokens (`footer-border`/`footer-muted`), not the
       * sidebar's, with the same `text-xs` size and `pb-5` bottom padding as the footer's
       * legal line, and no forced line break (that's what let it run to three lines and
       * pushed its top divider noticeably higher than the footer's) — the sidebar and footer
       * now share one background colour and sit flush against the same bottom edge, so both
       * the text and the divider above it land level with their footer counterparts.
       */}
      <p className="border-t border-footer-border/60 px-5 pb-5 pt-1 text-xs leading-snug text-footer-muted">
        {t("console.recommends")} {t("console.humanApproves")}
      </p>
    </aside>
  );
}

/**
 * The same nav, horizontally, for narrow screens where a 260px spine would eat the page.
 */
export function MobileNav({ locale }: { locale: Locale }) {
  const pathname = usePathname();
  const t = translator(locale);
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
            {t(item.label)}
          </Link>
        );
      })}
    </nav>
  );
}
