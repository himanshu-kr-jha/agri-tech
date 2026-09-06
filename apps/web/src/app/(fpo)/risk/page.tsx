/**
 * Risk register — M15d, UI-08, FR-552, FR-554.
 *
 * Sorted by exposure, not by probability. A 90%-likely problem affecting nine acres is not
 * the top of this list; a 30%-likely one affecting nine hundred is. Sorting by likelihood is
 * the mistake that puts "April is hot in Prayagraj" above "1,868 tonnes harvest into the
 * annual price floor".
 *
 * Every row names who is exposed. A hazard with no exposure attached is a weather report.
 */

import { ApiError, api, type RiskEntry } from "@/lib/api";
import { formatInr, formatRole } from "@/components/invariants";
import { EmptyState, ErrorPanel, PageHeader, Panel } from "@/components/ui";
import { translator } from "@/lib/i18n";
import { currentLocale } from "@/lib/locale";
import { term, recordText, localeDate } from "@/lib/localized-data";

export const dynamic = "force-dynamic";

/**
 * Bands are hairline rings, not filled blocks.
 *
 * Four coloured pills per row — and there are two bands on every entry — would turn the
 * register into a heat map, which is exactly the reading this page is arguing against.
 * Colour marks severity; the numbers beside it carry the argument.
 */
const BAND: Record<string, string> = {
  HIGH: "text-destructive ring-destructive/30 bg-destructive/[0.04]",
  MEDIUM: "text-accent-foreground/80 ring-accent/45 bg-accent/[0.07]",
  LOW: "text-muted-foreground ring-border",
};

const DOMAIN_LABEL: Record<string, string> = {
  WEATHER: "weather", CLIMATE: "climate", MARKET: "market", CROP_HEALTH: "crop health",
  POLICY: "policy", SUPPLY_CHAIN: "supply chain", GLOBAL: "global",
};

function exposureScore(entry: RiskEntry): number {
  return (entry.value_at_risk_paise ?? 0) / 100 + (entry.farmers_affected ?? 0) * 1000 + (entry.area_affected_acres ?? 0) * 100;
}

/** A number and its unit, the house pattern: serif figure, smaller muted label beside it. */
function Exposure({ value, label }: { value: string; label: string }) {
  return <span className="flex items-baseline gap-1.5"><span className="font-serif text-[19px] tabular-nums text-primary">{value}</span><span className="text-xs text-muted-foreground">{label}</span></span>;
}

export default async function RiskPage() {
  const locale = await currentLocale();
  const t = translator(locale);
  let data;
  try {
    data = await api.riskRegister();
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 0;
    return <main className="px-6 py-10 md:px-10">
      <PageHeader eyebrow={t("con.risk.eyebrow")} title={t("con.risk.title")} />
      <ErrorPanel title={t(status === 403 ? "Organization-internal" : "API unreachable")}>{t(status === 403 ? "The risk register is organization-internal." : "Could not reach the API. Run `make api`.")}</ErrorPanel>
    </main>;
  }
  const entries = [...data.entries].sort((a, b) => exposureScore(b) - exposureScore(a));
  return <main className="max-w-5xl px-6 py-10 md:px-10">
    <PageHeader eyebrow={t("con.risk.eyebrow")} title={t("con.risk.h1")} subtitle={t("con.risk.sub")} />
    {entries.length === 0 ? <Panel><EmptyState>{t("Nothing on the register yet. It fills in when the assistant is asked a question that runs the risk module.")}</EmptyState></Panel> : <ul className="space-y-3">
      {entries.map((entry) => <li key={entry.id} className="panel">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-2">
          <h2 className="title-panel">{recordText(entry.title, locale)}</h2>
          <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{term(DOMAIN_LABEL[entry.domain] ?? entry.domain.toLowerCase(), locale)}</span>
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] ring-1 ring-inset ${BAND[entry.likelihood]}`}>{t("{band} likelihood", { band: term(entry.likelihood.toLowerCase(), locale) })}</span>
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] ring-1 ring-inset ${BAND[entry.impact]}`}>{t("{band} impact", { band: term(entry.impact.toLowerCase(), locale) })}</span>
        </div>
        <div className="mt-4 flex flex-wrap gap-x-8 gap-y-2">
          {entry.farmers_affected != null && <Exposure value={entry.farmers_affected.toLocaleString("en-IN")} label={t("farmers")} />}
          {entry.area_affected_acres != null && <Exposure value={entry.area_affected_acres.toLocaleString("en-IN")} label={t("acres")} />}
          {entry.value_at_risk_paise != null && <Exposure value={formatInr(entry.value_at_risk_paise)} label={t("at stake")} />}
          {typeof entry.detail?.probability === "number" && <Exposure value={`${Math.round(entry.detail.probability * 100)}%`} label={t("of years in the record")} />}
        </div>
        {entry.recommended_action && <p className="mt-4 border-t border-border/60 pt-3 text-sm leading-relaxed"><span className="eyebrow-sm">{t("What would reduce it")}</span><span className="mt-1.5 block text-foreground/85">{recordText(entry.recommended_action, locale)}</span></p>}
        <p className="mt-3 text-xs text-muted-foreground/80">
          {entry.owner_role && t("Owned by the {role}", { role: term(formatRole(entry.owner_role), locale) })}
          {entry.review_on && ` · ${t("review by {date}", { date: localeDate(entry.review_on, locale, { year: undefined }) })}`}
          {entry.evidence?.length ? ` · ${t("{count} sources", { count: entry.evidence.length })}` : ""}
        </p>
      </li>)}
    </ul>}
  </main>;
}
