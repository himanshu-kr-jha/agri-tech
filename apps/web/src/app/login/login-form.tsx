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

  return (
    <>
      <form onSubmit={submit} className="space-y-4">
        <label className="block">
          <span className="text-sm text-neutral-600 dark:text-neutral-400">Username</span>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
            className="mt-1 w-full rounded-lg border border-neutral-300 px-3 py-2 dark:border-neutral-700 dark:bg-neutral-900"
          />
        </label>
        <label className="block">
          <span className="text-sm text-neutral-600 dark:text-neutral-400">Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
            className="mt-1 w-full rounded-lg border border-neutral-300 px-3 py-2 dark:border-neutral-700 dark:bg-neutral-900"
          />
        </label>

        {error && (
          <p
            role="alert"
            className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200"
          >
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-neutral-900 px-4 py-2.5 font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>

      {accounts.length > 0 && (
        <section className="mt-8">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
            Demo accounts
          </h2>
          <p className="mb-3 mt-1 text-xs text-neutral-500">
            Sign in as each to see the same system from both sides. What a member can reach is
            enforced by the API, not by hiding pages.
          </p>
          <ul className="space-y-2">
            {accounts.map((account) => (
              <li key={account.username}>
                <button
                  type="button"
                  onClick={() => {
                    setUsername(account.username);
                    setPassword(account.password);
                    setError(null);
                  }}
                  className={`w-full rounded-xl border p-3 text-left transition-colors hover:border-neutral-400 dark:hover:border-neutral-500 ${
                    username === account.username
                      ? "border-neutral-900 dark:border-neutral-100"
                      : "border-neutral-200 dark:border-neutral-800"
                  }`}
                >
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span className="font-medium">{account.display_name}</span>
                    <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-xs text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400">
                      {AUDIENCE_LABEL[account.audience] ?? account.audience}
                    </span>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-neutral-600 dark:text-neutral-400">
                    {account.description}
                  </p>
                  <p className="mt-1.5 font-mono text-xs text-neutral-500">
                    {account.username} · {account.password}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
