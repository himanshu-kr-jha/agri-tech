/**
 * The public site's header (ADR-0024).
 *
 * Every page outside the login gate wears this: the landing page, About us, the FAQ, the
 * two legal documents and the sign-in screen. Before it existed, each of those six pages
 * hand-rolled its own logo-and-language-toggle row, which is why five of them had no way
 * to reach the other four.
 *
 * Server component. It reads the locale cookie and resolves every label here, then hands
 * the already-translated strings to `PublicNav`, which is client-side only because it needs
 * `usePathname`. Chrome rendered this way costs no translation call at all (ADR-0023) —
 * the reader gets Hindi from the dictionary, on the server, in the first byte.
 *
 * Sticky rather than fixed: the hero below it is full-bleed video, and a fixed header would
 * need the page to carry a top offset that nothing else in the app carries. `relative` on
 * the element is load-bearing — the mobile menu panel positions against it.
 */

import Link from "next/link";

import { IconLeaf } from "@/components/icons";
import { LanguageToggle } from "@/components/language-toggle";
import { PublicNav, type NavLink } from "@/components/public-nav";
import { translator } from "@/lib/i18n";
import { currentLocale } from "@/lib/locale";

export async function PublicHeader() {
  const t = translator(await currentLocale());

  const links: NavLink[] = [
    { href: "/", label: t("publicNav.home") },
    { href: "/about", label: t("publicNav.about") },
    { href: "/privacy", label: t("publicNav.privacy") },
    { href: "/faq", label: t("publicNav.faq") },
  ];

  return (
    <header className="relative z-50 border-b border-border/70 bg-background/85 backdrop-blur">
      <div className="mx-auto flex h-16 w-full max-w-7xl items-center gap-3 px-6 md:px-10">
        <Link href="/" className="flex items-center gap-2.5" aria-label={t("publicNav.home")}>
          <span className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <IconLeaf size={17} />
          </span>
          {/* The wordmark is a name, not copy. Without `translate="no"` the runtime DOM
              translator would happily transliterate it into Devanagari. */}
          <span
            translate="no"
            className="font-serif text-[17px] tracking-tight text-primary [font-optical-sizing:auto]"
          >
            AgriVardhak
          </span>
        </Link>

        <div className="ml-auto flex items-center gap-2">
          <PublicNav
            links={links}
            openLabel={t("publicNav.openMenu")}
            closeLabel={t("publicNav.closeMenu")}
          />
          <LanguageToggle />
          <Link href="/login" className="btn-primary px-4 py-2">
            {t("publicNav.signIn")}
          </Link>
        </div>
      </div>
    </header>
  );
}
