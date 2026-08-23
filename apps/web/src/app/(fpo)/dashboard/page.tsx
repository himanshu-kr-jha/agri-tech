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
import { IconAlert, IconArrowUpRight, IconClock, IconDatabase, IconEye } from "@/components/icons";
import { Chip, EmptyState, ErrorPanel, KpiTile, PageHeader, Panel, PanelHeader } from "@/components/ui";

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
  const tile = (
    <KpiTile
      label={card.label}
      value={formatCardValue(card)}
      // "₹" is already inside the formatted value; showing it again as a suffix would read
      // as a currency-per-currency unit.
      unit={card.unit && card.unit !== "₹" ? card.unit : null}
      caption={card.detail}
      chip={card.confidence !== null ? <ConfidenceChip value={card.confidence} /> : null}
    />
  );

  return card.href ? (
    <Link href={card.href} className="block h-full">
      {tile}
    </Link>
  ) : (
    tile
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
      <Panel className="mb-8" aria-label="Briefing">
        <PanelHeader eyebrow="Briefing" title="Nothing needs a decision today" />
        <EmptyState>
          That is a real answer, not an empty state — the briefing stays short so that the day
          it is long, you read it.
        </EmptyState>
      </Panel>
    );
  }

  return (
    <section aria-label="Briefing" className="mb-8 grid gap-4 lg:grid-cols-2">
      {briefing.needs_decision.length > 0 && (
        <BriefingGroup
          eyebrow="Waiting on you"
          title="Nothing here has happened yet"
          items={briefing.needs_decision}
          icon={<IconAlert size={15} />}
          emphasis
        />
      )}
      {briefing.closing_soon.length > 0 && (
        <BriefingGroup
          eyebrow="Closing soon"
          title="Windows about to shut"
          items={briefing.closing_soon}
          icon={<IconClock size={15} />}
        />
      )}
      {briefing.watch.length > 0 && (
        <BriefingGroup
          eyebrow="Worth watching"
          title="Moving, not yet actionable"
          items={briefing.watch}
          icon={<IconEye size={15} />}
        />
      )}
      {briefing.data_health.length > 0 && (
        <BriefingGroup
          eyebrow="Data health"
          title="What the answers rest on"
          items={briefing.data_health}
          icon={<IconDatabase size={15} />}
        />
      )}
    </section>
  );
}

function BriefingGroup({
  eyebrow,
  title,
  items,
  icon,
  emphasis = false,
}: {
  eyebrow: string;
  title: string;
  items: Briefing["needs_decision"];
  icon: React.ReactNode;
  emphasis?: boolean;
}) {
  return (
    <div
      className={`panel ${
        emphasis ? "border-accent/45 shadow-[inset_2px_0_0_0_hsl(var(--accent))]" : ""
      }`}
    >
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <p className="eyebrow-sm">{eyebrow}</p>
          <h2 className="title-panel mt-0.5">{title}</h2>
        </div>
        <span className="pt-4 text-muted-foreground/70">{icon}</span>
      </div>
      <ul>
        {items.map((item, i) => (
          <li key={i} className="border-b border-border/60 py-3 last:border-0 last:pb-0">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              {item.href ? (
                <Link
                  href={item.href}
                  className="text-sm font-medium text-foreground underline-offset-4 hover:underline"
                >
                  {item.headline}
                </Link>
              ) : (
                <span className="text-sm font-medium text-foreground">{item.headline}</span>
              )}
              {item.value_paise != null && item.unit !== "paise_per_kg" && (
                <span className="font-mono text-xs tabular-nums text-muted-foreground">
                  {formatValue(item.value_paise, item.unit ?? null)}
                </span>
              )}
            </div>
            {item.detail && (
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{item.detail}</p>
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
      <main className="px-6 py-10 md:px-10">
        <PageHeader eyebrow="FPO Command Centre" title="Dashboard" />
        <ErrorPanel title={status === 403 ? "Not your view" : "API unreachable"}>
          {status === 403
            ? "This view is for organization staff. A farmer account sees their own farm instead — the boundary is enforced by the API, not by hiding this page."
            : "Could not reach the API. Run `make api`, and set AGRI_DEV_TOKEN for an authenticated view."}
        </ErrorPanel>
      </main>
    );
  }

  const { organization, cards } = data;
  // The *real* pending count, from the card the API computes — not
  // `briefing.needs_decision.length`, which is a truncated headline list. Using the list
  // length put "5 awaiting approval" in the header beside a tile reading 11, on the same
  // screen, both claiming to count the same thing.
  const pendingCard = cards.find((c) => c.key === "pending_actions");
  const pending = typeof pendingCard?.value === "number" ? pendingCard.value : 0;

  return (
    <main className="px-6 py-10 md:px-10">
      <PageHeader
        eyebrow="FPO Command Centre"
        title={
          <>
            What the collective
            <br />
            looks like today
          </>
        }
        subtitle={`Members, land, crops and open decisions for ${organization.name} — one layer, read before you act.`}
        aside={
          <>
            {organization.is_synthetic && <DemoDataBadge />}
            <Chip tone={pending > 0 ? "accent" : "neutral"}>
              {pending > 0
                ? `${pending} awaiting approval`
                : `${organization.district}, ${organization.state}`}
            </Chip>
          </>
        }
      />

      <section
        aria-label="Organization at a glance"
        className="mb-8 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
      >
        {cards.map((card) => (
          <StatCard key={card.key} card={card} />
        ))}
      </section>

      {briefing && <BriefingPanel briefing={briefing} />}

      <Panel className="flex flex-wrap items-center justify-between gap-4">
        <p className="max-w-2xl text-xs leading-relaxed text-muted-foreground">
          Every figure here is synthetic demonstration data drawn from a real district profile.
          Market prices and weather come from Agmarknet and Open-Meteo and are real. Generated{" "}
          <span className="font-mono">
            {new Date(data.generated_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}
          </span>
          .
        </p>
        <Link href="/decisions" className="btn-ghost">
          Open decisions
          <IconArrowUpRight size={14} />
        </Link>
      </Panel>
    </main>
  );
}
