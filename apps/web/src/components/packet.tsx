/**
 * Decision Packet renderer — FR-801…806, UI-02, UI-10.
 *
 * Nine sections in a fixed order, because the order is part of the contract: a CEO who reads
 * this weekly learns where to look, and shuffling sections by "importance" would take that
 * away every time the data changed.
 *
 * Three rules this component enforces on behalf of the invariants, so no page author has to
 * remember them:
 *
 * 1. **A claim with no evidence does not render** (FR-804). The API drops them too; doing it
 *    again here costs nothing and closes the last gap between a plausible sentence and a
 *    screen.
 * 2. **Every number carries its confidence** (UI-02).
 * 3. **The override is shown, and shown prominently** (FR-802). It is the most valuable thing
 *    in the packet — it is where the system disagrees with itself in front of the reader —
 *    so it sits above the recommendations rather than in a footnote.
 */

import { ConfidenceChip, formatInr } from "@/components/invariants";
import type {
  Claim,
  ConfidenceBlock,
  EvidenceRef,
  OverrideNote,
  Packet,
  PacketAction,
} from "@/lib/api";

const SECTION_TITLE: Record<string, string> = {
  situation: "Situation",
  impact: "Impact",
  recommendation: "Recommendation",
  expected_outcome: "Expected outcome",
  confidence: "Confidence",
  evidence: "Evidence",
  actions: "Actions",
};

/**
 * Renders a packet that may only be **partly arrived**.
 *
 * This component is mounted after every SSE frame, so on the first render it holds nothing
 * but `situation` — `recommendation`, `actions` and `overrides` are still undefined. Treating
 * the input as a complete `Packet` crashed the page on the first frame with
 * `Cannot read properties of undefined (reading 'map')`, and it crashed *only* in a browser:
 * a script that accumulates every frame before rendering never sees a half-built packet, so
 * the stream parsed perfectly and the screen was blank.
 *
 * So the type is `Partial<Packet>` and every section renders only once its data exists. A
 * section that has not arrived is *absent*, not an empty heading — the reader watches the
 * answer assemble rather than watching placeholders fill in.
 */
export function PacketView({ packet }: { packet: Partial<Packet> }) {
  return (
    <article className="space-y-8">
      {packet.overrides && packet.overrides.length > 0 && (
        <OverrideBanner overrides={packet.overrides} />
      )}

      {packet.situation && (
        <Section title={SECTION_TITLE.situation} subtitle="What is happening">
          <Claims claims={packet.situation} />
        </Section>
      )}

      {packet.impact && (
        <Section title={SECTION_TITLE.impact} subtitle="Who and what is affected">
          <Claims claims={packet.impact} showAffected />
        </Section>
      )}

      {packet.recommendation && (
        <Section
          title={SECTION_TITLE.recommendation}
          subtitle="Proposed — nothing happens until a human approves"
        >
          <div className="space-y-3">
            {packet.recommendation.map((action, i) => (
              <ActionCard key={i} action={action} />
            ))}
          </div>
        </Section>
      )}

      {packet.expected_outcome && (
        <Section
          title={SECTION_TITLE.expected_outcome}
          subtitle="Ranges and directions, never promised figures"
        >
          <Claims claims={packet.expected_outcome} />
        </Section>
      )}

      {packet.confidence && <ConfidenceSection confidence={packet.confidence} />}

      {packet.actions && packet.actions.length > 0 && (
        <Section title={SECTION_TITLE.actions} subtitle="A role, a task, a date">
          <ul className="divide-y divide-neutral-100 dark:divide-neutral-900">
            {packet.actions.map((action, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2.5 text-sm">
                <span className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-xs dark:bg-neutral-800">
                  {action.role.replace(/_/g, " ").toLowerCase()}
                </span>
                <span>{action.task}</span>
                {action.due_on && (
                  <span className="ml-auto text-xs text-neutral-500">
                    by{" "}
                    {new Date(action.due_on).toLocaleDateString("en-IN", {
                      day: "numeric",
                      month: "short",
                    })}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {packet.evidence && <EvidenceSection evidence={packet.evidence} packet={packet} />}
    </article>
  );
}

// --------------------------------------------------------------------------- override

function OverrideBanner({ overrides }: { overrides: OverrideNote[] }) {
  if (overrides.length === 0) return null;
  return (
    <section
      aria-label="Cross-domain override"
      className="rounded-xl border-2 border-amber-300 bg-amber-50 p-5 dark:border-amber-700 dark:bg-amber-950/40"
    >
      <h2 className="text-xs font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-200">
        The evidence disagrees with the plan
      </h2>
      {overrides.map((override) => (
        <div key={override.overridden_key} className="mt-3">
          <p className="text-sm leading-relaxed text-amber-950 dark:text-amber-100">
            {override.reason}
          </p>
          <p className="mt-2 font-mono text-xs text-amber-700 dark:text-amber-300">
            overrides {override.overridden_key} ({override.overridden_module}) ·{" "}
            {override.prevailing_evidence.length} pieces of prevailing evidence
          </p>
        </div>
      ))}
      <p className="mt-3 border-t border-amber-200 pt-3 text-xs text-amber-800 dark:border-amber-800 dark:text-amber-300">
        Shown rather than applied silently. You can disagree with this — that is the point of
        putting it in front of you.
      </p>
    </section>
  );
}

// --------------------------------------------------------------------------- pieces

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
        {title}
      </h2>
      {subtitle && <p className="mb-2 mt-0.5 text-xs text-neutral-400">{subtitle}</p>}
      {children}
    </section>
  );
}

function Claims({ claims, showAffected = false }: { claims: Claim[]; showAffected?: boolean }) {
  // FR-804, enforced a second time at the last possible moment.
  const rendered = claims.filter((c) => c.evidence.length > 0);
  if (rendered.length === 0) {
    return (
      <p className="text-sm text-neutral-500">
        Nothing here is supported by evidence we hold, so nothing is claimed.
      </p>
    );
  }
  return (
    <ul className="space-y-2.5">
      {rendered.map((claim, i) => (
        <li key={i} className="flex gap-3">
          <ConfidenceChip value={claim.confidence} className="mt-0.5 shrink-0" />
          <div className="min-w-0">
            <p className="text-sm leading-relaxed">{claim.statement}</p>
            {showAffected && claim.affected && <Affected affected={claim.affected} />}
            <p className="mt-0.5 text-xs text-neutral-400">
              {claim.evidence.length} source{claim.evidence.length === 1 ? "" : "s"}
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}

function Affected({ affected }: { affected: NonNullable<Claim["affected"]> }) {
  const parts: string[] = [];
  if (affected.farmer_ids.length) parts.push(`${affected.farmer_ids.length} farmers`);
  if (affected.area_sqm) {
    parts.push(`${(Number(affected.area_sqm) / 4046.86).toLocaleString("en-IN", { maximumFractionDigits: 0 })} acres`);
  }
  if (affected.quantity_kg) {
    parts.push(`${(Number(affected.quantity_kg) / 1000).toLocaleString("en-IN", { maximumFractionDigits: 0 })} t`);
  }
  if (affected.value_paise) parts.push(formatInr(affected.value_paise));
  if (parts.length === 0) return null;
  return <p className="mt-1 text-xs font-medium text-neutral-600 dark:text-neutral-400">{parts.join(" · ")}</p>;
}

function ActionCard({ action }: { action: PacketAction }) {
  const ladder = (action.expected_impact?.ladder ?? null) as
    | { rung: string; action: string; note?: string }[]
    | null;
  return (
    <div className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
      <div className="flex flex-wrap items-baseline gap-2">
        <h3 className="font-medium">{action.title}</h3>
        <ConfidenceChip value={action.confidence} />
        <span className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-xs text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400">
          {action.recommendation_type.replace(/_/g, " ").toLowerCase()}
        </span>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">
        {action.rationale}
      </p>

      {ladder && <Ladder steps={ladder} />}

      {action.risks?.length > 0 && (
        <Detail label="Risks">
          <ul className="list-disc space-y-0.5 pl-4">
            {action.risks.map((risk, i) => (
              <li key={i}>{risk}</li>
            ))}
          </ul>
        </Detail>
      )}
      {action.alternatives?.length > 0 && (
        <Detail label="Alternatives considered">
          <ul className="list-disc space-y-0.5 pl-4">
            {action.alternatives.map((alt, i) => (
              <li key={i}>{alt}</li>
            ))}
          </ul>
        </Detail>
      )}
    </div>
  );
}

/**
 * The IPM ladder (FR-522, INV-8).
 *
 * Rendered as an ordered ladder rather than a list because the order *is* the safety
 * property: the chemical rung must never read as a peer of the cultural ones.
 */
function Ladder({ steps }: { steps: { rung: string; action: string; note?: string }[] }) {
  const colour: Record<string, string> = {
    immediate: "text-rose-700 dark:text-rose-300",
    cultural: "text-emerald-700 dark:text-emerald-300",
    biological: "text-emerald-700 dark:text-emerald-300",
    chemical: "text-amber-700 dark:text-amber-300",
    monitoring: "text-neutral-500",
  };
  return (
    <ol className="mt-3 space-y-2 border-l-2 border-neutral-200 pl-4 dark:border-neutral-800">
      {steps.map((step, i) => (
        <li key={i} className="text-sm">
          <span className={`font-mono text-xs uppercase ${colour[step.rung] ?? ""}`}>
            {step.rung}
          </span>
          <p className="mt-0.5">{step.action}</p>
          {step.note && <p className="mt-0.5 text-xs text-neutral-500">{step.note}</p>}
        </li>
      ))}
    </ol>
  );
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <details className="mt-2">
      <summary className="cursor-pointer text-xs font-medium text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300">
        {label}
      </summary>
      <div className="mt-1.5 text-xs text-neutral-600 dark:text-neutral-400">{children}</div>
    </details>
  );
}

function ConfidenceSection({ confidence }: { confidence: ConfidenceBlock }) {
  return (
    <Section
      title={SECTION_TITLE.confidence}
      subtitle="What this rests on, and what would make it stronger"
    >
      <div
        className={`rounded-lg border p-4 ${
          confidence.below_floor
            ? "border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950/40"
            : "border-neutral-200 dark:border-neutral-800"
        }`}
      >
        <div className="flex items-center gap-3">
          <span className="text-2xl font-semibold tabular-nums">
            {Math.round(confidence.overall * 100)}%
          </span>
          <span className="text-sm text-neutral-500">overall</span>
          {confidence.below_floor && (
            <span className="ml-auto rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-900 dark:text-amber-100">
              below the confidence floor
            </span>
          )}
        </div>

        {Object.keys(confidence.per_section).length > 0 && (
          <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-600 dark:text-neutral-400">
            {Object.entries(confidence.per_section).map(([module, value]) => (
              <li key={module}>
                {module.replace(/_intelligence$/, "")}{" "}
                <span className="font-medium tabular-nums">{Math.round(value * 100)}%</span>
              </li>
            ))}
          </ul>
        )}

        {confidence.what_would_raise_it.length > 0 && (
          <div className="mt-4">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
              What would raise it
            </h3>
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-sm">
              {confidence.what_would_raise_it.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </div>
        )}

        {confidence.degraded_inputs.length > 0 && (
          <Detail label={`Known gaps (${confidence.degraded_inputs.length})`}>
            <ul className="list-disc space-y-0.5 pl-4">
              {confidence.degraded_inputs.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </Detail>
        )}
      </div>
    </Section>
  );
}

function EvidenceSection({
  evidence,
  packet,
}: {
  evidence: EvidenceRef[];
  packet: Partial<Packet>;
}) {
  const byKind = evidence.reduce<Record<string, number>>((acc, ref) => {
    acc[ref.kind] = (acc[ref.kind] ?? 0) + 1;
    return acc;
  }, {});
  return (
    <Section
      title={SECTION_TITLE.evidence}
      subtitle="Frozen at generation — this answer stays explainable"
    >
      <div className="rounded-lg border border-neutral-200 p-4 text-sm dark:border-neutral-800">
        <p className="text-neutral-600 dark:text-neutral-400">
          {evidence.length} sources ·{" "}
          {Object.entries(byKind)
            .map(([kind, n]) => `${n} ${kind.replace(/_/g, " ")}`)
            .join(", ")}
        </p>
        {packet.snapshot_id && (
          <p className="mt-2 font-mono text-xs break-all text-neutral-500">
            snapshot {packet.snapshot_id}
          </p>
        )}
        {packet.generated_at && (
          <p className="mt-1 text-xs text-neutral-500">
            Generated{" "}
            {new Date(packet.generated_at).toLocaleString("en-IN", {
              timeZone: "Asia/Kolkata",
            })}{" "}
            by {packet.model_id} · prompt {packet.prompt_version}
          </p>
        )}
        <Detail label="List the sources">
          <ul className="space-y-0.5">
            {evidence.slice(0, 40).map((ref) => (
              <li key={ref.id} className="flex gap-2">
                <span className="shrink-0 font-mono text-neutral-400">{ref.kind.slice(0, 4)}</span>
                <span className="truncate">{ref.label}</span>
              </li>
            ))}
          </ul>
        </Detail>
      </div>
    </Section>
  );
}
