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

  const packet = done || Object.keys(sections).length > 0 ? (sections as unknown as Packet) : null;

  return (
    <>
      <form onSubmit={ask} className="space-y-3">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={2}
          maxLength={500}
          className="w-full rounded-lg border border-neutral-300 px-4 py-3 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          placeholder="What should we do this season?"
        />
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="submit"
            disabled={busy}
            className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
          >
            {busy ? "Working…" : "Ask"}
          </button>
          {busy && (
            <button
              type="button"
              onClick={() => abort.current?.abort()}
              className="rounded-md px-3 py-2 text-sm ring-1 ring-inset ring-neutral-300 dark:ring-neutral-700"
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
            className="rounded-full px-3 py-1 text-xs ring-1 ring-inset ring-neutral-300 hover:bg-neutral-100 dark:ring-neutral-700 dark:hover:bg-neutral-800"
          >
            {example}
          </button>
        ))}
      </div>

      {progress && busy && (
        <p className="mt-6 text-sm text-neutral-500">
          {progress.state === "planning"
            ? "Choosing which modules this question needs…"
            : `Gathered ${progress.plan?.map((m) => MODULE_LABEL[m] ?? m).join(", ")} in ${(
                (progress.elapsed_ms ?? 0) / 1000
              ).toFixed(1)}s. Reconciling…`}
        </p>
      )}

      {error && (
        <p className="mt-6 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200">
          {error}
        </p>
      )}

      {packet && (
        <div className="mt-8 border-t border-neutral-200 pt-8 dark:border-neutral-800">
          <PacketView packet={packet} />
          {done && (
            <p className="mt-8 border-t border-neutral-100 pt-4 text-xs text-neutral-500 dark:border-neutral-900">
              Evidence frozen as{" "}
              <span className="font-mono">{done.content_hash.slice(0, 16)}…</span> ·{" "}
              <a
                href={`/decisions/${done.packet_id}`}
                className="underline underline-offset-2"
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
