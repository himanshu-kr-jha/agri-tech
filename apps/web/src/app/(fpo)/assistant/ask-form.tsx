"use client";

/**
 * The question box and the streamed answer (API-05).
 *
 * Sections arrive one at a time over SSE and render as they land. That is not a loading
 * animation dressed up: a packet takes several seconds because five modules are running over
 * a thousand farmers and two years of prices, and watching Situation appear while Impact is
 * still computing is the difference between "it is thinking" and "it has hung".
 *
 * Deliberately not token-by-token. The unit a CEO reads is a section, and a section either
 * has its evidence or it does not exist yet — streaming half-formed prose would put claims
 * on screen before the numbers that justify them.
 */

import { useRef, useState } from "react";

import { PacketView } from "@/components/packet";
import type { Packet } from "@/lib/api";

interface Progress {
  state: string;
  plan?: string[];
  elapsed_ms?: number;
}

const MODULE_LABEL: Record<string, string> = {
  quality: "production forecast",
  market: "buyers and prices",
  risk: "hazards and exposure",
  farm: "crop economics",
  crop_health: "field reports",
  scheme: "entitlements",
};

export function AskForm({ examples }: { examples: string[] }) {
  const [question, setQuestion] = useState(examples[0]);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [sections, setSections] = useState<Record<string, unknown>>({});
  const [done, setDone] = useState<{ packet_id: string; content_hash: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  async function ask(event: React.FormEvent) {
    event.preventDefault();
    if (!question.trim()) return;
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;

    setBusy(true);
    setError(null);
    setSections({});
    setDone(null);
    setProgress({ state: "planning" });

    try {
      const response = await fetch("/api/assistant/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        const problem = await response.json().catch(() => ({}));
        throw new Error(problem.detail ?? `The API returned ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done: finished } = await reader.read();
        if (finished) break;
        buffer += decoder.decode(value, { stream: true });
        // SSE frames are separated by a blank line; anything after the last one is partial.
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const line = frame.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          const payload = JSON.parse(line.slice(6));
          if (payload.section) {
            setSections((prev) => ({ ...prev, [payload.section]: payload.content }));
          } else if (payload.content_hash) {
            setDone(payload);
          } else {
            setProgress(payload);
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setError((err as Error).message);
      }
    } finally {
      setBusy(false);
    }
  }

  // `Partial<Packet>`, and the cast is deliberate rather than lazy: sections arrive one at a
  // time, so between the first frame and the last this object genuinely has holes in it.
  // Calling it a complete Packet is what crashed the page on the first render — PacketView
  // now takes a partial and renders only what has landed.
  const packet: Partial<Packet> | null =
    done || Object.keys(sections).length > 0 ? (sections as Partial<Packet>) : null;

  return (
    <>
      <form onSubmit={ask} className="space-y-3">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={2}
          maxLength={500}
          className="w-full rounded-md border border-border/70 bg-card px-4 py-3.5 text-sm leading-relaxed text-foreground transition-colors placeholder:text-muted-foreground/50 focus:border-primary/30"
          placeholder="What should we do this season?"
        />
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="submit"
            disabled={busy}
            className="btn-primary"
          >
            {busy ? "Working…" : "Ask"}
          </button>
          {busy && (
            <button
              type="button"
              onClick={() => abort.current?.abort()}
              className="btn-ghost"
            >
              Stop
            </button>
          )}
        </div>
      </form>

      <div className="mt-3 flex flex-wrap gap-2">
        {examples.map((example) => (
          <button
            key={example}
            onClick={() => setQuestion(example)}
            className="rounded-full border border-border/60 bg-card px-3.5 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/25 hover:text-foreground"
          >
            {example}
          </button>
        ))}
      </div>

      {progress && busy && (
        <p className="mt-6 flex items-center gap-2.5 text-sm text-muted-foreground">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" aria-hidden="true" />
          {progress.state === "planning"
            ? "Choosing which modules this question needs…"
            : `Gathered ${progress.plan?.map((m) => MODULE_LABEL[m] ?? m).join(", ")} in ${(
                (progress.elapsed_ms ?? 0) / 1000
              ).toFixed(1)}s. Reconciling…`}
        </p>
      )}

      {error && (
        <p className="mt-6 rounded-md border border-destructive/25 bg-destructive/[0.04] p-4 text-sm text-destructive">
          {error}
        </p>
      )}

      {packet && (
        <div className="mt-10 border-t border-border/70 pt-8">
          <PacketView packet={packet} />
          {done && (
            <p className="mt-8 border-t border-border/60 pt-4 text-xs text-muted-foreground">
              Evidence frozen as{" "}
              <span className="font-mono">{done.content_hash.slice(0, 16)}…</span> ·{" "}
              <a
                href={`/decisions/${done.packet_id}`}
                className="text-primary underline underline-offset-4"
              >
                open this decision to approve or reject
              </a>
            </p>
          )}
        </div>
      )}
    </>
  );
}
