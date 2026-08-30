/**
 * Which language the interface is rendered in.
 *
 * A cookie rather than a URL segment or client state, because every page in the farmer tree
 * is a Server Component: the language has to be known before the HTML is built, or the first
 * paint is in the wrong language and corrects itself, which is worse than being slow. A
 * cookie is the only one of the three that is readable on the server *and* survives a reload.
 *
 * This governs interface text only. It does not translate anything — the Hindi strings are
 * written by hand in `i18n.ts`, and the published Hindi of a government order is data, never
 * a string in that table (ADR-0015).
 */

import { cookies } from "next/headers";

export type Locale = "en" | "hi";

export const LOCALE_COOKIE = "agri_locale";

/**
 * English by default. The farmer tree used to lead in Hindi on every line with an English
 * gloss beside it; a reader who wants that now toggles to it once and the choice sticks for
 * a year.
 */
export const DEFAULT_LOCALE: Locale = "en";

export function isLocale(value: string | undefined): value is Locale {
  return value === "en" || value === "hi";
}

export async function currentLocale(): Promise<Locale> {
  const jar = await cookies();
  const value = jar.get(LOCALE_COOKIE)?.value;
  return isLocale(value) ? value : DEFAULT_LOCALE;
}
