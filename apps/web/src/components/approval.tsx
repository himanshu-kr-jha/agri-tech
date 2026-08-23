"use client";

/**
 * The approval gate — INV-1, FR-705, UI-11.
 *
 * This is the only place in the web tier that can advance a recommendation, and it is
 * deliberately a little heavy: approving something that moves lakhs of a collective's money
 * should not be a one-click affordance sitting next to "expand details".
 *
 * Three things it insists on:
 *
 * **Rejection requires a reason.** The API refuses without one (FR-706), and the form
 * refuses before the round trip so the CEO is not told off by a 409. An unexplained no is
 * the most valuable signal the system gets, thrown away.
 *
 * **Modification is offered as a first-class option, not an edge case.** The common real
 * answer to "release ₹35,000" is "yes, ₹32,000", and a UI with only Approve and Reject
 * quietly pushes that into a plain approval — which teaches the system its number was right.
 *
 * **The status is always stated in terms of what a human must still do.** "SUGGESTED" means
 * nothing to a CEO; "awaiting approval by an authorised role" means something.
 */

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { ConfidenceChip, formatRole, formatValue } from "@/components/invariants";
import type { Recommendation } from "@/lib/api";

type Mode = "idle" | "approve" | "modify" | "reject";

/**
 * Status reads as a hairline-ringed micro-cap, not a coloured pill.
 *
 * Only EXECUTED gets a fill: it is the one status that means something irreversible has
 * happened in the world. Everything before it is still a proposal, and colouring proposals
 * like outcomes is how a reader stops noticing the difference.
 */
const STATUS_STYLE: Record<string, string> = {
  SUGGESTED: "text-muted-foreground ring-border",
  REVIEWED: "text-chart-5 ring-chart-5/35",
  APPROVED: "text-primary ring-primary/30",
  EXECUTED: "bg-primary text-primary-foreground ring-primary",
  REJECTED: "text-destructive ring-destructive/30",
  SUPERSEDED: "text-muted-foreground/70 ring-border/70",
};

export function ApprovalCard({ recommendation }: { recommendation: Recommendation }) {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("idle");
  const [rationale, setRationale] = useState("");
  const [value, setValue] = useState(
    recommendation.recommended_value_paise
      ? String(Math.round(recommendation.recommended_value_paise / 100))
      : "",
  );
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();

  const decided = ["APPROVED", "EXECUTED", "REJECTED", "SUPERSEDED"].includes(
    recommendation.status,
  );

  async function send(path: string, body: Record<string, unknown>) {
    setError(null);
    const res = await fetch(`/api/recommendations/${recommendation.id}/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const problem = await res.json().catch(() => ({}));
      setError(problem.detail ?? `Request failed (${res.status})`);
      return;
    }
    setMode("idle");
    start(() => router.refresh());
  }

  return (
    <div className="rounded-md border border-border/70 bg-card p-5">
      <div className="flex flex-wrap items-baseline gap-2.5">
        <h3 className="font-serif text-[17px] tracking-tight text-primary">
          {recommendation.title}
        </h3>
        <ConfidenceChip value={recommendation.confidence} />
        <span
          className={`rounded px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.14em] ring-1 ring-inset ${
            STATUS_STYLE[recommendation.status] ?? STATUS_STYLE.SUGGESTED
          }`}
        >
          {recommendation.status.toLowerCase().replace(/_/g, " ")}
        </span>
        {recommendation.recommended_value_paise != null && (
          <span className="ml-auto font-serif text-xl tabular-nums text-primary">
            {formatValue(recommendation.recommended_value_paise, recommendation.value_unit)}
          </span>
        )}
      </div>

      <p className="mt-2.5 text-sm leading-relaxed text-foreground/85">
        {recommendation.reasoning}
      </p>

      {recommendation.awaiting && (
        <p className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
          Awaiting {recommendation.awaiting}. Nothing has happened yet.
        </p>
      )}

      {recommendation.approvals.length > 0 && (
        <ul className="mt-4 space-y-1.5 border-t border-border/60 pt-3 text-xs leading-relaxed text-muted-foreground">
          {recommendation.approvals.map((approval) => (
            <li key={approval.id}>
              <span className="font-medium">
                {approval.decision.toLowerCase().replace(/_/g, " ")}
              </span>{" "}
              by the {formatRole(approval.role_exercised)} on{" "}
              {new Date(approval.decided_at).toLocaleDateString("en-IN")}
              {approval.approved_value_paise != null &&
                approval.approved_value_paise !== recommendation.recommended_value_paise && (
                  <>
                    {" — modified to "}
                    <span className="font-medium">
                      {formatValue(approval.approved_value_paise, recommendation.value_unit)}
                    </span>
                  </>
                )}
              {approval.rationale && <span className="block italic">“{approval.rationale}”</span>}
            </li>
          ))}
        </ul>
      )}

      {error && (
        <p className="mt-3 rounded-md border border-destructive/25 bg-destructive/[0.04] p-3 text-xs leading-relaxed text-destructive">
          {error}
        </p>
      )}

      {!decided && mode === "idle" && (
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            onClick={() => setMode("approve")}
            className="btn-primary"
          >
            Approve
          </button>
          {recommendation.recommended_value_paise != null &&
            recommendation.value_unit !== "paise_per_kg" && (
            <button
              onClick={() => setMode("modify")}
              className="btn-ghost"
            >
              Approve with a different amount
            </button>
          )}
          <button
            onClick={() => setMode("reject")}
            className="btn-ghost border-destructive/30 text-destructive hover:border-destructive/50"
          >
            Reject
          </button>
        </div>
      )}

      {mode !== "idle" && (
        <form
          className="mt-4 space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (mode === "reject" && !rationale.trim()) {
              setError(
                "A rejection needs a reason. It is the clearest signal the system gets about what it got wrong.",
              );
              return;
            }
            if (mode === "reject") {
              void send("reject", { rationale });
            } else if (mode === "modify") {
              void send("approve", {
                rationale,
                approved_value_paise: Math.round(Number(value) * 100),
              });
            } else {
              void send("approve", { rationale: rationale || undefined });
            }
          }}
        >
          {mode === "modify" && (
            <label className="block text-sm">
              <span className="eyebrow-sm">Approved amount (₹)</span>
              <input
                type="number"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                required
                className="mt-1.5 w-full rounded-md border border-border/70 bg-card px-3 py-2 tabular-nums transition-colors focus:border-primary/30"
              />
              <span className="mt-1.5 block text-xs leading-relaxed text-muted-foreground">
                Recorded as a modification, not a plain approval — so the system learns its
                figure was not the one you agreed.
              </span>
            </label>
          )}
          <label className="block text-sm">
            <span className="eyebrow-sm">
              {mode === "reject" ? "Why not? (required)" : "Note (optional)"}
            </span>
            <textarea
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              rows={2}
              className="mt-1.5 w-full rounded-md border border-border/70 bg-card px-3 py-2 text-sm leading-relaxed transition-colors focus:border-primary/30"
            />
          </label>
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={pending}
              className="btn-primary"
            >
              {mode === "reject" ? "Confirm rejection" : "Confirm approval"}
            </button>
            <button
              type="button"
              onClick={() => {
                setMode("idle");
                setError(null);
              }}
              className="btn-ghost"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {recommendation.status === "APPROVED" && (
        <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-border/60 pt-4">
          <button onClick={() => void send("execute", {})} disabled={pending} className="btn-primary">
            Mark as executed
          </button>
          <span className="text-xs leading-relaxed text-muted-foreground">
            Records what was actually done, so the outcome can be attributed later (INV-7).
          </span>
        </div>
      )}
    </div>
  );
}
