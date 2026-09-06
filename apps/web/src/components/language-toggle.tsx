"use client";

import { useTranslation } from "@/components/language-provider";
import type { Locale } from "@/lib/locale";

/**
 * The language switch.
 *
 * Shows the language you would get by pressing it, not the one you are in — a control
 * labelled "English" while the page is already English reads as a status, and people press
 * it expecting nothing to happen.
 *
 * **Two things here are load-bearing, and the first version had neither.**
 *
 * The transition callback is `async` and awaits the action. The original wrote
 * `startTransition(() => void setLocale(next))`, and the `void` threw away the promise: the
 * transition finished the instant the request was *sent*, so React had nothing to wait on,
 * `pending` was never true, and the tree was not re-rendered when the cookie landed. The
 * server was right the whole time — a reload showed the new language — but the click
 * appeared to do nothing, which is the bug people actually saw.
 *
 * `router.refresh()` then discards the client router cache. `revalidatePath` in the action
 * invalidates the server's copy, but every page in this tree is `force-dynamic`, and without
 * the refresh the client can still paint its cached RSC payload — the old language — until
 * the next hard navigation.
 */
export function LanguageToggle(_props: { locale?: Locale; label?: string } = {}) {
  const { locale, copy, changeLanguage, pending, error } = useTranslation();

  return (
    <div className="shrink-0">
      <div role="group" aria-label={copy("Language")} aria-busy={pending} className="inline-flex rounded-md border border-border bg-card text-card-foreground">
        {(["en", "hi"] as const).map((language) => (
          <button
            key={language}
            type="button"
            lang={language}
            aria-pressed={locale === language}
            disabled={pending}
            onClick={() => changeLanguage(language)}
            className={`min-h-9 rounded px-3 py-1.5 font-sans text-sm transition-colors disabled:cursor-wait ${locale === language ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}
          >
            {language === "en" ? "English" : "हिंदी"}
          </button>
        ))}
      </div>
      {error && <p role="alert" className="max-w-48 text-sm text-destructive">{copy("Could not change language. Please try again.")}</p>}
    </div>
  );
}
