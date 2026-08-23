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

import { ConfidenceChip, formatValue } from "@/components/invariants";
import type { Recommendation } from "@/lib/api";

type Mode = "idle" | "approve" | "modify" | "reject";

const STATUS_STYLE: Record<string, string> = {
  SUGGESTED: "bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300",
  REVIEWED: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200",
  APPROVED: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  EXECUTED: "bg-emerald-600 text-white",
  REJECTED: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200",
  SUPERSEDED: "bg-neutral-200 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400",
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
    <div className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
      <div className="flex flex-wrap items-baseline gap-2">
        <h3 className="font-medium">{recommendation.title}</h3>
        <ConfidenceChip value={recommendation.confidence} />
        <span
          className={`rounded px-2 py-0.5 text-xs font-medium ${
            STATUS_STYLE[recommendation.status] ?? STATUS_STYLE.SUGGESTED
          }`}
        >
          {recommendation.status.toLowerCase().replace(/_/g, " ")}
        </span>
        {recommendation.recommended_value_paise != null && (
          <span className="ml-auto tabular-nums font-medium">
            {formatValue(recommendation.recommended_value_paise, recommendation.value_unit)}
          </span>
        )}
      </div>

      <p className="mt-2 text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">
        {recommendation.reasoning}
      </p>

      {recommendation.awaiting && (
        <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">
          Awaiting {recommendation.awaiting}. Nothing has happened yet.
        </p>
      )}

      {recommendation.approvals.length > 0 && (
        <ul className="mt-3 space-y-1 border-t border-neutral-100 pt-3 text-xs text-neutral-600 dark:border-neutral-900 dark:text-neutral-400">
          {recommendation.approvals.map((approval) => (
            <li key={approval.id}>
              <span className="font-medium">
                {approval.decision.toLowerCase().replace(/_/g, " ")}
              </span>{" "}
              by {approval.role_exercised.replace(/_/g, " ").toLowerCase()} on{" "}
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
        <p className="mt-3 rounded border border-rose-200 bg-rose-50 p-2 text-xs text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200">
          {error}
        </p>
      )}

      {!decided && mode === "idle" && (
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            onClick={() => setMode("approve")}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300"
          >
            Approve
          </button>
          {recommendation.recommended_value_paise != null &&
            recommendation.value_unit !== "paise_per_kg" && (
            <button
              onClick={() => setMode("modify")}
              className="rounded-md px-3 py-1.5 text-sm ring-1 ring-inset ring-neutral-300 hover:bg-neutral-100 dark:ring-neutral-700 dark:hover:bg-neutral-800"
            >
              Approve with a different amount
            </button>
          )}
          <button
            onClick={() => setMode("reject")}
            className="rounded-md px-3 py-1.5 text-sm text-rose-700 ring-1 ring-inset ring-rose-300 hover:bg-rose-50 dark:text-rose-300 dark:ring-rose-800 dark:hover:bg-rose-950"
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
              <span className="text-neutral-600 dark:text-neutral-400">Approved amount (₹)</span>
              <input
                type="number"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                required
                className="mt-1 w-full rounded-md border border-neutral-300 px-3 py-1.5 tabular-nums dark:border-neutral-700 dark:bg-neutral-900"
              />
              <span className="mt-1 block text-xs text-neutral-500">
                Recorded as a modification, not a plain approval — so the system learns its
                figure was not the one you agreed.
              </span>
            </label>
          )}
          <label className="block text-sm">
            <span className="text-neutral-600 dark:text-neutral-400">
              {mode === "reject" ? "Why not? (required)" : "Note (optional)"}
            </span>
            <textarea
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              rows={2}
              className="mt-1 w-full rounded-md border border-neutral-300 px-3 py-1.5 dark:border-neutral-700 dark:bg-neutral-900"
            />
          </label>
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={pending}
              className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
            >
              {mode === "reject" ? "Confirm rejection" : "Confirm approval"}
            </button>
            <button
              type="button"
              onClick={() => {
                setMode("idle");
                setError(null);
              }}
              className="rounded-md px-3 py-1.5 text-sm ring-1 ring-inset ring-neutral-300 dark:ring-neutral-700"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {recommendation.status === "APPROVED" && (
        <div className="mt-4 border-t border-neutral-100 pt-3 dark:border-neutral-900">
          <button
            onClick={() => void send("execute", {})}
            disabled={pending}
            className="rounded-md bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
          >
            Mark as executed
          </button>
          <span className="ml-2 text-xs text-neutral-500">
            Records what was actually done, so the outcome can be attributed later (INV-7).
          </span>
        </div>
      )}
    </div>
  );
}
