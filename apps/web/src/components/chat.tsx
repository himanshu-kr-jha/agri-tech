"use client";

/**
 * The conversational assistant — a transcript, not a single answer (API-05, FR-807).
 *
 * Each turn renders **by response shape**, because a question that asks what is true and a
 * question that proposes committing a season are not the same kind of answer and should not
 * look alike. A DECISION turn renders through the existing `PacketView`; a LOOKUP or EXPLAIN
 * turn renders as cited claims; a REFUSE turn says what the asker cannot see and, more
 * usefully, what they can.
 *
 * The first frame on the wire is the router's decision, and it is shown. That is not a
 * spinner with better copy: it is the only genuinely early information there is, it tells the
 * reader what the system is about to read, and it is what makes ~700ms of classification feel
 * like work rather than lag.
 *
 * A turn is never rendered token-by-token. The unit is a claim or a section, and either has
 * its evidence or does not exist yet — streaming half a claim would put a sentence on screen
 * before the number that justifies it.
 */

import { useEffect, useRef, useState } from "react";

import { ConfidenceChip } from "@/components/invariants";
import { PacketView } from "@/components/packet";
import type { Claim, Packet } from "@/lib/api";

interface Routing {
  shape: string;
  lookup: string | null;
  modules: string[];
  entities: { crop?: string; horizon_days?: number };
  rationale: string;
  fell_back: boolean;
}

interface Done {
  turn_id: string | null;
  packet_id: string | null;
  content_hash: string | null;
  grounded: boolean;
  shape: string;
}

interface Turn {
  key: string;
  question: string;
  routing?: Routing;
  claims: Claim[];
  packet: Partial<Packet> | null;
  refusal: string | null;
  done?: Done;
  error?: string;
}

/** Module keys read as jargon; these are what a CEO would call them. */
const MODULE_LABEL: Record<string, string> = {
  quality: "production forecast",
  market: "buyers and prices",
  risk: "hazards and exposure",
  farm: "crop economics",
  crop_health: "field reports",
  scheme: "entitlements",
  funding: "working capital",
};

const LOOKUP_LABEL: Record<string, string> = {
  TODAYS_PRIORITIES: "what needs a decision today",
  FARMERS_NEEDING_ATTENTION: "members and crops needing attention",
  PRODUCTION_FORECAST: "expected production",
  RISK_SUMMARY: "the risk register",
  SCHEME_ELIGIBILITY: "scheme entitlements",
  MARKET_SNAPSHOT: "buyers and prices",
  FUNDING_POSITION: "working capital",
  WHATS_CHANGED: "what has changed recently",
  MY_YIELD_GAP: "your crops and their yield gap",
  MY_TASKS_TODAY: "your farm today",
  MY_SCHEMES: "schemes you may claim",
  MY_ANNOUNCEMENTS: "what the collective has shared",
};

export function ChatPanel({
  examples,
  placeholder = "Ask a question",
}: {
  examples: string[];
  placeholder?: string;
}) {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const conversationId = useRef<string>("");
  const anchor = useRef<string | null>(null);
  const tail = useRef<HTMLDivElement | null>(null);

  // One conversation id per mount. Follow-ups anchor to the last packet within it; a reload
  // starts a new thread, which matches the agreed scope — session-scoped, not persistent.
  useEffect(() => {
    if (!conversationId.current) conversationId.current = crypto.randomUUID();
  }, []);

  useEffect(() => {
    tail.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  function patch(key: string, change: (turn: Turn) => Turn) {
    setTurns((prev) => prev.map((t) => (t.key === key ? change(t) : t)));
  }

  async function send(text: string) {
    const asked = text.trim();
    if (!asked || busy) return;

    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;

    const key = crypto.randomUUID();
    setTurns((prev) => [
      ...prev,
      { key, question: asked, claims: [], packet: null, refusal: null },
    ]);
    setQuestion("");
    setBusy(true);

    try {
      const response = await fetch("/api/assistant/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: asked,
          conversation_id: conversationId.current,
          anchor_packet_id: anchor.current,
        }),
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
        // SSE frames are separated by a blank line; whatever follows the last one is partial.
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const event = frame.match(/^event: (.+)$/m)?.[1];
          const raw = frame.match(/^data: (.+)$/m)?.[1];
          if (!event || !raw) continue;
          const payload = JSON.parse(raw);

          if (event === "routing") {
            patch(key, (t) => ({ ...t, routing: payload as Routing }));
          } else if (event === "claim") {
            patch(key, (t) => ({ ...t, claims: [...t.claims, payload.content as Claim] }));
          } else if (event === "section") {
            patch(key, (t) => ({
              ...t,
              packet: { ...(t.packet ?? {}), [payload.section]: payload.content },
            }));
          } else if (event === "refusal") {
            patch(key, (t) => ({ ...t, refusal: payload.text as string }));
          } else if (event === "error") {
            // The response is already a 200 by the time this can happen, so this event is
            // the only way the browser learns a turn failed rather than simply stopping.
            patch(key, (t) => ({ ...t, error: String(payload.detail) }));
          } else if (event === "done") {
            const done = payload as Done;
            if (done.packet_id) anchor.current = done.packet_id;
            patch(key, (t) => ({ ...t, done }));
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        patch(key, (t) => ({ ...t, error: (err as Error).message }));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-8">
      {turns.length === 0 && (
        <div className="flex flex-wrap gap-2">
          {examples.map((example) => (
            <button
              key={example}
              onClick={() => send(example)}
              className="rounded-full border border-border/60 bg-card px-3.5 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:border-primary/25 hover:text-foreground"
            >
              {example}
            </button>
          ))}
        </div>
      )}

      {turns.map((turn) => (
        <TurnView key={turn.key} turn={turn} />
      ))}
      <div ref={tail} />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send(question);
        }}
        className="sticky bottom-0 space-y-3 border-t border-border/70 bg-background/95 pt-4 backdrop-blur"
      >
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send(question);
            }
          }}
          rows={2}
          maxLength={500}
          placeholder={placeholder}
          className="w-full rounded-md border border-border/70 bg-card px-4 py-3.5 text-sm leading-relaxed text-foreground transition-colors placeholder:text-muted-foreground/50 focus:border-primary/30"
        />
        <div className="flex flex-wrap items-center gap-2">
          <button type="submit" disabled={busy} className="btn-primary">
            {busy ? "Working…" : "Ask"}
          </button>
          {busy && (
            <button type="button" onClick={() => abort.current?.abort()} className="btn-ghost">
              Stop
            </button>
          )}
          {turns.length > 0 && !busy && (
            <span className="text-xs text-muted-foreground">
              Ask “why?” to see the evidence behind the last answer.
            </span>
          )}
        </div>
      </form>
    </div>
  );
}

function TurnView({ turn }: { turn: Turn }) {
  const waiting = !turn.done && !turn.error;
  return (
    <section className="space-y-4">
      <p className="text-[15px] font-medium text-foreground">{turn.question}</p>

      {turn.routing && <RoutingLine routing={turn.routing} waiting={waiting} />}
      {!turn.routing && waiting && (
        <p className="flex items-center gap-2.5 text-sm text-muted-foreground">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" aria-hidden="true" />
          Working out what this question needs…
        </p>
      )}

      {turn.error && (
        <p className="rounded-md border border-destructive/25 bg-destructive/[0.04] p-4 text-sm text-destructive">
          {turn.error}
        </p>
      )}

      {turn.refusal && (
        <p className="rounded-md border border-border/70 bg-muted/30 p-4 text-sm leading-relaxed text-foreground">
          {turn.refusal}
        </p>
      )}

      {turn.claims.length > 0 && <ClaimList claims={turn.claims} />}
      {turn.packet && <PacketView packet={turn.packet} />}

      {turn.done && <TurnFooter done={turn.done} />}
    </section>
  );
}

function RoutingLine({ routing, waiting }: { routing: Routing; waiting: boolean }) {
  const what =
    routing.lookup !== null
      ? (LOOKUP_LABEL[routing.lookup] ?? routing.lookup.toLowerCase().replace(/_/g, " "))
      : routing.modules.length > 0
        ? routing.modules.map((m) => MODULE_LABEL[m] ?? m).join(", ")
        : routing.rationale || "the full picture";
  const crop = routing.entities?.crop;
  return (
    <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
      {waiting && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" aria-hidden="true" />
      )}
      <span>
        Reading {what}
        {/* Shown because "did it understand which crop I asked about" is the first thing a
            reader wants to know, and it is knowable before any work has been done. */}
        {crop ? <>, focused on <span className="text-foreground">{crop}</span></> : null}.
      </span>
      {routing.fell_back && (
        // A degraded answer is shown as degraded. Silently worse is the failure mode this
        // whole system is arranged against.
        <span className="rounded-full border border-border/60 px-2 py-0.5 text-[11px] text-muted-foreground">
          matched on keywords — the routing model was unavailable
        </span>
      )}
    </p>
  );
}

function ClaimList({ claims }: { claims: Claim[] }) {
  // FR-804 again, in the renderer. The API drops unevidenced claims and the schema forbids
  // them; doing it a third time here costs nothing and closes the last gap.
  const evidenced = claims.filter((c) => c.evidence && c.evidence.length > 0);
  if (evidenced.length === 0) return null;
  return (
    <ul className="space-y-3">
      {evidenced.map((claim, i) => (
        <li key={i} className="rounded-md border border-border/60 bg-card p-4">
          <div className="flex items-start justify-between gap-4">
            <p className="text-sm leading-relaxed text-foreground">{claim.statement}</p>
            <ConfidenceChip value={claim.confidence} />
          </div>
          <p className="mt-2.5 text-xs text-muted-foreground">
            {claim.evidence.length} source{claim.evidence.length === 1 ? "" : "s"} ·{" "}
            {claim.evidence
              .slice(0, 2)
              .map((e) => e.label)
              .join(" · ")}
          </p>
        </li>
      ))}
    </ul>
  );
}

function TurnFooter({ done }: { done: Done }) {
  return (
    <p className="border-t border-border/60 pt-3 text-xs text-muted-foreground">
      {done.packet_id && done.content_hash && (
        <>
          Evidence frozen as <span className="font-mono">{done.content_hash.slice(0, 16)}…</span> ·{" "}
          <a
            href={`/decisions/${done.packet_id}`}
            className="text-primary underline underline-offset-4"
          >
            open this decision to approve or reject
          </a>
        </>
      )}
      {!done.packet_id && (
        <>Answered from current records. Nothing here proposes an action, so nothing needs approval.</>
      )}
      {!done.grounded && (
        <span className="ml-2 text-destructive">
          · shown unreviewed: the relevance pass did not verify against its sources
        </span>
      )}
    </p>
  );
}
