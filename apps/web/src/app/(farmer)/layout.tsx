/**
 * Farmer portal shell — UI-05, INV-5.
 *
 * A separate route group from the FPO console, and separately guarded. The separation is not
 * decoration: no page in this tree renders organization-internal data, so the information
 * boundary cannot be crossed by a routing mistake. The API refuses anyway.
 *
 * Larger type and fewer words than the console. This is read on a phone, outdoors, often by
 * someone for whom Hindi is the first language and text is not the easiest channel.
 */

import Link from "next/link";
import { redirect } from "next/navigation";

import { SignOutButton } from "@/components/sign-out";
import { currentUser, homeFor } from "@/lib/session";

export default async function FarmerLayout({ children }: { children: React.ReactNode }) {
  const user = await currentUser();
  if (!user) redirect("/login");
  if (user.audience !== "FARMER") redirect(homeFor(user));

  return (
    <div className="min-h-screen font-sans text-[17px]">
      <header className="border-b border-neutral-200 dark:border-neutral-800">
        <nav className="mx-auto flex max-w-2xl items-center gap-4 px-5 py-3">
          <Link href="/today" className="font-semibold tracking-tight">
            AgriVardhak
          </Link>
          <span className="text-sm text-neutral-500">मेरा खेत · My farm</span>
          <div className="ml-auto">
            <SignOutButton />
          </div>
        </nav>
      </header>
      {children}
    </div>
  );
}
