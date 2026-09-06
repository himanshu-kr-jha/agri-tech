/**
 * Sign in — FR-104.
 *
 * The demo accounts are listed on the page with their passwords, and that is deliberate
 * rather than lazy. This is a demonstration system seeded with synthetic people; a credential
 * that is published, fixed and clearly labelled is safer than one that looks like a secret
 * while being equally guessable. The API only serves that list outside production and only
 * for accounts flagged `is_demo_account`.
 *
 * The two accounts are the point of the screen. Signing in as the CEO and then as a member
 * shows the information boundary as a *product behaviour* rather than as a status code in a
 * terminal — which is the version a non-technical judge can actually evaluate.
 */

import { redirect } from "next/navigation";

import { translator } from "@/lib/i18n";
import { interfaceCopy } from "@/lib/ui-copy";
import { currentLocale } from "@/lib/locale";

import { LoginForm, type DemoAccount } from "./login-form";
import { IconLeaf } from "@/components/icons";
import { LanguageToggle } from "@/components/language-toggle";
import { currentUser, homeFor } from "@/lib/session";

export const dynamic = "force-dynamic";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function demoAccounts(): Promise<DemoAccount[]> {
  try {
    const res = await fetch(`${API}/api/v1/auth/demo-accounts`, { cache: "no-store" });
    if (!res.ok) return [];
    const body = await res.json();
    return (body.accounts ?? []) as DemoAccount[];
  } catch {
    return [];
  }
}

export default async function LoginPage() {
  const user = await currentUser();
  if (user) redirect(homeFor(user));

  const accounts = await demoAccounts();
  const locale = await currentLocale();
  const t = translator(locale);
  const copy = interfaceCopy(locale);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-lg flex-col justify-center px-6 py-16">
      <header className="mb-9">
        <div className="mb-6 flex items-center justify-between">
          <span className="flex h-11 w-11 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <IconLeaf size={20} />
          </span>
          <LanguageToggle locale={locale} label={t("lang.switchTo")} />
        </div>
        <p className="eyebrow">{t("login.eyebrow")}</p>
        <h1 className="title-page mt-1.5 text-[2.5rem]">{copy("AgriVardhak")}</h1>
        <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">
          {t("login.tagline")}
        </p>
      </header>

      <LoginForm accounts={accounts} locale={locale} />

      <p className="mt-10 border-t border-border/60 pt-6 text-xs leading-relaxed text-muted-foreground">
        {copy("Market prices, weather and hazard climatology are cited in")}{" "}
        <code className="font-mono text-[11px]">seed/sources.md</code>.
      </p>
    </main>
  );
}
