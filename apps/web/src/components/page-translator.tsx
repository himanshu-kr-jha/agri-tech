"use client";

/**
 * Mounts the page translator once for the whole app and shares the reader's language with
 * the switch (ADR-0023, UI-11).
 *
 * Lives in the root layout, so sign-in, the farmer portal and the FPO console all get the
 * same behaviour from one place — no portal wires its own.
 *
 * Starts in an effect, i.e. after hydration. Translating before React has attached would
 * make the server HTML and the client tree disagree, and React would "fix" the page back.
 */

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

import { setLocale as persistLocale } from "@/app/actions/locale";
import {
  LANG_FOR_LOCALE,
  PageTranslator,
  TranslationCache,
  type Lang,
  type TranslatorStatus,
} from "@/lib/dom-translate";
import { dictionaryLookups } from "@/lib/i18n";
import type { Locale } from "@/lib/locale";

interface TranslationContextValue {
  locale: Locale;
  status: TranslatorStatus;
  switchTo: (next: Locale) => void;
  retry: () => void;
}

const TranslationContext = createContext<TranslationContextValue | null>(null);

/**
 * One translator per document, not per mount. React Strict Mode mounts effects twice in dev:
 * with a fresh instance each time, the first applied cached Hindi synchronously and the
 * second then recorded that Hindi as the page's *original* text, so switching back to English
 * machine-translated Hindi instead of restoring the English (measured: "2.5 t" → "2.5 ct.").
 */
let sharedTranslator: PageTranslator | null = null;
/** The mounted provider's setter; the shared instance reports through whichever is current. */
let statusListener: ((status: TranslatorStatus) => void) | null = null;

function translatorFor(locale: Locale, onStatus: (status: TranslatorStatus) => void): PageTranslator {
  if (!sharedTranslator) {
    sharedTranslator = new PageTranslator({
      root: document.body,
      target: LANG_FOR_LOCALE[locale],
      fetchTranslations,
      dictionary: dictionaryLookups(),
      cache: (sharedCache = new TranslationCache()),
      onStatus: (status) => statusListener?.(status),
    });
  }
  statusListener = onStatus;
  return sharedTranslator;
}

/** One cache per document, shared with the translator so the glossary version can reset it. */
let sharedCache: TranslationCache | null = null;

async function fetchTranslations(texts: string[], target: Lang): Promise<(string | null)[]> {
  const response = await fetch("/api/translate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target, texts }),
  });
  if (!response.ok) throw new Error(`translate failed: ${response.status}`);
  const body = (await response.json()) as {
    translations?: unknown;
    resolved?: unknown;
    corpus_version?: unknown;
  };
  if (typeof body.corpus_version === "string") sharedCache?.useCorpusVersion(body.corpus_version);
  if (!Array.isArray(body.translations)) throw new Error("translate: malformed response");
  const resolved = Array.isArray(body.resolved) ? body.resolved : [];
  return body.translations.map((t, i) =>
    typeof t === "string" && resolved[i] !== false ? t : null,
  );
}

export function TranslationProvider({
  initialLocale,
  children,
}: {
  initialLocale: Locale;
  children: React.ReactNode;
}) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);
  const [status, setStatus] = useState<TranslatorStatus>({ busy: false, failed: 0 });
  const translator = useRef<PageTranslator | null>(null);

  useEffect(() => {
    const instance = translatorFor(initialLocale, setStatus);
    translator.current = instance;
    void instance.start();
    // A page served wholly from the browser cache never sees a translate response, so it
    // would never learn the glossary changed ("मोहल्ला" stayed after Village → गाँव). Ask once;
    // if the cache was stale, re-translate what is on screen.
    void fetch("/api/translate", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((body: { corpus_version?: unknown } | null) => {
        if (typeof body?.corpus_version === "string" && sharedCache?.useCorpusVersion(body.corpus_version)) {
          void instance.refresh();
        }
      })
      .catch(() => {});
    return () => {
      instance.stop();
      translator.current = null;
    };
    // The translator is created once; later language changes go through `switchTo`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
    if (status.busy) document.documentElement.dataset.translating = "true";
    else delete document.documentElement.dataset.translating;
  }, [locale, status.busy]);

  const switchTo = useCallback((next: Locale) => {
    setLocaleState(next);
    // The cookie is for the *next* server render (reload, navigation) so static text arrives
    // in the right language. The page already on screen is translated in place, now.
    void persistLocale(next);
    void translator.current?.setTarget(LANG_FOR_LOCALE[next]);
  }, []);

  const retry = useCallback(() => {
    void translator.current?.retry();
  }, []);

  return (
    <TranslationContext.Provider value={{ locale, status, switchTo, retry }}>
      {children}
    </TranslationContext.Provider>
  );
}

export function usePageTranslation(): TranslationContextValue {
  const value = useContext(TranslationContext);
  if (!value) throw new Error("usePageTranslation must be used inside TranslationProvider");
  return value;
}
