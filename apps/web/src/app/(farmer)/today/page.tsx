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
import { ConfidenceChip, formatMass } from "@/components/invariants";
import { translator } from "@/lib/i18n";
import { currentLocale } from "@/lib/locale";

export const dynamic = "force-dynamic";

export default async function TodayPage() {
  const t = translator(await currentLocale());
  let data;
  try {
    data = await api.farmerToday();
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 0;
    return (
      <main className="mx-auto max-w-2xl px-5 py-10">
        <p className="rounded-md border border-accent/40 bg-accent/[0.06] p-4 text-[15px] leading-relaxed text-foreground/85">
          {status === 403
            ? "This view is for a farmer account. Organization staff have the FPO console — the two see different data by design (INV-5)."
            : t("today.unreachable")}
        </p>
      </main>
    );
  }

  const { farmer, crops, lot_contributions: contributions } = data;

  return (
    <main className="mx-auto max-w-2xl px-5 py-8">
      <header className="mb-8">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="title-section text-[2rem]">{farmer.name}</h1>
        </div>
        <p className="mt-1.5 text-[15px] text-muted-foreground">
          {[farmer.village, farmer.block].filter(Boolean).join(" · ")}
        </p>
      </header>

      <section className="mb-8">
        <h2 className="eyebrow mb-3">{t("today.myCrops")}</h2>
        {crops.length === 0 ? (
          <p className="panel text-[15px] text-muted-foreground">
            {t("today.noCrop")}
          </p>
        ) : (
          <ul className="space-y-3">
            {crops.map((crop) => (
              <li key={crop.id} className="panel">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="font-serif text-[21px] tracking-tight text-primary">
                    {crop.crop}
                  </span>
                  <span className="text-sm text-muted-foreground">{crop.variety}</span>
                  <span className="ml-auto tabular-nums">
                    <span className="font-serif text-lg text-primary">
                      {crop.area_acres.toFixed(2)}
                    </span>
                    <span className="ml-1 text-sm text-muted-foreground">{t("today.acres")}</span>
                  </span>
                </div>

                {crop.health_pct != null ? (
                  <p className="mt-3 flex flex-wrap items-center gap-2 text-[15px]">
                    <span>
                      {t("today.cropHealth")}{" "}
                      <strong className="font-serif text-lg tabular-nums text-primary">
                        {Math.round(crop.health_pct)}%
                      </strong>
                    </span>
                    {crop.health_confidence != null && (
                      <ConfidenceChip value={crop.health_confidence} />
                    )}
                    {crop.health_observed_at && (
                      <span className="font-mono text-xs text-muted-foreground">
                        {new Date(crop.health_observed_at).toLocaleDateString("en-IN", {
                          day: "numeric",
                          month: "short",
                        })}
                      </span>
                    )}
                  </p>
                ) : (
                  <p className="mt-3 flex items-center gap-2 text-[15px] text-muted-foreground">
                    <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
                    {t("today.noVisit")}
                  </p>
                )}

                {crop.expected_harvest && (
                  <p className="mt-2 text-[15px] text-muted-foreground">
                    {t("today.expectedHarvest")}{" "}
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
          <h2 className="eyebrow mb-3">{t("today.givenToCollective")}</h2>
          <ul className="panel p-0">
            {contributions.map((item, i) => (
              <li
                key={i}
                className="flex flex-wrap items-baseline gap-3 border-b border-border/60 px-5 py-3.5 last:border-0"
              >
                <span className="font-medium">{item.crop}</span>
                <span className="font-serif text-lg tabular-nums text-primary">
                  {formatMass(item.quantity_kg)}
                </span>
                {item.grade && (
                  <span className="text-sm text-muted-foreground">
                    {t("today.grade")} {item.grade}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="panel bg-muted/50 text-[15px] leading-relaxed text-muted-foreground">
        {data.boundary_note}
      </p>
    </main>
  );
}
