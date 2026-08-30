/**
 * SSE proxy for the assistant.
 *
 * Streams the upstream body straight through rather than buffering it — buffering would
 * defeat the entire purpose, which is that the first section reaches the screen before the
 * last one is computed. The dev token stays server-side (see the approval proxy for why).
 */

import { NextRequest, NextResponse } from "next/server";

import { sessionToken } from "@/lib/session";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Deployment (Vercel). The Node runtime, because Edge would sever the streaming proxy from
// the Node fetch semantics this route relies on. maxDuration because a decision packet that
// calls six modules and then narrates outlives the default serverless budget — and the
// failure mode is a truncated stream mid-answer, which reads as a broken product rather
// than as a timeout. Both are inert in local dev.
export const runtime = "nodejs";
export const maxDuration = 60;


export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  const token = await sessionToken();
  const upstream = await fetch(`${API}/api/v1/assistant/ask/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });

  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text();
    return new NextResponse(text || JSON.stringify({ detail: "upstream failed" }), {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new NextResponse(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
