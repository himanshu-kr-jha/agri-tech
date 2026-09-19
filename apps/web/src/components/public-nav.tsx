"use client";

/**
 * The public site's navigation links.
 *
 * A client component for the same single reason `sidebar.tsx` is one: `usePathname` is the
 * only way to know which link is current. The header around it stays on the server, which
 * is why the labels arrive here already translated — `translator()` returns a function, and
 * functions do not cross the server/client boundary.
 *
 * Under `md` the links collapse behind a button rather than wrapping. Four links plus a
 * language toggle plus a sign-in button is more than a 375px bar holds, and the horizontal
 * scroller the console uses works there because the console's nav is a working tool you
 * return to — a marketing header that scrolls sideways just looks broken.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useState } from "react";

import { IconChevronDown } from "@/components/icons";

export type NavLink = { href: string; label: string };

export function PublicNav({
  links,
  openLabel,
  closeLabel,
}: {
  links: NavLink[];
  openLabel: string;
  closeLabel: string;
}) {
  const pathname = usePathname();
  const menuId = useId();

  // The menu remembers *where* it was opened rather than merely that it is open. Navigating
  // therefore closes it for free — no effect watching the pathname, and no frame in which
  // the panel sits open over the page you just asked for.
  const [openedAt, setOpenedAt] = useState<string | null>(null);
  const open = openedAt === pathname;
  const setOpen = (next: boolean) => setOpenedAt(next ? pathname : null);

  useEffect(() => {
    if (!open) return;
    // `setOpenedAt` rather than the `setOpen` wrapper: the useState setter is stable, so
    // the listener is attached once per open rather than re-attached on every render.
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpenedAt(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const isCurrent = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <>
      <nav className="hidden items-center gap-1 md:flex">
        {links.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            aria-current={isCurrent(link.href) ? "page" : undefined}
            className={`public-nav-item ${isCurrent(link.href) ? "public-nav-item-active" : ""}`}
          >
            {link.label}
          </Link>
        ))}
      </nav>

      <button
        type="button"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label={open ? closeLabel : openLabel}
        onClick={() => setOpen(!open)}
        className="public-nav-item md:hidden"
      >
        <IconChevronDown
          size={16}
          className={`transition-transform duration-150 ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open ? (
        <div
          id={menuId}
          className="absolute inset-x-0 top-full flex flex-col gap-0.5 border-b border-border/70 bg-background/95 p-3 backdrop-blur md:hidden"
        >
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              aria-current={isCurrent(link.href) ? "page" : undefined}
              className={`public-nav-item ${isCurrent(link.href) ? "public-nav-item-active" : ""}`}
            >
              {link.label}
            </Link>
          ))}
        </div>
      ) : null}
    </>
  );
}
