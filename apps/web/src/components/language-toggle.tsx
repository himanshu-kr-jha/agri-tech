"use client";

import { useTransition } from "react";

import { setLocale } from "@/app/actions/locale";
import type { Locale } from "@/lib/locale";

/**
 * The language switch.
 *
 * Shows the language you would get by pressing it, not the one you are in — a control
 * labelled "English" while the page is already English reads as a status, and people press
 * it expecting nothing to happen. `useTransition` keeps the old text on screen while the
 * server rebuilds rather than flashing an empty shell.
 */
export function LanguageToggle({ locale, label }: { locale: Locale; label: string }) {
  const [pending, startTransition] = useTransition();
  const next: Locale = locale === "en" ? "hi" : "en";

  return (
    <button
      type="button"
      aria-label={locale === "en" ? "Switch to Hindi" : "अंग्रेज़ी में देखें"}
      disabled={pending}
      onClick={() => startTransition(() => void setLocale(next))}
      className="border border-border px-2.5 py-1 text-sm text-muted-foreground transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
    >
      {label}
    </button>
  );
}
