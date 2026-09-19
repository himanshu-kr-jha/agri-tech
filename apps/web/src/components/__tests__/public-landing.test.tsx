/**
 * The public header, the stats band, and the fallback behind them.
 *
 * The stats assertions are the ones that matter beyond rendering: this is a public page
 * making numeric claims, and the framing that keeps those claims true (the verb in each
 * label, the dataset footnote) is as much a requirement as the number itself — see
 * ADR-0026 and UI-12.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StatsBand } from "@/components/landing/stats-band";
import { PublicNav } from "@/components/public-nav";
import type { PlatformStats } from "@/lib/api";
import { SEED_STATS } from "@/lib/public-stats";

vi.mock("next/navigation", () => ({ usePathname: () => "/about" }));

afterEach(cleanup);

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/about", label: "About us" },
  { href: "/privacy", label: "Privacy policy" },
  { href: "/faq", label: "FAQ" },
];

describe("the public nav", () => {
  it("offers all four destinations", () => {
    render(<PublicNav links={LINKS} openLabel="Open menu" closeLabel="Close menu" />);
    for (const link of LINKS) {
      expect(screen.getAllByText(link.label).length).toBeGreaterThan(0);
    }
  });

  it("marks exactly one link as the current page", () => {
    const { container } = render(
      <PublicNav links={LINKS} openLabel="Open menu" closeLabel="Close menu" />,
    );
    // Rendered twice (desktop row + mobile panel source), so count distinct hrefs.
    const current = new Set(
      [...container.querySelectorAll('[aria-current="page"]')].map((el) =>
        el.getAttribute("href"),
      ),
    );
    expect([...current]).toEqual(["/about"]);
  });
});

describe("the stats band", () => {
  const live: PlatformStats = {
    farmers_modelled: 1234,
    crop_cycles_analysed: 9876,
    acres_mapped: 4321,
    organizations: 2,
    is_synthetic: false,
    generated_at: "2026-09-19T00:00:00Z",
  };

  it("renders the figures it is handed, grouped for an Indian reader", () => {
    render(<StatsBand stats={live} locale="en" />);
    expect(screen.getByText("1,234")).toBeTruthy();
    expect(screen.getByText("9,876")).toBeTruthy();
    expect(screen.getByText("4,321")).toBeTruthy();
  });

  it("renders the fallback constants in the same shape", () => {
    // Guards the fallback from drifting out of the API's shape: if a field is renamed on
    // one side only, this fails rather than printing "undefined" on the front door.
    render(<StatsBand stats={SEED_STATS} locale="en" />);
    expect(screen.getByText("1,000")).toBeTruthy();
    expect(screen.getByText("2,412")).toBeTruthy();
  });

  it("keeps the verb in every label", () => {
    // "Farmers modelled" is a claim about a dataset; "Farmers" alone is a claim about
    // customers. The distinction is the whole reason this page needs no DEMO DATA badge.
    render(<StatsBand stats={live} locale="en" />);
    expect(screen.getByText("Farmers modelled")).toBeTruthy();
    expect(screen.getByText("Crop cycles analysed")).toBeTruthy();
    expect(screen.getByText("Acres mapped")).toBeTruthy();
  });

  it("names the dataset", () => {
    render(<StatsBand stats={live} locale="en" />);
    expect(screen.getByText("Prayagraj pilot dataset.")).toBeTruthy();
  });

  it("marks the numerals as untranslatable", () => {
    // "1,234" is not a pure-number text node — the comma means dom-translate would happily
    // hand it to the translation API and get something else back.
    const { container } = render(<StatsBand stats={live} locale="en" />);
    for (const node of container.querySelectorAll(".kpi-value")) {
      expect(node.getAttribute("translate")).toBe("no");
    }
  });

  it("renders Hindi from the dictionary, not at runtime", () => {
    render(<StatsBand stats={live} locale="hi" />);
    expect(screen.getByText("किसान मॉडल में")).toBeTruthy();
    expect(screen.getByText("प्रयागराज पायलट डेटासेट।")).toBeTruthy();
  });
});

describe("platformStats", () => {
  // `resetModules` before each case, not after: the file already imported the real
  // `@/lib/public-stats` at the top (for SEED_STATS), so without a reset the dynamic
  // import below resolves to the cached module and `doMock` has nothing to replace —
  // the test then silently exercises the live API instead of the failure path.
  beforeEach(() => vi.resetModules());
  afterEach(() => vi.doUnmock("@/lib/api"));

  it("falls back to the seeded figures when the API throws", async () => {
    // The assertion an end-to-end check cannot make: live and fallback print identical
    // numbers today, so only a forced failure proves which path ran.
    vi.doMock("@/lib/api", () => ({
      api: { platformStats: () => Promise.reject(new Error("ECONNREFUSED")) },
    }));
    const { platformStats, SEED_STATS: seed } = await import("@/lib/public-stats");
    await expect(platformStats()).resolves.toEqual(seed);
  });

  it("returns the live payload when the API answers", async () => {
    const payload = { ...SEED_STATS, farmers_modelled: 4242 };
    vi.doMock("@/lib/api", () => ({
      api: { platformStats: () => Promise.resolve(payload) },
    }));
    const { platformStats } = await import("@/lib/public-stats");
    await expect(platformStats()).resolves.toEqual(payload);
  });
});
