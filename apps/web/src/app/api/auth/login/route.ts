/**
 * Sign in, and put the token where scripts cannot read it.
 *
 * The browser posts credentials here; this handler forwards them to FastAPI and, on success,
 * writes the returned JWT into an httpOnly cookie. The password never touches our own
 * storage and the token never reaches client JavaScript.
 */

import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE } from "@/lib/session";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));

  const upstream = await fetch(`${API}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: body.username, password: body.password }),
    cache: "no-store",
  }).catch(() => null);

  if (!upstream) {
    return NextResponse.json(
      { detail: "Could not reach the API. Is it running? (make api)" },
      { status: 503 },
    );
  }
  const payload = await upstream.json().catch(() => ({}));
  if (!upstream.ok) {
    return NextResponse.json(
      { detail: payload.detail ?? "Sign-in failed." },
      { status: upstream.status },
    );
  }

  const response = NextResponse.json({ user: payload.user });
  response.cookies.set(SESSION_COOKIE, payload.token, {
    httpOnly: true,
    sameSite: "lax",
    // Not `secure` in development, or the cookie would be dropped over plain http and the
    // sign-in would appear to succeed and then silently do nothing.
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: payload.expires_in ?? 60 * 60 * 12,
  });
  return response;
}
