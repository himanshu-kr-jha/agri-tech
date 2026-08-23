#!/usr/bin/env python3
"""Derive hazard climatology for the demo district from 30 years of Open-Meteo archive.

Why this exists
---------------
The Risk module needs to answer "how likely is unseasonal rain during the potato harvest
window?". That number decides whether 740 acres get staggered or not, so it must not be
invented. Nothing in `seed/sources.md` gives a half-month hazard frequency for Prayagraj,
and CLAUDE.md rule 5 forbids making one up.

So we compute it, from a real record: ERA5 reanalysis via Open-Meteo, 1995-2024, at the
same three tract points the seasonal weather uses. "Unseasonal rain probability 0.71" then
means something checkable — *in 30 years of record, 71% of them had a heavy-rain day in
this window at this point* — rather than something asserted.

What is stored
--------------
Not 33,000 daily rows. A **summary per half-month window per tract**: the fraction of years
that saw at least one hazard day, plus the counts it was computed from. The summary is the
evidence; the raw daily series stays in the payload file for anyone who wants to re-derive
it.

Hazard thresholds are stated here rather than buried, because they are judgement calls:

    heavy rain   >= 15 mm in a day   — enough to lodge a standing crop or halt a harvest
    very heavy   >= 40 mm in a day   — field flooding
    frost risk   tmin <= 4.0 C       — damages gram, mustard, potato foliage
    heat stress  tmax >= 40.0 C      — terminal heat on wheat grain fill

They are documented in `seed/sources.md` C8 so a reviewer can disagree with the threshold
without having to reverse-engineer it from code.

Usage
-----
    python seed/fetch_climatology.py                 # 1995-2024, all three tracts
    python seed/fetch_climatology.py --years 15
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from fetch_weather import ARCHIVE, TRACT_POINTS  # noqa: E402

OUT = pathlib.Path(__file__).parent / "generated" / "weather"

HEAVY_RAIN_MM = 15.0
VERY_HEAVY_RAIN_MM = 40.0
FROST_MAX_C = 4.0
HEAT_STRESS_C = 40.0

DAILY_FIELDS = ("temperature_2m_max", "temperature_2m_min", "precipitation_sum")


def window_key(date: dt.date) -> str:
    """Half-month buckets: fine enough to separate a harvest window from the month around it.

    A calendar month is too coarse — potato lifts in the first half of February and the
    hazard is not uniform across the month. A week is too fine for 30 samples.
    """
    return f"{date.month:02d}{'A' if date.day <= 15 else 'B'}"


def fetch(lat: float, lon: float, start: dt.date, end: dt.date) -> dict:
    query = urllib.parse.urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": ",".join(DAILY_FIELDS),
            "timezone": "Asia/Kolkata",
        }
    )
    request = urllib.request.Request(
        f"{ARCHIVE}?{query}",
        headers={"User-Agent": "AgriVardhak-seed/0.1 (hackathon research; contact via repo)"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310 - fixed https
        return json.loads(response.read().decode())


def summarise(payload: dict) -> dict:
    """Fraction of years in which each window saw at least one hazard day.

    Per-year-then-average, not per-day. "3% of February days are wet" and "60% of Februaries
    have a wet day" are different numbers, and only the second one answers the question an
    FPO is actually asking about a harvest window.
    """
    daily = payload["daily"]
    dates = [dt.date.fromisoformat(d) for d in daily["time"]]
    rain = daily["precipitation_sum"]
    tmax = daily["temperature_2m_max"]
    tmin = daily["temperature_2m_min"]

    # (window, year) -> set of hazards seen
    seen: dict[tuple[str, int], set[str]] = {}
    days: dict[str, int] = {}
    rain_total: dict[str, list[float]] = {}

    for i, date in enumerate(dates):
        key = window_key(date)
        days[key] = days.get(key, 0) + 1
        cell = seen.setdefault((key, date.year), set())
        r, hi, lo = rain[i], tmax[i], tmin[i]
        if r is not None:
            rain_total.setdefault(key, []).append(r)
            if r >= VERY_HEAVY_RAIN_MM:
                cell.add("very_heavy_rain")
            if r >= HEAVY_RAIN_MM:
                cell.add("heavy_rain")
        if lo is not None and lo <= FROST_MAX_C:
            cell.add("frost")
        if hi is not None and hi >= HEAT_STRESS_C:
            cell.add("heat_stress")

    windows: dict[str, dict] = {}
    for key in sorted(days):
        years = {y for (w, y) in seen if w == key}
        if not years:
            continue
        counts = {
            hazard: sum(1 for y in years if hazard in seen[(key, y)])
            for hazard in ("heavy_rain", "very_heavy_rain", "frost", "heat_stress")
        }
        windows[key] = {
            "years_observed": len(years),
            "probability": {h: round(c / len(years), 3) for h, c in counts.items()},
            "years_with_hazard": counts,
            "mean_rain_mm_per_day": round(
                sum(rain_total.get(key, [0])) / max(1, len(rain_total.get(key, [1]))), 2
            ),
        }
    return windows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, default=30)
    parser.add_argument("--end-year", type=int, default=2024)
    args = parser.parse_args()

    end = dt.date(args.end_year, 12, 31)
    start = dt.date(args.end_year - args.years + 1, 1, 1)
    OUT.mkdir(parents=True, exist_ok=True)

    for tract, (lat, lon) in TRACT_POINTS.items():
        try:
            payload = fetch(lat, lon, start, end)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"  {tract}: FAILED — {exc}", file=sys.stderr)
            continue
        windows = summarise(payload)
        target = OUT / f"CLIMATOLOGY_{tract}.json"
        target.write_text(
            json.dumps(
                {
                    "_tract": tract,
                    "_point": {"lat": lat, "lon": lon},
                    "_period": {"from": str(start), "to": str(end), "years": args.years},
                    "_thresholds": {
                        "heavy_rain_mm": HEAVY_RAIN_MM,
                        "very_heavy_rain_mm": VERY_HEAVY_RAIN_MM,
                        "frost_max_c": FROST_MAX_C,
                        "heat_stress_c": HEAT_STRESS_C,
                    },
                    "_source": "ERA5 reanalysis via Open-Meteo archive API",
                    "windows": windows,
                },
                indent=1,
            )
        )
        feb = windows.get("02A", {}).get("probability", {})
        print(
            f"  {tract:<12} {len(windows):>2} windows  "
            f"1-15 Feb heavy rain p={feb.get('heavy_rain')}  frost p={feb.get('frost')}"
        )

    print(f"\n-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
