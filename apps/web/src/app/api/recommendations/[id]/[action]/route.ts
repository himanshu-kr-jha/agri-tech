/**
 * Proxy for the approval actions.
 *
 * The browser never talks to FastAPI directly, and that is not incidental: the dev token
 * lives in a server-only environment variable, and a client component posting straight to
 * the API would have to hold a credential the browser can read. Routing through here keeps
 * the token server-side and leaves the boundary with exactly one enforcement point
 * (ADR-0001).
 */

import { NextRequest, NextResponse } from "next/server";

import { sessionToken } from "@/lib/session";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";


/** Only these three. A path segment from the URL must never become an arbitrary API call. */
const ALLOWED = new Set(["approve", "reject", "execute", "review"]);

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; action: string }> },
) {
  const { id, action } = await params;
  if (!ALLOWED.has(action)) {
    return NextResponse.json({ detail: `unknown action: ${action}` }, { status: 400 });
  }
  const body = await request.json().catch(() => ({}));
  const token = await sessionToken();
  const upstream = await fetch(`${API}/api/v1/recommendations/${id}/${action}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json" },
  });
}
