/** FPO console shell — shared nav for the organization-facing screens. */

import Link from "next/link";

const NAV = [
  { href: "/assistant", label: "Ask" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/decisions", label: "Decisions" },
  { href: "/risk", label: "Risk" },
  { href: "/market", label: "Market" },
  { href: "/farmers", label: "Farmers" },
  { href: "/impact", label: "Impact" },
];

export default function FpoLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen font-sans">
      <header className="border-b border-neutral-200 dark:border-neutral-800">
        <nav className="mx-auto flex max-w-5xl items-center gap-6 px-6 py-3 text-sm">
          <Link href="/" className="font-semibold tracking-tight">
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
        </nav>
      </header>
      {children}
    </div>
  );
}
