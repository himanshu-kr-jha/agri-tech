/**
 * Farmer list with tract filter — FR-806, NFR-103.
 *
 * The tract filter is the point, not a convenience. When the Risk module says "312 farmers
 * exposed", the CEO's next question is "which ones", and the answer clusters by tract. A
 * list that could not be filtered that way would show a pattern as a flat roll of names.
 */

import Link from "next/link";

import { ApiError, TRACT_LABEL, api } from "@/lib/api";
import { ErrorPanel, PageHeader, Panel } from "@/components/ui";
import { translator } from "@/lib/i18n";
import { currentLocale } from "@/lib/locale";

export const dynamic = "force-dynamic";

const TRACTS = ["GANGA_PAR", "DOAB", "YAMUNA_PAR"] as const;

export default async function FarmersPage({
  searchParams,
}: {
  searchParams: Promise<{ tract?: string; offset?: string }>;
}) {
  const t = translator(await currentLocale());
  const params = await searchParams;
  const tract = params.tract;
  const offset = Number(params.offset ?? 0);

  let data;
  try {
    data = await api.farmers({ tract, limit: 50, offset });
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 0;
    return (
      <main className="px-6 py-10 md:px-10">
        <PageHeader eyebrow={t("con.farmers.eyebrow")} title={t("con.farmers.title")} />
        <ErrorPanel title={status === 403 ? "Organization-internal" : "API unreachable"}>
          {status === 403
            ? "The member list is organization-internal. A farmer sees only their own record."
            : "Could not reach the API. Run `make api`."}
        </ErrorPanel>
      </main>
    );
  }

  const shown = data.farmers.length;
  const end = offset + shown;

  return (
    <main className="max-w-6xl px-6 py-10 md:px-10">
      <PageHeader
        eyebrow="Membership"
        title="Farmers"
        subtitle={`${data.total.toLocaleString("en-IN")} members${
          tract ? ` in ${TRACT_LABEL[tract] ?? tract}` : ""
        }, across three tracts of the district.`}
      />

      <nav aria-label="Filter by tract" className="mb-5 flex flex-wrap gap-2">
        <FilterLink label="All tracts" href="/farmers" active={!tract} />
        {TRACTS.map((key) => (
          <FilterLink
            key={key}
            label={TRACT_LABEL[key]}
            href={`/farmers?tract=${key}`}
            active={tract === key}
          />
        ))}
      </nav>

      <Panel className="overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/70 text-left">
              {["Name", "Village", "Block", "Tract", "Area"].map((h, i) => (
                <th
                  key={h}
                  className={`px-6 py-3.5 text-[10px] font-medium uppercase tracking-[0.16em] text-muted-foreground ${
                    i === 4 ? "text-right" : ""
                  }`}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.farmers.map((farmer) => (
              <tr
                key={farmer.id}
                className="border-b border-border/50 transition-colors last:border-0 hover:bg-muted/40"
              >
                <td className="px-6 py-3">
                  <Link
                    href={`/farmers/${farmer.id}`}
                    className="font-medium text-foreground underline-offset-4 hover:underline"
                  >
                    {farmer.name}
                  </Link>
                </td>
                <td className="px-6 py-3 text-muted-foreground">{farmer.village ?? "—"}</td>
                <td className="px-6 py-3 text-muted-foreground">{farmer.block ?? "—"}</td>
                <td className="px-6 py-3 text-muted-foreground">
                  {farmer.tract ? (TRACT_LABEL[farmer.tract] ?? farmer.tract) : "—"}
                </td>
                <td className="px-6 py-3 text-right tabular-nums">
                  <span className="font-serif text-[15px] text-primary">
                    {farmer.area_acres.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
                  </span>
                  <span className="ml-1 text-xs text-muted-foreground">ac</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <div className="mt-4 flex items-center justify-between text-sm">
        <span className="text-xs uppercase tracking-[0.14em] text-muted-foreground">
          {shown === 0 ? "No farmers match" : `Showing ${offset + 1}–${end} of ${data.total}`}
        </span>
        <div className="flex gap-2">
          {offset > 0 && (
            <PageLink label="Previous" tract={tract} offset={Math.max(0, offset - 50)} />
          )}
          {end < data.total && <PageLink label="Next" tract={tract} offset={end} />}
        </div>
      </div>
    </main>
  );
}

function FilterLink({ label, href, active }: { label: string; href: string; active: boolean }) {
  return (
    <Link
      href={href}
      aria-current={active ? "true" : undefined}
      className={
        active
          ? "rounded-md bg-primary px-3 py-1.5 text-[13px] font-medium text-primary-foreground"
          : "btn-ghost px-3 py-1.5 text-[13px]"
      }
    >
      {label}
    </Link>
  );
}

function PageLink({ label, tract, offset }: { label: string; tract?: string; offset: number }) {
  const search = new URLSearchParams();
  if (tract) search.set("tract", tract);
  search.set("offset", String(offset));
  return (
    <Link href={`/farmers?${search}`} className="btn-ghost px-3 py-1.5 text-[13px]">
      {label}
    </Link>
  );
}
