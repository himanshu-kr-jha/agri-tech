"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { setLocale } from "@/app/actions/locale";
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
export function LanguageToggle({ locale, label }: { locale: Locale; label: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const next: Locale = locale === "en" ? "hi" : "en";

  return (
    <button
      type="button"
      aria-label={locale === "en" ? "Switch to Hindi" : "Switch to English"}
      aria-busy={pending}
      disabled={pending}
      onClick={() =>
        startTransition(async () => {
          await setLocale(next);
          router.refresh();
        })
      }
      className="border border-border px-2.5 py-1 text-sm text-muted-foreground transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
    >
      {label}
    </button>
  );
}
