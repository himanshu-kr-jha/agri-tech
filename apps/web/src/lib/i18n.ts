/**
 * The static dictionary — interface chrome, written by hand in both languages (ADR-0023).
 *
 * This is the *stored* half of translation. Nav, headers, labels and fixed sentences live in
 * `strings.json` so they render in the reader's language on the server, before any script
 * runs, and cost no API call. Everything else on a page — API data, assistant answers, crop
 * names, console screens nobody wrote Hindi for — is translated on demand by the page
 * translator (`lib/dom-translate.ts`) through Sarvam, and remembered in the API's
 * translation memory.
 *
 * The same JSON seeds that memory as `HUMAN` rows (`make i18n-seed`), which is how a
 * hand-written Hindi label keeps beating a machine rendering of the same English.
 *
 * Keys are dotted and grouped by surface. `StringKey` is derived from the JSON, so a key
 * that does not exist is still a compile error.
 */

import type { Locale } from "@/lib/locale";

import strings from "./strings.json";

type Entry = { en: string; hi: string };

export const STRINGS: Record<keyof typeof strings, Entry> = strings;

export type StringKey = keyof typeof strings;

/** Bind a locale once, at the top of a component, and pass `t` down. */
export function translator(locale: Locale): (key: StringKey) => string {
  return (key) => STRINGS[key][locale];
}

/** The five canned searches on the notices page, in the reader's language. */
export const NOTICE_SUGGESTIONS: Entry[] = [
  STRINGS["notices.suggest.insurance"],
  STRINGS["notices.suggest.soil"],
  STRINGS["notices.suggest.fertiliser"],
  STRINGS["notices.suggest.irrigation"],
  STRINGS["notices.suggest.seed"],
];

/** Collapse whitespace — the same normalisation the API hashes on. */
export function normaliseText(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

/**
 * The dictionary as two lookups, keyed by normalised text: English → Hindi and Hindi →
 * English. The page translator checks these before its cache and before the network.
 */
export function dictionaryLookups(): { toHindi: Map<string, string>; toEnglish: Map<string, string> } {
  const toHindi = new Map<string, string>();
  const toEnglish = new Map<string, string>();
  for (const entry of Object.values(STRINGS)) {
    const en = normaliseText(entry.en);
    const hi = normaliseText(entry.hi);
    if (en && hi) {
      if (!toHindi.has(en)) toHindi.set(en, entry.hi);
      if (!toEnglish.has(hi)) toEnglish.set(hi, entry.en);
    }
  }
  return { toHindi, toEnglish };
}
