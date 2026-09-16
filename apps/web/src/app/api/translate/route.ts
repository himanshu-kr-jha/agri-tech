/**
 * Proxy for the page translator (ADR-0023).
 *
 * The browser never calls FastAPI or Sarvam directly: the Sarvam key lives only in the API's
 * environment, and the session token that lets a signed-in reader spend a translation call
 * lives in an httpOnly cookie only the server can read.
 */

import { NextRequest, NextResponse } from "next/server";

import { sessionToken } from "@/lib/session";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** The glossary version, so a page served wholly from the browser cache can tell it is stale. */
export async function GET() {
  try {
    const upstream = await fetch(`${API}/api/v1/translate/version`, { cache: "no-store" });
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "translation service unreachable" }, { status: 502 });
  }
}

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  if (!body || typeof body !== "object") {
    return NextResponse.json({ detail: "expected a JSON body" }, { status: 400 });
  }

  const token = await sessionToken();
  try {
    const upstream = await fetch(`${API}/api/v1/translate`, {
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
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "translation service unreachable" }, { status: 502 });
  }
}
