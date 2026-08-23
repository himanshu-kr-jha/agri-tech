"use client";

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

const AUDIENCE_LABEL: Record<string, string> = {
  FPO: "Organization console",
  FARMER: "Farmer view",
};

export function LoginForm({ accounts }: { accounts: DemoAccount[] }) {
  const router = useRouter();
  const [username, setUsername] = useState(accounts[0]?.username ?? "");
  const [password, setPassword] = useState(accounts[0]?.password ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
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
        setError(body.detail ?? "Sign-in failed.");
        return;
      }
      // Where you land is decided by the API's `audience`, not by this form. One authority
      // for "who is this", so the console and the farmer view cannot disagree about it.
      router.replace(body.user?.audience === "FARMER" ? "/today" : "/dashboard");
      router.refresh();
    } catch {
      setError("Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  const field =
    "mt-1.5 w-full rounded-md border border-border/70 bg-card px-3 py-2.5 text-sm text-foreground transition-colors placeholder:text-muted-foreground/50 focus:border-primary/30";

  return (
    <>
      <form onSubmit={submit} className="space-y-5">
        <label className="block">
          <span className="eyebrow-sm">Username</span>
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
          <span className="eyebrow-sm">Password</span>
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
            {error}
          </p>
        )}

        <button type="submit" disabled={busy} className="btn-primary w-full py-2.5">
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>

      {accounts.length > 0 && (
        <section className="mt-10">
          <p className="eyebrow-sm">Demo accounts</p>
          <p className="mb-4 mt-1.5 text-xs leading-relaxed text-muted-foreground">
            Sign in as each to see the same system from both sides. What a member can reach is
            enforced by the API, not by hiding pages.
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
                        {AUDIENCE_LABEL[account.audience] ?? account.audience}
                      </span>
                    </div>
                    <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
                      {account.description}
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
