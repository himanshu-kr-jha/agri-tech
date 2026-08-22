/**
 * Phase 0 gate (docs/MVP-SCOPE.md §5): prove the API → UI path works end to end and that the
 * invariant components render. Replaced by the real FPO console in Phase 1.
 */

import {
  ConfidenceChip,
  DemoDataBadge,
  DiscrepancyBadge,
  ProvenancePopover,
  formatArea,
  formatInr,
  formatMass,
} from "@/components/invariants";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Health {
  status: string;
  environment: string;
  use_fixtures: boolean;
  checks: Record<string, string>;
}

async function getHealth(): Promise<Health | null> {
  try {
    const res = await fetch(`${API}/api/v1/health`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as Health;
  } catch {
    return null;
  }
}

export default async function Home() {
  const health = await getHealth();

  return (
    <main className="mx-auto max-w-3xl px-6 py-12 font-sans">
      <header className="mb-10">
        <h1 className="text-3xl font-semibold tracking-tight">AgriVardhak</h1>
        <p className="mt-2 text-neutral-600 dark:text-neutral-400">
          AI decision &amp; orchestration platform for farmer collectives — Prayagraj, Uttar
          Pradesh.
        </p>
      </header>

      <section className="mb-10 rounded-xl border border-neutral-200 p-5 dark:border-neutral-800">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Phase 0 — foundation
        </h2>
        {health ? (
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <dt className="text-neutral-500">API</dt>
            <dd className="font-medium">{health.status}</dd>
            {Object.entries(health.checks).map(([name, value]) => (
              <div key={name} className="contents">
                <dt className="text-neutral-500">{name}</dt>
                <dd className="font-mono text-xs">{value}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="text-sm text-rose-600 dark:text-rose-400">
            API unreachable at {API} — run <code className="font-mono">make api</code>.
          </p>
        )}
      </section>

      <section className="rounded-xl border border-neutral-200 p-5 dark:border-neutral-800">
        <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Invariant components <DemoDataBadge />
        </h2>
        <p className="mb-5 text-sm text-neutral-600 dark:text-neutral-400">
          Every AI-derived number in this product renders through these. A bare number is a
          review finding, not a style choice.
        </p>

        <ul className="space-y-4 text-sm">
          <li className="flex flex-wrap items-center gap-2">
            <span className="w-40 shrink-0 text-neutral-500">Crop health</span>
            <ProvenancePopover
              provenance={{
                sourceType: "FIELD_OFFICER",
                observedAt: "2026-08-15T00:00:00Z",
                confidence: 0.94,
                verificationStatus: "VERIFIED",
              }}
            >
              82%
            </ProvenancePopover>
          </li>

          <li className="flex flex-wrap items-center gap-2">
            <span className="w-40 shrink-0 text-neutral-500">Crop health (AI)</span>
            <ProvenancePopover
              provenance={{
                sourceType: "AI_INFERENCE",
                observedAt: "2026-06-02T00:00:00Z",
                confidence: 0.61,
                verificationStatus: "UNVERIFIED",
                isStale: true,
              }}
            >
              82%
            </ProvenancePopover>
            <span className="text-xs text-neutral-500">
              — same number, materially less trustworthy
            </span>
          </li>

          <li className="flex flex-wrap items-center gap-2">
            <span className="w-40 shrink-0 text-neutral-500">Plot area</span>
            <span>{formatArea(7284.3)}</span>
            <DiscrepancyBadge />
            <span className="text-xs text-neutral-500">
              — farmer 2.0 ac / record 1.6 / officer 1.8; no value chosen
            </span>
          </li>

          <li className="flex flex-wrap items-center gap-2">
            <span className="w-40 shrink-0 text-neutral-500">Recommended support</span>
            <span>{formatInr(3_200_000)}</span>
            <ConfidenceChip value={0.72} />
          </li>

          <li className="flex flex-wrap items-center gap-2">
            <span className="w-40 shrink-0 text-neutral-500">Expected production</span>
            <span>{formatMass(420_000)}</span>
            <ConfidenceChip value={0.83} />
          </li>
        </ul>
      </section>
    </main>
  );
}
