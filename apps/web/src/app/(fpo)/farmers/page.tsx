/**
 * Farmer list with tract filter — FR-806, NFR-103.
 *
 * The tract filter is the point, not a convenience. When the Risk module says "312 farmers
 * exposed", the CEO's next question is "which ones", and the answer clusters by tract. A
 * list that could not be filtered that way would show a pattern as a flat roll of names.
 */

import Link from "next/link";

import { ApiError, TRACT_LABEL, api } from "@/lib/api";
import { DemoDataBadge } from "@/components/invariants";

export const dynamic = "force-dynamic";

const TRACTS = ["GANGA_PAR", "DOAB", "YAMUNA_PAR"] as const;

export default async function FarmersPage({
  searchParams,
}: {
  searchParams: Promise<{ tract?: string; offset?: string }>;
}) {
  const params = await searchParams;
  const tract = params.tract;
  const offset = Number(params.offset ?? 0);

  let data;
  try {
    data = await api.farmers({ tract, limit: 50, offset });
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 0;
    return (
      <main className="mx-auto max-w-5xl px-6 py-12">
        <h1 className="text-2xl font-semibold">Farmers</h1>
        <p className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200">
          {status === 403
            ? "The member list is organization-internal. A farmer sees only their own record."
            : "Could not reach the API. Run `make api`."}
        </p>
      </main>
    );
  }

  const shown = data.farmers.length;
  const end = offset + shown;

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-6">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">Farmers</h1>
          <DemoDataBadge />
        </div>
        <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
          {data.total.toLocaleString("en-IN")} members
          {tract ? ` in ${TRACT_LABEL[tract] ?? tract}` : ""}
        </p>
      </header>

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

      <div className="overflow-x-auto rounded-xl border border-neutral-200 dark:border-neutral-800">
        <table className="w-full text-sm">
          <thead className="border-b border-neutral-200 text-left text-xs uppercase tracking-wide text-neutral-500 dark:border-neutral-800">
            <tr>
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium">Village</th>
              <th className="px-4 py-3 font-medium">Block</th>
              <th className="px-4 py-3 font-medium">Tract</th>
              <th className="px-4 py-3 text-right font-medium">Area</th>
            </tr>
          </thead>
          <tbody>
            {data.farmers.map((farmer) => (
              <tr
                key={farmer.id}
                className="border-b border-neutral-100 last:border-0 hover:bg-neutral-50 dark:border-neutral-900 dark:hover:bg-neutral-900"
              >
                <td className="px-4 py-2.5">
                  <Link
                    href={`/farmers/${farmer.id}`}
                    className="font-medium underline-offset-2 hover:underline"
                  >
                    {farmer.name}
                  </Link>
                </td>
                <td className="px-4 py-2.5 text-neutral-600 dark:text-neutral-400">
                  {farmer.village ?? "—"}
                </td>
                <td className="px-4 py-2.5 text-neutral-600 dark:text-neutral-400">
                  {farmer.block ?? "—"}
                </td>
                <td className="px-4 py-2.5 text-neutral-600 dark:text-neutral-400">
                  {farmer.tract ? (TRACT_LABEL[farmer.tract] ?? farmer.tract) : "—"}
                </td>
                <td className="px-4 py-2.5 text-right tabular-nums">
                  {farmer.area_acres.toLocaleString("en-IN", { maximumFractionDigits: 2 })} ac
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex items-center justify-between text-sm">
        <span className="text-neutral-500">
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

function FilterLink({
  label,
  href,
  active,
}: {
  label: string;
  href: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={`rounded-md px-3 py-1.5 text-sm ring-1 ring-inset transition-colors ${
        active
          ? "bg-neutral-900 text-white ring-neutral-900 dark:bg-neutral-100 dark:text-neutral-900 dark:ring-neutral-100"
          : "ring-neutral-300 hover:bg-neutral-100 dark:ring-neutral-700 dark:hover:bg-neutral-800"
      }`}
    >
      {label}
    </Link>
  );
}

function PageLink({
  label,
  tract,
  offset,
}: {
  label: string;
  tract?: string;
  offset: number;
}) {
  const search = new URLSearchParams();
  if (tract) search.set("tract", tract);
  search.set("offset", String(offset));
  return (
    <Link
      href={`/farmers?${search}`}
      className="rounded-md px-3 py-1.5 ring-1 ring-inset ring-neutral-300 hover:bg-neutral-100 dark:ring-neutral-700 dark:hover:bg-neutral-800"
    >
      {label}
    </Link>
  );
}
