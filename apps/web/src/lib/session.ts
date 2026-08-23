/**
 * The signed-in session, server-side only.
 *
 * The JWT lives in an **httpOnly** cookie. That is the whole design decision worth
 * explaining: a token in `localStorage` is readable by any script on the page, so a single
 * XSS anywhere becomes a stolen session that works against the API directly. httpOnly means
 * the browser will send it and no script can read it — including ours, which is why every
 * API call goes through a server component or a route handler rather than `fetch` from the
 * browser.
 *
 * `AGRI_DEV_TOKEN` still works as a fallback so `make dev-env` and the older scripts keep
 * functioning, but a real cookie always wins.
 */

import { cookies } from "next/headers";

export const SESSION_COOKIE = "agrivardhak_session";

export interface SessionUser {
  id: string;
  display_name: string;
  email: string | null;
  locale: string;
  roles: string[];
  /** "FPO" | "FARMER" | "NONE" — decided by the API, never re-derived here. */
  audience: string;
  organization_id: string | null;
  farmer_id: string | null;
  farmer_name: string | null;
  is_demo_account: boolean;
}

/** The bearer token for outgoing API calls, or "" when nobody is signed in. */
export async function sessionToken(): Promise<string> {
  const jar = await cookies();
  return jar.get(SESSION_COOKIE)?.value ?? process.env.AGRI_DEV_TOKEN ?? "";
}

/**
 * Who is signed in, according to the API.
 *
 * Asks the API rather than decoding the JWT here. Decoding is easy and would be wrong: the
 * web tier has no way to *verify* the signature, so it would be trusting a value it merely
 * read. One authority for identity, and it is the service that holds the key.
 */
export async function currentUser(): Promise<SessionUser | null> {
  const token = await sessionToken();
  if (!token) return null;
  try {
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/auth/me`,
      { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" },
    );
    if (!res.ok) return null;
    return (await res.json()) as SessionUser;
  } catch {
    // API down. Treat it as signed out rather than crashing every page — the layouts show
    // a "could not reach the API" message, which is the more useful thing to see.
    return null;
  }
}

/** Where a signed-in user belongs. One place, so no two screens can disagree. */
export function homeFor(user: SessionUser | null): string {
  if (!user) return "/login";
  if (user.audience === "FPO") return "/dashboard";
  if (user.audience === "FARMER") return "/today";
  return "/login";
}
