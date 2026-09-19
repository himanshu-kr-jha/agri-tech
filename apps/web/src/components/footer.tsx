/**
 * The site-wide footer — rendered on every page: the public pages (landing, login, privacy,
 * FAQ, about, terms) via their own JSX, and the FPO console / farmer portal via their
 * route-group layouts (`(fpo)/layout.tsx`, `(farmer)/layout.tsx`), so every screen ends in
 * the same place.
 *
 * The sitemap column and the legal bar deliberately carry different links: sitemap is
 * wayfinding (Home, Sign in, FAQ, About us), the legal bar is the two documents a visitor
 * looks for at the very bottom of any site (Privacy Policy, Terms of Use) — Privacy Policy
 * lives at `/privacy` either way, it just moved rows.
 *
 * Full-bleed sage green (`--footer`, globals.css), structured as brand + sitemap + contact
 * columns and a legal bar underneath. Breaks out of its container with the
 * `left-1/2 / -translate-x-1/2 / w-screen` trick so the colour runs edge to edge without
 * every page needing its own full-width wrapper — this only resolves correctly when the
 * footer's parent is itself full viewport width or centered in the viewport, which is why
 * the FPO layout renders the fixed-position sidebar out of flow and the footer as an
 * unindented sibling, rather than nesting either inside the (narrower, offset) content column.
 * That's also why `(fpo)/layout.tsx` passes `sidebarOffset` — see the constant below.
 *
 * `flex-1`: every call site wraps this in a `flex min-h-screen flex-col` column, and none of
 * those columns' other children carry their own `flex-1` any more — so on a short page the
 * footer is what grows to reach the bottom of the viewport (more green, not blank paper
 * below it), rather than the content area stretching to push a shorter footer down. The
 * footer itself is also a flex column with its content bottom-anchored (`justify-end`), so
 * any extra height that growth adds shows up as breathing room above the content — which
 * keeps the legal line flush against the true bottom of the page at a fixed `pb-5`, the same
 * distance the FPO console's sidebar keeps its own bottom note from that same edge (see
 * `sidebar.tsx`), so the two lines land level with each other whenever both are on screen.
 */

import Link from "next/link";

import { FooterFeedbackForm } from "@/components/footer-feedback-form";
import { IconLeaf } from "@/components/icons";
import { translator } from "@/lib/i18n";
import { currentLocale } from "@/lib/locale";

const CONTACT_EMAIL = "agritechbuzz@gmail.com";

// The FPO console's sidebar is `fixed left-0 w-[260px]` and always paints over whatever is
// behind it (sidebar.tsx) — including this footer, since it renders as a full-bleed sibling
// rather than inside the sidebar layout's own `md:pl-[260px]` column. Centering the content
// on the full window width (as the public pages do) would put the left column half-hidden
// behind the sidebar at ordinary laptop widths, so the FPO layout opts into a fixed left
// inset instead of the `mx-auto` max-width treatment.
const SIDEBAR_INSET = "px-6 md:pl-[292px] md:pr-10";
const CENTERED = "mx-auto max-w-7xl px-6 md:px-10";

export async function Footer({ sidebarOffset = false }: { sidebarOffset?: boolean } = {}) {
  const locale = await currentLocale();
  const t = translator(locale);
  const year = new Date().getFullYear();
  const containerWidth = sidebarOffset ? SIDEBAR_INSET : CENTERED;

  return (
    <footer className="relative left-1/2 flex w-screen flex-1 -translate-x-1/2 flex-col justify-end bg-footer text-footer-foreground">
      <div className={`w-full pt-8 md:pt-10 ${containerWidth}`}>
        <div className="grid gap-8 md:grid-cols-[1.1fr_0.8fr_0.9fr_1.1fr] md:gap-14">
          <div>
            <Link href="/" className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-md bg-accent/15 text-accent">
                <IconLeaf size={18} />
              </span>
              <span translate="no" className="font-serif text-lg text-footer-foreground">
                AgriVardhak
              </span>
            </Link>
            <p className="mt-4 max-w-xs text-sm leading-relaxed text-footer-muted">
              {t("footer.tagline")}
            </p>
          </div>

          <div>
            <p className="eyebrow-sm text-footer-muted">{t("footer.sitemapTitle")}</p>
            <nav className="mt-4 flex flex-col gap-2.5 text-sm">
              <Link href="/" className="text-footer-foreground/85 hover:text-footer-foreground">
                {t("footer.home")}
              </Link>
              <Link
                href="/login"
                className="text-footer-foreground/85 hover:text-footer-foreground"
              >
                {t("footer.signIn")}
              </Link>
              <Link href="/faq" className="text-footer-foreground/85 hover:text-footer-foreground">
                {t("footer.faq")}
              </Link>
              <Link
                href="/about"
                className="text-footer-foreground/85 hover:text-footer-foreground"
              >
                {t("footer.aboutUs")}
              </Link>
            </nav>
          </div>

          <div>
            <p className="eyebrow-sm text-footer-muted">{t("footer.contactTitle")}</p>
            <p className="mt-4 text-sm leading-relaxed text-footer-muted">
              {t("footer.contactBody")}
            </p>
            <a
              href={`mailto:${CONTACT_EMAIL}`}
              className="mt-2 inline-block text-sm text-footer-foreground underline decoration-footer-muted/50 underline-offset-4 hover:text-footer-foreground/90"
            >
              {CONTACT_EMAIL}
            </a>
          </div>

          <div>
            <FooterFeedbackForm locale={locale} />
          </div>
        </div>
      </div>

      {/*
       * Full-bleed divider — deliberately not confined to the column above it, so it runs
       * edge to edge the way the sidebar's own divider runs edge to edge of the console
       * spine. On the FPO console the sidebar sits on top of its left ~260px, so what reads
       * on screen is the two dividers meeting at the sidebar's right edge as one continuous
       * line across the page.
       */}
      <div className="mt-8 border-t border-footer-border/60">
        <div
          className={`flex w-full flex-col gap-3 py-5 text-xs text-footer-muted md:flex-row md:items-center md:justify-between ${containerWidth}`}
        >
          <p>
            © {year} <span translate="no">AgriVardhak</span>. {t("footer.rightsReserved")}
          </p>
          <div className="flex items-center gap-4">
            <Link href="/privacy" className="hover:text-footer-foreground">
              {t("footer.privacyPolicy")}
            </Link>
            <Link href="/terms" className="hover:text-footer-foreground">
              {t("footer.termsOfUse")}
            </Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
