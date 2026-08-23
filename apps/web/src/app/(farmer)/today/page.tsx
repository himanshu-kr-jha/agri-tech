/**
 * The farmer's view — M16, UI-05, UI-06, INV-5.
 *
 * What one farmer sees about their own farm. Bilingual labels rather than a language toggle:
 * a toggle is a decision to make before you can read anything, and on a shared phone the
 * setting is never the one you left it on.
 *
 * The boundary is stated on the page, not just enforced behind it. A farmer who can see that
 * the collective's negotiations are deliberately not shown has a reason to trust that their
 * own data is treated the same way in the other direction — which is the actual product here
 * (INV-9).
 */

import { ApiError, api } from "@/lib/api";
import { ConfidenceChip, DemoDataBadge, formatMass } from "@/components/invariants";

export const dynamic = "force-dynamic";

export default async function TodayPage() {
  let data;
  try {
    data = await api.farmerToday();
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 0;
    return (
      <main className="mx-auto max-w-2xl px-5 py-10">
        <p className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
          {status === 403
            ? "This view is for a farmer account. Organization staff have the FPO console — the two see different data by design (INV-5)."
            : "Could not reach the API. Run `make api`, and set AGRI_DEV_TOKEN to a farmer token to see this view."}
        </p>
      </main>
    );
  }

  const { farmer, crops, lot_contributions: contributions } = data;

  return (
    <main className="mx-auto max-w-2xl px-5 py-8">
      <header className="mb-6">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">{farmer.name}</h1>
          {farmer.is_synthetic && <DemoDataBadge />}
        </div>
        <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
          {[farmer.village, farmer.block].filter(Boolean).join(" · ")}
        </p>
      </header>

      <section className="mb-8">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
          मेरी फ़सल · My crops
        </h2>
        {crops.length === 0 ? (
          <p className="rounded-lg border border-neutral-200 p-4 text-sm text-neutral-500 dark:border-neutral-800">
            कोई चालू फ़सल नहीं · No crop currently growing.
          </p>
        ) : (
          <ul className="space-y-3">
            {crops.map((crop) => (
              <li
                key={crop.id}
                className="rounded-xl border border-neutral-200 p-4 dark:border-neutral-800"
              >
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="text-lg font-medium">{crop.crop}</span>
                  <span className="text-sm text-neutral-500">{crop.variety}</span>
                  <span className="ml-auto tabular-nums">{crop.area_acres.toFixed(2)} एकड़</span>
                </div>

                {crop.health_pct != null ? (
                  <p className="mt-2 flex flex-wrap items-center gap-2 text-sm">
                    <span>
                      फ़सल की स्थिति · Crop health{" "}
                      <strong className="tabular-nums">{Math.round(crop.health_pct)}%</strong>
                    </span>
                    {crop.health_confidence != null && (
                      <ConfidenceChip value={crop.health_confidence} />
                    )}
                    {crop.health_observed_at && (
                      <span className="text-xs text-neutral-500">
                        {new Date(crop.health_observed_at).toLocaleDateString("en-IN", {
                          day: "numeric",
                          month: "short",
                        })}
                      </span>
                    )}
                  </p>
                ) : (
                  <p className="mt-2 text-sm text-amber-700 dark:text-amber-300">
                    अभी तक कोई जाँच नहीं · No field visit recorded yet.
                  </p>
                )}

                {crop.expected_harvest && (
                  <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
                    कटाई · Expected harvest{" "}
                    {new Date(crop.expected_harvest).toLocaleDateString("en-IN", {
                      day: "numeric",
                      month: "long",
                    })}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {contributions.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
            समिति को दिया · Given to the collective
          </h2>
          <ul className="divide-y divide-neutral-100 rounded-xl border border-neutral-200 dark:divide-neutral-900 dark:border-neutral-800">
            {contributions.map((item, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-3 px-4 py-3">
                <span className="font-medium">{item.crop}</span>
                <span className="tabular-nums">{formatMass(item.quantity_kg)}</span>
                {item.grade && (
                  <span className="text-sm text-neutral-500">श्रेणी {item.grade}</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="rounded-lg border border-neutral-200 bg-neutral-50 p-4 text-sm text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-400">
        {data.boundary_note}
      </p>
    </main>
  );
}
