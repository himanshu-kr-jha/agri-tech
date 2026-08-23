/**
 * SSE proxy for the assistant.
 *
 * Streams the upstream body straight through rather than buffering it — buffering would
 * defeat the entire purpose, which is that the first section reaches the screen before the
 * last one is computed. The dev token stays server-side (see the approval proxy for why).
 */

import { NextRequest, NextResponse } from "next/server";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEV_TOKEN = process.env.AGRI_DEV_TOKEN ?? "";

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  const upstream = await fetch(`${API}/api/v1/assistant/ask/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(DEV_TOKEN ? { Authorization: `Bearer ${DEV_TOKEN}` } : {}),
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
