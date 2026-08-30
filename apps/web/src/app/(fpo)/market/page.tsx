/**
 * Lots and buyer offers — M15d, FR-542, FR-543.
 *
 * The headline price is shown small and the deductions are shown at all, because the gap
 * between them is the whole finding: a buyer offering ₹19.50/kg 180 km away can be worth
 * less than one offering ₹18 next door, and an FPO that only ever sees headline prices has
 * no way to know that.
 */

import { ApiError, api } from "@/lib/api";
import { formatMass } from "@/components/invariants";
import { EmptyState, ErrorPanel, PageHeader, Panel, PanelHeader } from "@/components/ui";
import { translator } from "@/lib/i18n";
import { currentLocale } from "@/lib/locale";

export const dynamic = "force-dynamic";

export default async function MarketPage() {
  const t = translator(await currentLocale());
  let data;
  try {
    data = await api.market();
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 0;
    return (
      <main className="px-6 py-10 md:px-10">
        <PageHeader eyebrow={t("con.market.eyebrow")} title={t("con.market.title")} />
        <ErrorPanel title={status === 403 ? "Organization-internal" : "API unreachable"}>
          {status === 403
            ? "Buyer negotiations are organization-internal (INV-5)."
            : "Could not reach the API. Run `make api`."}
        </ErrorPanel>
      </main>
    );
  }

  return (
    <main className="max-w-6xl px-6 py-10 md:px-10">
      <PageHeader
        eyebrow={t("con.market.eyebrow")}
        title={t("con.market.h1")}
        subtitle={t("con.market.sub")}
      />

      <div className="space-y-4">
        {data.lots.map((lot) => (
          <Panel key={lot.id}>
            <PanelHeader
              eyebrow={`${lot.contributors} contributing farmers`}
              title={
                <span className="flex flex-wrap items-baseline gap-x-3">
                  {lot.crop ?? lot.label}
                  <span className="font-sans text-sm font-normal tabular-nums text-muted-foreground">
                    {formatMass(lot.quantity_kg)}
                  </span>
                  {lot.grade && (
                    <span className="font-sans text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                      Grade {lot.grade}
                    </span>
                  )}
                </span>
              }
              meta={
                lot.ready_date
                  ? `Ready ${new Date(lot.ready_date).toLocaleDateString("en-IN", {
                      day: "numeric",
                      month: "short",
                      year: "numeric",
                    })}`
                  : undefined
              }
            />

            {lot.offers.length === 0 ? (
              <EmptyState>
                No offers on record for this crop. That is a gap, not a market signal.
              </EmptyState>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border/70 text-left">
                      {["Buyer", "Offer", "Distance", "Pays in", "Rejects"].map((h, i) => (
                        <th
                          key={h}
                          className={`pb-2.5 pr-4 text-[10px] font-medium uppercase tracking-[0.16em] text-muted-foreground ${
                            i === 0 ? "" : "text-right"
                          }`}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[...lot.offers]
                      .sort((a, b) => (b.price_paise_per_kg ?? 0) - (a.price_paise_per_kg ?? 0))
                      .map((offer, i) => (
                        <tr key={i} className="border-b border-border/50 last:border-0">
                          <td className="py-3 pr-4 text-foreground">{offer.buyer ?? "—"}</td>
                          <td className="py-3 pr-4 text-right font-serif text-[15px] tabular-nums text-primary">
                            {offer.price_paise_per_kg != null
                              ? `₹${(offer.price_paise_per_kg / 100).toFixed(2)}/kg`
                              : "—"}
                          </td>
                          <td className="py-3 pr-4 text-right font-mono text-xs tabular-nums text-muted-foreground">
                            {offer.distance_km != null ? `${offer.distance_km} km` : "—"}
                          </td>
                          <td className="py-3 pr-4 text-right font-mono text-xs tabular-nums text-muted-foreground">
                            {offer.payment_terms_days != null
                              ? `${offer.payment_terms_days} d`
                              : "—"}
                          </td>
                          <td className="py-3 text-right font-mono text-xs tabular-nums text-muted-foreground">
                            {offer.rejection_rate != null
                              ? `${Math.round(offer.rejection_rate * 100)}%`
                              : "no history"}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
                <p className="mt-4 border-t border-border/60 pt-3 text-xs leading-relaxed text-muted-foreground">
                  The headline price is not what the collective banks. Ask the assistant to
                  score these — distance, payment delay and rejection history all come off
                  first, and rejection history is usually the largest of the three.
                </p>
              </div>
            )}
          </Panel>
        ))}
      </div>
    </main>
  );
}
