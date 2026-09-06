/**
 * Impact panel — M20, FR-1201…1203, SAF-12.
 *
 * The honest version of a metrics dashboard. It shows what could *not* be attributed as
 * prominently as what could, because a panel that reports only successes is measuring the
 * selection, not the impact — and any FPO board that has seen one vendor dashboard already
 * knows that.
 *
 * On a fresh install every number here is zero, and that is the correct thing to show. The
 * loop closes when advice is followed and outcomes are recorded; claiming impact before then
 * would be the exact dishonesty this screen exists to avoid.
 */

import { ApiError, api } from "@/lib/api";
import { EmptyState, ErrorPanel, KpiTile, PageHeader, Panel, PanelHeader } from "@/components/ui";
import { translator, type StringKey } from "@/lib/i18n";
import { currentLocale } from "@/lib/locale";
import { term, recordText } from "@/lib/localized-data";

export const dynamic = "force-dynamic";

const STRENGTH_NOTE: Record<string, StringKey> = {
  HIGH: "Followed faithfully, moved materially, no confounder we track",
  MODERATE: "Followed and moved, but less decisively",
  UNCERTAIN: "Moved inside ordinary variation, or had no baseline",
  CONFOUNDED: "Something else would explain it equally well",
};

export default async function ImpactPage() {
  const locale = await currentLocale();
  const t = translator(locale);
  let data;
  try {
    data = await api.impact();
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 0;
    return <main className="px-6 py-10 md:px-10">
      <PageHeader eyebrow={t("con.impact.eyebrow")} title={t("con.impact.title")} />
      <ErrorPanel title={t(status === 403 ? "Organization-internal" : "API unreachable")}>{t(status === 403 ? "Organization-internal." : "Could not reach the API. Run `make api`.")}</ErrorPanel>
    </main>;
  }

  const nothingYet = data.interventions === 0;
  return <main className="max-w-5xl px-6 py-10 md:px-10">
    <PageHeader eyebrow={t("con.impact.eyebrow")} title={t("con.impact.h1")} subtitle={t("con.impact.sub")} />
    {nothingYet ? <Panel>
      <PanelHeader eyebrow={t("Nothing recorded")} title={t("No impact to report yet")} />
      <p className="text-sm leading-relaxed text-foreground/85">{t("Impact is measured from recommendations that were approved, executed, and whose outcomes were recorded against a baseline.")}</p>
      <EmptyState>{t("An empty panel is the correct answer here. Filling it with activity counts — how many questions were asked, how many packets generated — would be reporting our own busyness as the collective's benefit.")}</EmptyState>
    </Panel> : <>
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiTile label={t("Actions executed")} value={data.interventions} />
        <KpiTile label={t("Attributed")} value={data.attributions} />
        <KpiTile label={t("Could not attribute")} value={data.unattributable} caption={t("not followed, or followed too loosely to score")} />
        <KpiTile label={t("Forecast error")} value={data.mean_absolute_error != null ? `${Math.round(data.mean_absolute_error * 100)}%` : "—"} caption={t("{count} scored", { count: data.predictions_scored })} />
      </section>
      <Panel className="mt-4">
        <PanelHeader eyebrow={t("Confidence in the claim")} title={t("Attribution strength")} meta={t("{count} attributed", { count: data.attributions })} />
        <ul>{Object.entries(STRENGTH_NOTE).map(([strength, note]) => <li key={strength} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-border/60 py-3 last:border-0">
          <span className="w-28 shrink-0 text-[10px] uppercase tracking-[0.16em] text-muted-foreground">{term(strength.toLowerCase(), locale)}</span>
          <span className="w-10 font-serif text-lg tabular-nums text-primary">{data.attribution_strength[strength] ?? 0}</span>
          <span className="flex-1 text-xs leading-relaxed text-muted-foreground">{t(note)}</span>
        </li>)}</ul>
      </Panel>
      <Panel className="mt-4">
        <PanelHeader eyebrow="INV-7" title={t("Adherence")} />
        <p className="-mt-2 mb-4 text-xs leading-relaxed text-muted-foreground">{t("Whether the recommendation was actually followed. Advice nobody took tells us nothing about the advice.")}</p>
        <ul className="flex flex-wrap gap-x-10 gap-y-3">{Object.entries(data.adherence).map(([key, count]) => <li key={key}><p className="kpi-label">{term(key.toLowerCase(), locale)}</p><p className="mt-1 font-serif text-xl tabular-nums text-primary">{count}</p></li>)}</ul>
      </Panel>
    </>}
    <p className="mt-6 border-t border-border/60 pt-4 text-xs leading-relaxed text-muted-foreground">{recordText(data.note, locale)}</p>
  </main>;
}
