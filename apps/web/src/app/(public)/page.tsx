/**
 * The front door.
 *
 * Sends you where you belong: the console if you are organization staff, your own farm if
 * you are a member. `homeFor` is the single place that decision is made, and it reads the
 * audience the API returned rather than re-deriving it from a role list — so no two screens
 * can disagree about who you are.
 *
 * Anyone signed out sees the public landing page instead of bouncing straight to `/login` —
 * this is the one URL a judge or funder might open cold, before ever touching the console.
 *
 * (This replaced the Phase 0 gate page, which existed to prove the API → UI path worked.
 * That job is now done by 8 component tests and 311 API tests.)
 */

import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { LandingPage } from "@/components/landing/landing-page";
import { currentUser, homeFor } from "@/lib/session";

/**
 * Per-request, because the redirect above reads the session cookie. Two things must never
 * be added to this file or to the `(public)` layout, and both fail silently rather than
 * loudly:
 *
 * - `export const fetchCache = …`. `force-dynamic` alone does NOT defeat the landing
 *   page's hourly stats cache — Next only applies its no-store rule to fetches that carry
 *   no explicit config of their own, and `getPublic()` passes `next.revalidate`. An
 *   explicit `fetchCache`, though, is honoured, and would turn that hourly read into a
 *   database round-trip on every cold view.
 * - Routing the stats call through `api.ts`'s `get<T>()`, which attaches a bearer token —
 *   any fetch carrying an `authorization` header is classed uncacheable.
 */
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: { absolute: "AgriVardhak — decision support for FPOs" },
  description:
    "AgriVardhak turns fragmented farmer data and outside agricultural intelligence into auditable, human-approved decision packets — never an autonomous action.",
  openGraph: {
    title: "AgriVardhak — decision support for FPOs",
    description:
      "Auditable, human-approved decision packets for sustainable farmer income and FPO financial health.",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "AgriVardhak — decision support for FPOs",
    description:
      "Auditable, human-approved decision packets for sustainable farmer income and FPO financial health.",
  },
};

export default async function RootPage() {
  const user = await currentUser();
  if (user) redirect(homeFor(user));
  return <LandingPage />;
}
