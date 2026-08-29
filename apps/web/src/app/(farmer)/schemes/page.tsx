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
 * Hindi leads on every line. Not a toggle: on a shared phone the setting is never the one
 * you left it on (the `today` page reached the same conclusion first).
 */

import { ApiError, api, type KnowledgeHit } from "@/lib/api";
import { DemoDataBadge } from "@/components/invariants";

export const dynamic = "force-dynamic";

const SUGGESTIONS: { hi: string; en: string }[] = [
  { hi: "फसल बीमा", en: "crop insurance" },
  { hi: "मृदा नमूना", en: "soil sample" },
  { hi: "उर्वरक अनुदान", en: "fertiliser subsidy" },
  { hi: "सिंचाई", en: "irrigation" },
  { hi: "बीज", en: "seed" },
];

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function Notice({ hit }: { hit: KnowledgeHit }) {
  return (
    <li className="panel">
      <div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-sm text-muted-foreground">{formatDate(hit.observed_at)}</span>
        <span className="text-sm text-muted-foreground">
          कृषि विभाग, उत्तर प्रदेश · UP Agriculture Dept
        </span>
      </div>

      {/* The published wording, at reading size. Hindi is the canonical text (ADR-0015). */}
      <p className="text-[17px] leading-relaxed text-foreground">{hit.text_hi}</p>

      {hit.text_en && (
        <p className="mt-2 text-[15px] leading-relaxed text-muted-foreground">{hit.text_en}</p>
      )}

      {hit.inert && (
        <p className="mt-3 border-t border-border/60 pt-2.5 text-sm leading-relaxed text-muted-foreground">
          यह विभाग की सामान्य जानकारी है — किसी लाभ की पुष्टि नहीं।
          <span className="block">
            General departmental guidance, not confirmation of any benefit.
          </span>
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
          <h1 className="title-section text-[2rem]">सरकारी सूचनाएँ</h1>
          <DemoDataBadge />
        </div>
        <p className="mt-1 text-[17px] text-muted-foreground">Government notices</p>
        <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">
          कृषि विभाग, उत्तर प्रदेश द्वारा प्रकाशित शासनादेश एवं जानकारी — जैसा प्रकाशित हुआ,
          वैसा ही।
          <span className="mt-1 block">
            Orders and guidance published by the UP Agriculture Department, shown exactly as
            published.
          </span>
        </p>
      </header>

      <form method="GET" className="panel mb-4">
        <label htmlFor="q" className="mb-2 block text-sm text-muted-foreground">
          खोजें · Search
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <input
            id="q"
            name="q"
            type="search"
            defaultValue={query}
            placeholder="फसल बीमा · crop insurance"
            className="min-w-0 flex-1 border-b border-border bg-transparent py-2 text-[17px] text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-accent"
          />
          <button
            type="submit"
            className="border border-border px-5 py-2 text-[15px] text-foreground transition-colors hover:border-accent hover:text-accent"
          >
            खोजें
          </button>
        </div>
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
          {SUGGESTIONS.map((s) => (
            <a
              key={s.hi}
              href={`/schemes?q=${encodeURIComponent(s.hi)}`}
              className="text-[15px] text-muted-foreground underline-offset-4 hover:text-accent hover:underline"
            >
              {s.hi}
            </a>
          ))}
        </div>
      </form>

      {failure !== null && (
        <p className="panel text-[15px] leading-relaxed text-muted-foreground">
          {failure === 403
            ? "यह पृष्ठ किसान खाते के लिए है। · This view is for a farmer account."
            : "जानकारी नहीं मिल सकी। · Could not reach the API. Run `make api`."}
        </p>
      )}

      {notices && notices.count === 0 && (
        <p className="panel text-[15px] leading-relaxed text-muted-foreground">
          इस विषय पर विभाग ने कुछ प्रकाशित नहीं किया है।
          <span className="mt-1 block">
            The department has not published anything on this. That is a real answer — this
            page searches only what the government has actually issued, and invents nothing.
          </span>
        </p>
      )}

      {notices && notices.count > 0 && (
        <>
          <p className="mb-3 text-sm text-muted-foreground">
            {query
              ? `“${query}” — ${notices.count} सूचनाएँ · ${notices.count} notices`
              : "हाल की सूचनाएँ · Recent notices"}
          </p>
          <ul className="space-y-3">
            {notices.results.map((hit) => (
              <Notice key={hit.chunk_id} hit={hit} />
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
              आपकी फ़सलें: <span className="text-foreground">{crops.join(", ")}</span>. ये
              सूचनाएँ पूरे विभाग के लिए हैं — किसी एक फ़सल के लिए नहीं।
              <span className="mt-1 block">
                Your crops: {crops.join(", ")}. These notices are department-wide — none of
                them names a specific crop, so none is matched to your farm.
              </span>
            </>
          ) : (
            <>
              ये सूचनाएँ पूरे विभाग के लिए हैं।
              <span className="mt-1 block">These notices are department-wide.</span>
            </>
          )}
        </p>
        <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">
          यह पृष्ठ यह नहीं बताता कि आप किसी योजना के पात्र हैं या नहीं। पात्रता एवं अंतिम
          तिथि की पुष्टि अपने विकास खंड कार्यालय या कृषि रक्षा इकाई से करें।
          <span className="mt-1 block">
            This page does not tell you whether you qualify for anything. It shows what was
            published and when. Confirm eligibility and deadlines at your block office —
            saying you qualify when you might not would do real harm.
          </span>
        </p>
      </section>
    </main>
  );
}
