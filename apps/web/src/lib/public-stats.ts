import { api, type PlatformStats } from "@/lib/api";

/**
 * The landing page's numbers, and what to print when the API cannot supply them.
 *
 * The landing page is the one screen in the product read by people who have no account and
 * no patience — a funder opening a link, a judge with twenty tabs. It may never show an
 * error state, and it may never block on a slow database. So the read is best-effort: try
 * the API, and fall back to figures we can stand behind if anything at all goes wrong.
 */

/**
 * The seeded Prayagraj dataset. Cited rather than invented:
 *
 * - `farmers_modelled` and `acres_mapped` are the published figures in
 *   `docs/DEMO-CONTEXT.md`, asserted by `test_membership_is_one_thousand_farmers` and
 *   `test_total_area_matches_the_documented_acreage`.
 * - `crop_cycles_analysed` is the count a fresh `make seed` produces: five season windows
 *   across every plot. `scripts/progress.py` asserts a floor of 7,000 rather than this
 *   exact figure, so a change in plot generation moves the number without failing the
 *   build — which is why the test below compares the two.
 *
 * `apps/api/tests/test_public_stats.py::test_the_published_totals_match_the_demo_context`
 * is what keeps these honest. There is no compile-time bond across Python and TypeScript;
 * that test is the bond, and it fails before anyone can ship a page quoting figures the
 * database no longer holds.
 */
export const SEED_STATS: PlatformStats = {
  farmers_modelled: 1000,
  crop_cycles_analysed: 7258,
  acres_mapped: 2412,
  organizations: 1,
  is_synthetic: true,
  generated_at: "",
};

/**
 * Live totals, or the seeded ones.
 *
 * Swallowing the error is the point, not laziness: a 500, an unreachable host and the 2s
 * timeout all mean the same thing to a visitor, and all three should produce a complete
 * page rather than a gap where the numbers were. The failure is invisible by design — if
 * you are debugging a stale-looking band, check the API before you check this file.
 */
export async function platformStats(): Promise<PlatformStats> {
  try {
    return await api.platformStats();
  } catch {
    return SEED_STATS;
  }
}
