/**
 * The front door.
 *
 * Sends you where you belong: the console if you are organization staff, your own farm if
 * you are a member, the sign-in page if you are neither. `homeFor` is the single place that
 * decision is made, and it reads the audience the API returned rather than re-deriving it
 * from a role list — so no two screens can disagree about who you are.
 *
 * (This replaced the Phase 0 gate page, which existed to prove the API → UI path worked.
 * That job is now done by 8 component tests and 311 API tests.)
 */

import { redirect } from "next/navigation";

import { currentUser, homeFor } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function RootPage() {
  redirect(homeFor(await currentUser()));
}
