/**
 * FPO console shell — nav, and the guard that decides who may be here.
 *
 * The redirect is a *convenience*, not the security boundary. Every one of these screens
 * fetches through the API, which refuses a farmer token with 403 whatever the browser did to
 * get here. Sending them to their own view instead of showing an error is simply the more
 * useful behaviour for someone who typed the wrong URL.
 */

import Link from "next/link";
import { redirect } from "next/navigation";

import { SignOutButton } from "@/components/sign-out";
import { currentUser, homeFor } from "@/lib/session";

const NAV = [
  { href: "/assistant", label: "Ask" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/decisions", label: "Decisions" },
  { href: "/risk", label: "Risk" },
  { href: "/market", label: "Market" },
  { href: "/farmers", label: "Farmers" },
  { href: "/impact", label: "Impact" },
];

export default async function FpoLayout({ children }: { children: React.ReactNode }) {
  const user = await currentUser();
  if (!user) redirect("/login");
  if (user.audience !== "FPO") redirect(homeFor(user));

  return (
    <div className="min-h-screen font-sans">
      <header className="border-b border-neutral-200 dark:border-neutral-800">
        <nav className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-2 px-6 py-3 text-sm">
          <Link href="/dashboard" className="font-semibold tracking-tight">
            AgriVardhak
          </Link>
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="text-neutral-600 underline-offset-4 hover:underline dark:text-neutral-400"
            >
              {item.label}
            </Link>
          ))}
          <div className="ml-auto flex items-center gap-3">
            <span className="text-xs text-neutral-500">{user.display_name}</span>
            <SignOutButton />
          </div>
        </nav>
      </header>
      {children}
    </div>
  );
}
