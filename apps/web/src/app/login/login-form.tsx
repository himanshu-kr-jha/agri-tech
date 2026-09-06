"use client";

import type { StringKey } from "@/lib/i18n";
import { useTranslation } from "@/components/language-provider";
import { recordText } from "@/lib/localized-data";
import type { Locale } from "@/lib/locale";

import { useState } from "react";
import { useRouter } from "next/navigation";

export interface DemoAccount {
  username: string;
  password: string;
  display_name: string;
  roles: string[];
  audience: string;
  description: string;
}

const AUDIENCE_KEY = {
  FPO: "login.audience.fpo",
  FARMER: "login.audience.farmer",
} as const satisfies Record<string, StringKey>;

export function LoginForm({ accounts }: { accounts: DemoAccount[]; locale: Locale }) {
  const { t, copy, locale } = useTranslation();
  const router = useRouter();
  const [username, setUsername] = useState(accounts[0]?.username ?? "");
  const [password, setPassword] = useState(accounts[0]?.password ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!username.trim() || !password) {
      setError("required");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(res.status === 401 ? "credentials" : "failed");
        return;
      }
      // Where you land is decided by the API's `audience`, not by this form. One authority
      // for "who is this", so the console and the farmer view cannot disagree about it.
      router.replace(body.user?.audience === "FARMER" ? "/today" : "/dashboard");
      router.refresh();
    } catch {
      setError("network");
    } finally {
      setBusy(false);
    }
  }

  const field =
    "mt-1.5 w-full rounded-md border border-border/70 bg-card px-3 py-2.5 text-sm text-foreground transition-colors placeholder:text-muted-foreground/50 focus:border-primary/30";

  return (
    <>
      <form onSubmit={submit} noValidate className="space-y-5">
        <label className="block">
          <span className="eyebrow-sm">{t("login.username")}</span>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
            className={field}
          />
        </label>
        <label className="block">
          <span className="eyebrow-sm">{t("login.password")}</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
            className={field}
          />
        </label>

        {error && (
          <p
            role="alert"
            className="rounded-md border border-destructive/25 bg-destructive/[0.04] p-3 text-sm text-destructive"
          >
            {error === "required" ? copy("Enter your username and password.") : error === "credentials" ? copy("Incorrect username or password.") : error === "network" ? t("login.failed") : copy("Sign-in failed.")}
          </p>
        )}

        <button type="submit" disabled={busy} className="btn-primary w-full py-2.5">
          {busy ? t("login.signingIn") : t("login.signIn")}
        </button>
      </form>

      {accounts.length > 0 && (
        <section className="mt-10">
          <p className="eyebrow-sm">{t("login.accounts")}</p>
          <p className="mb-4 mt-1.5 text-xs leading-relaxed text-muted-foreground">
            {t("login.accountsHint")}
          </p>
          <ul className="space-y-2.5">
            {accounts.map((account) => {
              const selected = username === account.username;
              return (
                <li key={account.username}>
                  <button
                    type="button"
                    onClick={() => {
                      setUsername(account.username);
                      setPassword(account.password);
                      setError(null);
                    }}
                    aria-pressed={selected}
                    className={`w-full rounded-md border bg-card p-4 text-left transition-colors ${
                      selected
                        ? "border-primary/40 shadow-[inset_2px_0_0_0_hsl(var(--accent))]"
                        : "border-border/70 hover:border-primary/25"
                    }`}
                  >
                    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                      <span className="font-serif text-[15px] tracking-tight text-primary">
                        {account.display_name}
                      </span>
                      <span className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                        {account.audience in AUDIENCE_KEY
                          ? t(AUDIENCE_KEY[account.audience as keyof typeof AUDIENCE_KEY])
                          : account.audience}
                      </span>
                    </div>
                    <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
                      {recordText(account.description, locale)}
                    </p>
                    <p className="mt-2 font-mono text-[11px] text-muted-foreground/80">
                      {account.username} · {account.password}
                    </p>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </>
  );
}
