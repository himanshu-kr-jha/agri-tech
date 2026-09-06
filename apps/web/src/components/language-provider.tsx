"use client";

import { createContext, useContext, useEffect, useTransition, useState } from "react";
import { setLocale } from "@/app/actions/locale";
import { translator } from "@/lib/i18n";
import { interfaceCopy } from "@/lib/ui-copy";
import type { Locale } from "@/lib/locale";

type LanguageState = {
  locale: Locale;
  changeLanguage: (locale: Locale) => void;
  pending: boolean;
  error: boolean;
};

const LanguageContext = createContext<LanguageState | null>(null);

export function LanguageProvider({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState(false);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  function changeLanguage(next: Locale) {
    if (next === locale || pending) return;
    setError(false);
    startTransition(async () => {
      try {
        // The action returns the translated RSC tree and the persistent cookie together.
        // Keeping the old tree until then avoids mixing two languages during a transition.
        await setLocale(next);
      } catch {
        setError(true);
      }
    });
  }

  return <LanguageContext.Provider value={{ locale, changeLanguage, pending, error }}>{children}</LanguageContext.Provider>;
}

export function useTranslation() {
  const context = useContext(LanguageContext);
  if (!context) throw new Error("useTranslation requires LanguageProvider");
  return { ...context, t: translator(context.locale), copy: interfaceCopy(context.locale) };
}
