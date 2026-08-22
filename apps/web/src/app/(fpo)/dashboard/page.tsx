/**
 * FPO dashboard — UI-01, the ten cards.
 *
 * The design constraint worth respecting: this is what a CEO sees *before* they think. It
 * has to survive a glance. Anything that needs explaining belongs behind the assistant,
 * which is where the actual reasoning happens.
 */

import Link from "next/link";

import { ApiError, api, type Card } from "@/lib/api";
import { ConfidenceChip, DemoDataBadge } from "@/components/invariants";

export const dynamic = "force-dynamic";

function formatValue(card: Card): string {
  if (card.value === null || card.value === undefined) return "—";
  if (typeof card.value === "number") {
    if (card.unit === "₹") {
      return `₹${card.value.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
    }
    return card.value.toLocaleString("en-IN", { maximumFractionDigits: 1 });
  }
  return String(card.value);
}

function StatCard({ card }: { card: Card }) {
  const body = (
    <div className="flex h-full flex-col justify-between rounded-xl border border-neutral-200 p-4 transition-colors hover:border-neutral-400 dark:border-neutral-800 dark:hover:border-neutral-600">
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-neutral-500">
          {card.label}
        </span>
        {card.confidence !== null && <ConfidenceChip value={card.confidence} />}
      </div>
      <div className="mt-3">
        <span className="text-2xl font-semibold tabular-nums">{formatValue(card)}</span>
        {card.unit && card.unit !== "₹" && (
          <span className="ml-1 text-sm text-neutral-500">{card.unit}</span>
        )}
      </div>
      {card.detail && (
        <p className="mt-1 line-clamp-2 text-xs text-neutral-500 dark:text-neutral-400">
          {card.detail}
        </p>
      )}
    </div>
  );

  return card.href ? (
    <Link href={card.href} className="block h-full">
      {body}
    </Link>
  ) : (
    body
  );
}

export default async function DashboardPage() {
  let data;
  try {
    data = await api.dashboard();
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 0;
    return (
      <main className="mx-auto max-w-5xl px-6 py-12">
        <h1 className="text-2xl font-semibold">FPO dashboard</h1>
        <p className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200">
          {status === 403
            ? "This view is for organization staff. A farmer account sees their own farm instead — the boundary is enforced by the API, not by hiding this page."
            : "Could not reach the API. Run `make api`, and set AGRI_DEV_TOKEN for an authenticated view."}
        </p>
      </main>
    );
  }

  const { organization, cards } = data;

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-8">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">{organization.name}</h1>
          {organization.is_synthetic && <DemoDataBadge />}
        </div>
        <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
          {organization.type} · {organization.district}, {organization.state}
        </p>
      </header>

      <section
        aria-label="Organization at a glance"
        className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
      >
        {cards.map((card) => (
          <StatCard key={card.key} card={card} />
        ))}
      </section>

      <p className="mt-8 text-xs text-neutral-500 dark:text-neutral-400">
        Every figure here is synthetic demonstration data drawn from a real district profile.
        Market prices and weather come from Agmarknet and Open-Meteo and are real. Generated{" "}
        {new Date(data.generated_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}.
      </p>
    </main>
  );
}
