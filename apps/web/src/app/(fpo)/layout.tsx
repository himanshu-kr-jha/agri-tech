/**
 * FPO console shell — nav, and the guard that decides who may be here.
 *
 * The redirect is a *convenience*, not the security boundary. Every one of these screens
 * fetches through the API, which refuses a farmer token with 403 whatever the browser did to
 * get here. Sending them to their own view instead of showing an error is simply the more
 * useful behaviour for someone who typed the wrong URL.
 *
 * The header reads the organization from the dashboard endpoint and shrugs if it cannot —
 * a console that fails to render because the identity strip is missing would be a worse
 * failure than a header that says "AgriVardhak" for one page load.
 */

import { redirect } from "next/navigation";

import { LanguageToggle } from "@/components/language-toggle";
import { MobileNav, Sidebar, type NavLabels } from "@/components/sidebar";
import { SignOutButton } from "@/components/sign-out";
import { IconBell, IconSearch } from "@/components/icons";
import { formatRole } from "@/components/invariants";
import { api } from "@/lib/api";
import { translator } from "@/lib/i18n";
import { currentLocale } from "@/lib/locale";
import { currentUser, homeFor } from "@/lib/session";

/** "Ramesh Prajapati" → "RP". Two letters, because three is a logo and one is ambiguous. */
function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export default async function FpoLayout({ children }: { children: React.ReactNode }) {
  const locale = await currentLocale();
  const t = translator(locale);
  // The sidebar is a client component and cannot read the locale cookie, so the shell
  // resolves its strings here. Listed rather than mapped so a missing key is a type error.
  const nav: NavLabels = {
    "con.nav.dashboard": t("con.nav.dashboard"),
    "con.nav.assistant": t("con.nav.assistant"),
    "con.nav.decisions": t("con.nav.decisions"),
    "con.nav.risk": t("con.nav.risk"),
    "con.nav.farmers": t("con.nav.farmers"),
    "con.nav.market": t("con.nav.market"),
    "con.nav.discrepancies": t("con.nav.discrepancies"),
    "con.nav.knowledge": t("con.nav.knowledge"),
    "con.nav.impact": t("con.nav.impact"),
    "con.nav.group.decide": t("con.nav.group.decide"),
    "con.nav.group.collective": t("con.nav.group.collective"),
  };

  const user = await currentUser();
  if (!user) redirect("/login");
  if (user.audience !== "FPO") redirect(homeFor(user));

  const organization = await api
    .dashboard()
    .then((d) => d.organization)
    .catch(() => null);

  const role = user.roles[0] ? formatRole(user.roles[0]) : "Member";

  return (
    <div className="flex min-h-screen">
      <Sidebar labels={nav} />

      <div className="flex min-w-0 flex-1 flex-col">
        <MobileNav labels={nav} />

        <header className="sticky top-0 z-40 border-b border-border/70 bg-background/85 backdrop-blur">
          <div className="flex h-16 items-center gap-6 px-6">
            <div className="min-w-0">
              <div className="flex flex-wrap items-baseline gap-x-3">
                <span className="truncate font-serif text-[17px] tracking-tight text-primary">
                  {organization?.name ?? "AgriVardhak"}
                </span>
                {organization && (
                  <span className="text-xs text-muted-foreground">
                    {organization.district}, {organization.state}
                  </span>
                )}
              </div>
              {organization && (
                <p className="mt-0.5 text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
                  {organization.type}
                </p>
              )}
            </div>

            {/*
             * Presentational for now: search is not built, and a box that does nothing when
             * you type in it is worse than one that says so. It carries the header's
             * proportions until the real thing lands.
             */}
            <div className="ml-auto hidden items-center gap-2 rounded-full border border-border/60 bg-card px-4 py-2 text-sm text-muted-foreground/60 lg:flex lg:w-72">
              <IconSearch size={15} />
              <span className="truncate">Search farmers, decisions, lots…</span>
            </div>

            <div className="flex items-center gap-4">
              <span className="text-muted-foreground/60">
                <IconBell size={17} />
              </span>
              <div className="flex items-center gap-2.5">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-[11px] font-medium text-primary-foreground">
                  {initials(user.display_name)}
                </span>
                <span className="hidden leading-tight sm:block">
                  <span className="block text-[13px] text-foreground">{user.display_name}</span>
                  <span className="block text-[11px] text-muted-foreground">{role}</span>
                </span>
              </div>
              <LanguageToggle locale={locale} label={t("lang.switchTo")} />
              <SignOutButton />
            </div>
          </div>
        </header>

        <div className="flex-1">{children}</div>
      </div>
    </div>
  );
}
