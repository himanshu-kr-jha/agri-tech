/**
 * What the agriculture department has published — the farmer's view. UI-05, UI-06, INV-5.
 *
 * The originating pain in `context.md` is that farmers cannot reach scheme information; the
 * brief is about "improving access to information for an underserved community". This page
 * is the most direct answer this system has to that, so it is farmer-facing rather than
 * something the CEO relays.
 *
 * **It does not cross the information boundary.** INV-5 governs data flowing from the FPO
 * context to a farmer, or between farmers. A government order published on a public state
 * portal is neither — it is public, and the farmer is arguably its intended audience. The
 * only farmer-specific thing on this page is their own crop list, which is their own data.
 *
 * **It never says "you are eligible."** `seed/sources.md` puts the stake plainly: *telling a
 * farmer they qualify for a benefit they do not is a real harm.* Nothing here is an
 * eligibility assessment. It shows what was published, when, and tells the reader where to
 * confirm it. The scheme module's own assessments are capped at 0.55 and carry
 * `rules_verified=False`; this page has no rules at all, and says so.
 *
 * **It is honest that the notices are not about them personally.** Measured across the 75
 * cached orders: *none* names an individual crop. They are department-wide. Presenting them
 * as "matched to your paddy" would be a fabrication dressed as personalisation, so the page
 * states the relationship it actually has — these apply to every farmer in the state,
 * including you.
 *
 * One language at a time, set by the switch in the header. This page used to lead in Hindi
 * with an English gloss under every line; that reversal was asked for deliberately, and the
 * cost is named rather than hidden: in English the published Devanagari is not on screen,
 * so what you are reading is a rendering of a legal order and not the order itself. Where
 * no English rendering exists the Hindi is shown anyway, labelled — an order with no
 * translation must not silently vanish from the list.
 */

import { ApiError, api, type KnowledgeHit } from "@/lib/api";
import { NOTICE_SUGGESTIONS, translator, type StringKey } from "@/lib/i18n";
import { currentLocale, type Locale } from "@/lib/locale";

export const dynamic = "force-dynamic";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function Notice({
  hit,
  locale,
  t,
}: {
  hit: KnowledgeHit;
  locale: Locale;
  t: (key: StringKey) => string;
}) {
  // In Hindi the canonical text is what you get. In English the publisher's own rendering is
  // preferred; where there is none the published Hindi is rendered and the page translator
  // turns it into English on screen, unlabelled (ADR-0023). `text_hi` itself is never
  // replaced — only what is displayed changes.
  const body = locale === "en" && hit.text_en ? hit.text_en : hit.text_hi;

  return (
    <li className="panel">
      <div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-sm text-muted-foreground">{formatDate(hit.observed_at)}</span>
        <span className="text-sm text-muted-foreground">{t("notices.department")}</span>
      </div>

      <p className="text-[17px] leading-relaxed text-foreground">{body}</p>

      {hit.inert && (
        <p className="mt-3 border-t border-border/60 pt-2.5 text-sm leading-relaxed text-muted-foreground">
          {t("notices.inert")}
        </p>
      )}
    </li>
  );
}

export default async function SchemesPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const locale = await currentLocale();
  const t = translator(locale);
  const query = (q ?? "").trim();

  let notices = null;
  let crops: string[] = [];
  let failure: number | null = null;

  try {
    const [knowledge, today] = await Promise.all([
      query ? api.knowledgeSearch({ q: query, k: 8 }) : api.knowledgeRecent({ k: 6 }),
      // The farmer's own crops — their data, used only to say honestly that the notices
      // below are not specific to them.
      api.farmerToday().catch(() => null),
    ]);
    notices = knowledge;
    crops = [...new Set((today?.crops ?? []).map((c) => c.crop))];
  } catch (error) {
    failure = error instanceof ApiError ? error.status : 0;
  }

  return (
    <main className="mx-auto max-w-2xl px-5 py-8">
      <header className="mb-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="title-section text-[2rem]">{t("notices.title")}</h1>
        </div>
        <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">
          {t("notices.intro")}
        </p>
      </header>

      <form method="GET" className="panel mb-4">
        <label htmlFor="q" className="mb-2 block text-sm text-muted-foreground">
          {t("notices.search")}
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <input
            id="q"
            name="q"
            type="search"
            defaultValue={query}
            placeholder={t("notices.searchPlaceholder")}
            className="min-w-0 flex-1 border-b border-border bg-transparent py-2 text-[17px] text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-accent"
          />
          <button
            type="submit"
            className="border border-border px-5 py-2 text-[15px] text-foreground transition-colors hover:border-accent hover:text-accent"
          >
            {t("notices.search")}
          </button>
        </div>
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
          {NOTICE_SUGGESTIONS.map((suggestion) => (
            <a
              key={suggestion.en}
              href={`/schemes?q=${encodeURIComponent(suggestion[locale])}`}
              className="text-[15px] text-muted-foreground underline-offset-4 hover:text-accent hover:underline"
            >
              {suggestion[locale]}
            </a>
          ))}
        </div>
      </form>

      {failure !== null && (
        <p className="panel text-[15px] leading-relaxed text-muted-foreground">
          {failure === 403
            ? t("notices.forbidden")
            : t("notices.unreachable")}
        </p>
      )}

      {notices && notices.count === 0 && (
        <p className="panel text-[15px] leading-relaxed text-muted-foreground">
          {t("notices.none")}
        </p>
      )}

      {notices && notices.count > 0 && (
        <>
          <p className="mb-3 text-sm text-muted-foreground">
            {query
              ? `“${query}” — ${notices.count} ${t("notices.countSuffix")}`
              : t("notices.recent")}
          </p>
          <ul className="space-y-3">
            {notices.results.map((hit) => (
              <Notice key={hit.chunk_id} hit={hit} locale={locale} t={t} />
            ))}
          </ul>
        </>
      )}

      {/* The honest statement of what this page is and is not. Placed after the notices,
          because a reader who has just read one is the reader who needs it. */}
      <section className="mt-8 border-t border-border/70 pt-5">
        <p className="text-[15px] leading-relaxed text-muted-foreground">
          {crops.length > 0 ? (
            <>
              {t("notices.yourCrops")}:{" "}
              <span className="text-foreground">{crops.join(", ")}</span>.{" "}
              {t("notices.departmentWideWithCrops")}
            </>
          ) : (
            <>
              {t("notices.departmentWide")}
            </>
          )}
        </p>
        <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">
          {t("notices.disclaimer")}
        </p>
      </section>
    </main>
  );
}
