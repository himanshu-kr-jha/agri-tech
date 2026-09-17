"use client";

import { usePageTranslation } from "@/components/page-translator";
import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { setLocale } from "@/app/actions/locale";
import type { Locale } from "@/lib/locale";

/**
 * The language switch — one component, top right of every screen (UI-11).
 *
 * Shows the language you would get by pressing it, not the one you are in — a control
 * labelled "English" while the page is already English reads as a status, and people press
 * it expecting nothing to happen.
 *
 * `translate="no"`: the label is already written in the language it names, and the page
 * translator must not turn "हिन्दी" into "Hindi".
 *
 * While strings are being fetched the old text stays on screen and the button shows a quiet
 * pulse. If some strings could not be translated, a small retry appears beside it rather than
 * an error: the page is still fully usable in its source language.
 */
export function LanguageToggle() {
  const { locale, status, switchTo, retry } = usePageTranslation();
  const next = locale === "en" ? "hi" : "en";

  return (
    <span translate="no" className="inline-flex items-center gap-1.5">
      {status.failed > 0 && !status.busy && (
        <button
          type="button"
          onClick={retry}
          aria-label={locale === "en" ? "Retry translation" : "अनुवाद फिर से करें"}
          className="px-1 text-sm text-muted-foreground transition-colors hover:text-accent"
        >
          ↻
        </button>
      )}
      <button
        type="button"
        aria-label={locale === "en" ? "Switch to Hindi" : "अंग्रेज़ी में देखें"}
        aria-busy={status.busy}
        onClick={() => switchTo(next)}
        className={`border border-border px-2.5 py-1 text-sm text-muted-foreground transition-colors hover:border-accent hover:text-accent ${
          status.busy ? "animate-pulse" : ""
        }`}
      >
        {locale === "en" ? "हिन्दी" : "English"}
      </button>
    </span>
  );
}
