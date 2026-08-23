/**
 * Lots and buyer offers — M15d, FR-542, FR-543.
 *
 * The headline price is shown small and the deductions are shown at all, because the gap
 * between them is the whole finding: a buyer offering ₹19.50/kg 180 km away can be worth
 * less than one offering ₹18 next door, and an FPO that only ever sees headline prices has
 * no way to know that.
 */

import { ApiError, api } from "@/lib/api";
import { DemoDataBadge, formatMass } from "@/components/invariants";

export const dynamic = "force-dynamic";

export default async function MarketPage() {
  let data;
  try {
    data = await api.market();
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 0;
    return (
      <main className="mx-auto max-w-4xl px-6 py-12">
        <h1 className="text-2xl font-semibold">Market</h1>
        <p className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200">
          {status === 403
            ? "Buyer negotiations are organization-internal (INV-5)."
            : "Could not reach the API. Run `make api`."}
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <header className="mb-6">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">Lots and offers</h1>
          <DemoDataBadge />
        </div>
        <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
          Buyers and their offers are demonstration data. The mandi prices they are anchored
          to are real, from Agmarknet.
        </p>
      </header>

      <div className="space-y-4">
        {data.lots.map((lot) => (
          <section
            key={lot.id}
            className="rounded-xl border border-neutral-200 p-4 dark:border-neutral-800"
          >
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <h2 className="font-medium">{lot.crop ?? lot.label}</h2>
              <span className="tabular-nums">{formatMass(lot.quantity_kg)}</span>
              {lot.grade && <span className="text-xs text-neutral-500">Grade {lot.grade}</span>}
              <span className="text-xs text-neutral-500">
                {lot.contributors} contributing farmers
              </span>
              {lot.ready_date && (
                <span className="ml-auto text-xs text-neutral-500">
                  ready{" "}
                  {new Date(lot.ready_date).toLocaleDateString("en-IN", {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })}
                </span>
              )}
            </div>

            {lot.offers.length === 0 ? (
              <p className="mt-3 text-sm text-neutral-500">
                No offers on record for this crop. That is a gap, not a market signal.
              </p>
            ) : (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-neutral-200 text-left text-xs uppercase tracking-wide text-neutral-500 dark:border-neutral-800">
                    <tr>
                      <th className="py-2 pr-3 font-medium">Buyer</th>
                      <th className="py-2 pr-3 text-right font-medium">Offer</th>
                      <th className="py-2 pr-3 text-right font-medium">Distance</th>
                      <th className="py-2 pr-3 text-right font-medium">Pays in</th>
                      <th className="py-2 text-right font-medium">Rejects</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...lot.offers]
                      .sort((a, b) => (b.price_paise_per_kg ?? 0) - (a.price_paise_per_kg ?? 0))
                      .map((offer, i) => (
                        <tr
                          key={i}
                          className="border-b border-neutral-100 last:border-0 dark:border-neutral-900"
                        >
                          <td className="py-2 pr-3">{offer.buyer ?? "—"}</td>
                          <td className="py-2 pr-3 text-right tabular-nums">
                            {offer.price_paise_per_kg != null
                              ? `₹${(offer.price_paise_per_kg / 100).toFixed(2)}/kg`
                              : "—"}
                          </td>
                          <td className="py-2 pr-3 text-right tabular-nums text-neutral-500">
                            {offer.distance_km != null ? `${offer.distance_km} km` : "—"}
                          </td>
                          <td className="py-2 pr-3 text-right tabular-nums text-neutral-500">
                            {offer.payment_terms_days != null ? `${offer.payment_terms_days} d` : "—"}
                          </td>
                          <td className="py-2 text-right tabular-nums text-neutral-500">
                            {offer.rejection_rate != null
                              ? `${Math.round(offer.rejection_rate * 100)}%`
                              : "no history"}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
                <p className="mt-2 text-xs text-neutral-500">
                  The headline price is not what the collective banks. Ask the assistant to
                  score these — distance, payment delay and rejection history all come off
                  first, and rejection history is usually the largest of the three.
                </p>
              </div>
            )}
          </section>
        ))}
      </div>
    </main>
  );
}
