/**
 * FPO dashboard — UI-01, the ten cards.
 *
 * The design constraint worth respecting: this is what a CEO sees *before* they think. It
 * has to survive a glance. Anything that needs explaining belongs behind the assistant,
 * which is where the actual reasoning happens.
 */

import Link from "next/link";

import { ApiError, api, type Briefing, type Card } from "@/lib/api";
import { ConfidenceChip, DemoDataBadge, formatValue } from "@/components/invariants";

export const dynamic = "force-dynamic";

function formatCardValue(card: Card): string {
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
        <span className="text-2xl font-semibold tabular-nums">{formatCardValue(card)}</span>
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

/**
 * The briefing, above the cards.
 *
 * It leads with what is waiting on a human because that is the only thing on this page that
 * *stops* if it is ignored. Ten healthy totals underneath are context; an unapproved
 * recommendation is work the collective has already paid for and is not yet getting.
 */
function BriefingPanel({ briefing }: { briefing: Briefing }) {
  if (briefing.quiet) {
    return (
      <section className="mb-8 rounded-xl border border-neutral-200 p-4 text-sm text-neutral-600 dark:border-neutral-800 dark:text-neutral-400">
        Nothing needs a decision today. That is a real answer, not an empty state — the
        briefing stays short so that the day it is long, you read it.
      </section>
    );
  }
  return (
    <section aria-label="Briefing" className="mb-8 space-y-4">
      {briefing.needs_decision.length > 0 && (
        <BriefingGroup
          title="Waiting on you"
          subtitle="Nothing here has happened yet"
          items={briefing.needs_decision}
          emphasis
        />
      )}
      {briefing.closing_soon.length > 0 && (
        <BriefingGroup title="Closing soon" items={briefing.closing_soon} />
      )}
      {briefing.watch.length > 0 && (
        <BriefingGroup title="Worth watching" items={briefing.watch} />
      )}
      {briefing.data_health.length > 0 && (
        <BriefingGroup title="Data health" items={briefing.data_health} />
      )}
    </section>
  );
}

function BriefingGroup({
  title,
  subtitle,
  items,
  emphasis = false,
}: {
  title: string;
  subtitle?: string;
  items: Briefing["needs_decision"];
  emphasis?: boolean;
}) {
  return (
    <div
      className={`rounded-xl border p-4 ${
        emphasis
          ? "border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950/40"
          : "border-neutral-200 dark:border-neutral-800"
      }`}
    >
      <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
        {title}
      </h2>
      {subtitle && <p className="mt-0.5 text-xs text-neutral-400">{subtitle}</p>}
      <ul className="mt-2 space-y-1.5">
        {items.map((item, i) => (
          <li key={i} className="text-sm">
            {item.href ? (
              <Link href={item.href} className="font-medium underline-offset-2 hover:underline">
                {item.headline}
              </Link>
            ) : (
              <span className="font-medium">{item.headline}</span>
            )}
            {item.detail && (
              <span className="ml-2 text-xs text-neutral-500">{item.detail}</span>
            )}
            {item.value_paise != null && item.unit !== "paise_per_kg" && (
              <span className="ml-2 text-xs tabular-nums text-neutral-500">
                {formatValue(item.value_paise, item.unit ?? null)}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default async function DashboardPage() {
  let data;
  let briefing: Briefing | null = null;
  try {
    data = await api.dashboard();
    briefing = await api.briefing().catch(() => null);
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

      {briefing && <BriefingPanel briefing={briefing} />}

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
