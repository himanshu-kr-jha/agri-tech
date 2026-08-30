/**
 * Search the external knowledge base — DR-07, FR-403, ADR-0018.
 *
 * The published government text this system has cached, ranked and cited. It exists as its
 * own screen because retrieval is otherwise invisible: a Decision Packet shows the *finding*
 * a policy order produced, never the order, and "why did it say that?" is the question a
 * CEO asks second.
 *
 * **The design rule here is the same one the conflicts page follows: show the gate, do not
 * hide behind it.** A passage from a source whose licence nobody has confirmed is still
 * worth reading — it is real published guidance — but under ADR-0014 it may never drive a
 * recommendation, and the API caps its confidence below the orchestrator's floor so that it
 * structurally cannot. Rendering those results identically to cleared ones would undo that
 * at the last step, so they carry a marker and sit visibly below the line.
 *
 * Hindi is shown first and largest, because Hindi is the canonical text (ADR-0015). The
 * English underneath is only ever the publisher's own; we do not translate on the way in,
 * and we do not translate on the way out either.
 *
 * No client JavaScript. The search box is a GET form and the query lives in the URL, which
 * makes a result set shareable and re-runnable — worth more here than an instant filter,
 * because the thing people will want to do with a surprising result is send it to someone.
 */

import { ApiError, api, type KnowledgeHit } from "@/lib/api";
import { Chip, EmptyState, ErrorPanel, PageHeader, Panel } from "@/components/ui";

export const dynamic = "force-dynamic";

const DOMAIN_LABEL: Record<string, string> = {
  POLICY: "policy",
  CLIMATE: "climate",
  MARKET: "market",
  SUPPLY_CHAIN: "supply chain",
  GLOBAL: "global",
  INPUT_PRICE: "input price",
};

/** Queries that show something real about this corpus rather than an empty state. */
const EXAMPLES = [
  "फसल बीमा",
  "crop insurance",
  "मृदा नमूना",
  "उर्वरक अनुदान",
  "soil testing",
];

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function Result({ hit, rank }: { hit: KnowledgeHit; rank: number }) {
  return (
    <li className="border-b border-border/60 py-5 last:border-0">
      <div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1.5">
        <span className="font-mono text-[11px] text-muted-foreground/70">{rank}</span>
        <span className="font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">
          {hit.source_key}
        </span>
        <span className="font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">
          {formatDate(hit.observed_at)}
        </span>
        {hit.news_domain && (
          <span className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            {DOMAIN_LABEL[hit.news_domain] ?? hit.news_domain.toLowerCase()}
          </span>
        )}
        {/* ADR-0010 rule 3: gold appears once per screen, and the header's count chip has
            it. An authority label on every row would spend the accent on the ordinary case,
            which is exactly the inflation the rule exists to prevent. The exception is the
            one thing a reader must not miss — and `alert` is red, not the accent. */}
        {hit.inert ? (
          <Chip tone="alert">context only</Chip>
        ) : (
          <span className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            {hit.authority.toLowerCase()}
          </span>
        )}
      </div>

      {/* Hindi is the canonical text and is set at reading size, not as a caption. */}
      <p className="text-[15px] leading-relaxed text-foreground">{hit.text_hi}</p>

      {hit.text_en && (
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {hit.text_en}
          <span className="ml-2 text-[10px] uppercase tracking-[0.14em] text-muted-foreground/70">
            publisher&rsquo;s own English
          </span>
        </p>
      )}

      {/* The arithmetic, shown rather than summarised: relevance x trust is the ordering. */}
      <p className="mt-3 font-mono text-[11px] text-muted-foreground/80">
        relevance {hit.relevance.toFixed(5)} × trust {hit.trust.toFixed(3)} ={" "}
        {hit.score.toFixed(5)}
        {hit.inert && ` · capped at ${hit.ceiling}`}
      </p>

      {hit.inert && (
        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
          The licence on this source is unconfirmed, so its confidence is capped below the
          level a recommendation needs. You may read it; the system may not act on it until
          a named person clears the licence (ADR-0014).
        </p>
      )}
    </li>
  );
}

export default async function KnowledgePage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const query = (q ?? "").trim();

  let data = null;
  let failure: number | null = null;
  if (query) {
    try {
      data = await api.knowledgeSearch({ q: query, k: 8 });
    } catch (error) {
      failure = error instanceof ApiError ? error.status : 0;
    }
  }

  const usable = data?.results.filter((r) => !r.inert) ?? [];
  const inert = data?.results.filter((r) => r.inert) ?? [];

  return (
    <main className="max-w-4xl px-6 py-10 md:px-10">
      <PageHeader
        eyebrow="DR-07"
        title="What the government has published"
        subtitle="Cached public agricultural text — Uttar Pradesh government orders and departmental guidance — searchable in Hindi or English. Results are ranked by relevance multiplied by how much the source is worth trusting, so a well-matching passage nobody has cleared us to rely on loses to a cited one."
        aside={
          <>
            {data && (
              <Chip tone={data.count > 0 ? "accent" : "neutral"}>
                {data.count === 1 ? "1 passage" : `${data.count} passages`}
              </Chip>
            )}
          </>
        }
      />

      <Panel className="mb-3">
        <form method="GET" className="flex flex-wrap items-center gap-3">
          <label htmlFor="q" className="sr-only">
            Search published text
          </label>
          <input
            id="q"
            name="q"
            type="search"
            defaultValue={query}
            placeholder="फसल बीमा · crop insurance · मृदा नमूना"
            className="min-w-0 flex-1 border-b border-border bg-transparent py-2 text-[15px] text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-accent"
          />
          <button
            type="submit"
            className="border border-border px-4 py-2 text-xs uppercase tracking-[0.14em] text-foreground transition-colors hover:border-accent hover:text-accent"
          >
            Search
          </button>
        </form>

        <div className="mt-4 flex flex-wrap items-baseline gap-x-4 gap-y-1.5">
          <span className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            try
          </span>
          {EXAMPLES.map((example) => (
            <a
              key={example}
              href={`/knowledge?q=${encodeURIComponent(example)}`}
              className="text-sm text-muted-foreground underline-offset-4 hover:text-accent hover:underline"
            >
              {example}
            </a>
          ))}
        </div>
      </Panel>

      {failure !== null && (
        <ErrorPanel title={failure === 401 ? "Not signed in" : "API unreachable"}>
          {failure === 401
            ? "This search needs a signed-in session."
            : "Could not reach the API. Run `make api`."}
        </ErrorPanel>
      )}

      {!query && failure === null && (
        <Panel>
          <EmptyState>
            Nothing searched yet. This index holds the government orders and departmental
            guidance the system has cached — the same text the risk register cites when it
            reports policy activity. An English query will find Hindi text: the passages are
            embedded with a multilingual model, so meaning carries across the two.
          </EmptyState>
        </Panel>
      )}

      {data && data.count === 0 && (
        <Panel>
          <EmptyState>
            Nothing matched &ldquo;{query}&rdquo;. The corpus is deliberately small — a few
            hundred passages of real published text, not a web index — so a miss usually
            means the government has not written about it, rather than that the search failed.
          </EmptyState>
        </Panel>
      )}

      {usable.length > 0 && (
        <Panel>
          <ul>
            {usable.map((hit, i) => (
              <Result key={hit.chunk_id} hit={hit} rank={i + 1} />
            ))}
          </ul>
        </Panel>
      )}

      {inert.length > 0 && (
        <Panel className="mt-3">
          <p className="eyebrow-sm mb-1">Licence unconfirmed</p>
          <h2 className="title-panel">Readable, but not actionable</h2>
          <p className="mt-2 max-w-2xl text-xs leading-relaxed text-muted-foreground">
            {inert.length === 1 ? "This passage comes" : "These passages come"} from a source
            whose licence nobody has confirmed. That is not a judgement about the content —
            it is often the most direct answer to the question — but a fetch cannot assert we
            are entitled to rely on it, so the system caps it below the confidence a
            recommendation requires.
          </p>
          <ul className="mt-3">
            {inert.map((hit, i) => (
              <Result key={hit.chunk_id} hit={hit} rank={usable.length + i + 1} />
            ))}
          </ul>
        </Panel>
      )}

      {data && (
        <p className="mt-6 max-w-2xl text-xs leading-relaxed text-muted-foreground">
          Every passage above is stored verbatim as published, in Hindi, and traces back to a
          raw cached payload with its own SHA-256 — so a claim built on one can be audited
          years later against exactly the text it cited (INV-2, ADR-0015).
        </p>
      )}
    </main>
  );
}
