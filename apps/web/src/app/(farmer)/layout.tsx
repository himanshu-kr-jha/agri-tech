/**
 * Farmer portal shell — UI-05, INV-5.
 *
 * A separate route group from the FPO console, and separately guarded. The separation is not
 * decoration: no page in this tree renders organization-internal data, so the information
 * boundary cannot be crossed by a routing mistake. The API refuses anyway.
 *
 * Larger type and fewer words than the console. This is read on a phone, outdoors, often by
 * someone for whom Hindi is the first language and text is not the easiest channel — which
 * is why this tree gets none of the console's sidebar, density, or micro-caps labelling.
 * It shares the palette and the serif; it does not share the information architecture.
 */

import Link from "next/link";
import { redirect } from "next/navigation";

import { IconLeaf } from "@/components/icons";
import { LanguageToggle } from "@/components/language-toggle";
import { SignOutButton } from "@/components/sign-out";
import { translator } from "@/lib/i18n";
import { currentLocale } from "@/lib/locale";
import { currentUser, homeFor } from "@/lib/session";

export default async function FarmerLayout({ children }: { children: React.ReactNode }) {
  const user = await currentUser();
  if (!user) redirect("/login");
  if (user.audience !== "FARMER") redirect(homeFor(user));

  const locale = await currentLocale();
  const t = translator(locale);

  return (
    <div className="flex min-h-screen flex-col text-[17px]">
      <header className="sticky top-0 z-40 border-b border-border/70 bg-background/85 backdrop-blur">
        <nav className="mx-auto flex max-w-2xl flex-wrap items-center gap-3 px-5 py-3.5">
          <Link href="/today" className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <IconLeaf size={16} />
            </span>
            <span className="font-serif text-[17px] tracking-tight text-primary">
              {locale === "hi" ? "कृषिवर्धक" : "AgriVardhak"}
            </span>
          </Link>
          <span className="text-sm text-muted-foreground">{t("nav.myFarm")}</span>
          <Link
            href="/ask"
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            {t("nav.ask")}
          </Link>
          <Link
            href="/schemes"
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            {t("nav.notices")}
          </Link>
          <div className="ml-auto flex items-center gap-2">
            <LanguageToggle locale={locale} label={t("lang.switchTo")} />
            <SignOutButton label={t("nav.signOut")} />
          </div>
        </nav>
      </header>
      <div className="flex-1">{children}</div>
    </div>
  );
}
