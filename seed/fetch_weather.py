#!/usr/bin/env python3
"""Fetch daily weather for the demo district from Open-Meteo's archive.

Open-Meteo needs no API key and permits non-commercial use. Unlike the Agmarknet endpoints
this *is* a documented public API, so it is a good deal safer to depend on — but the same
rule applies: the fetched payload is the durable artifact, because NFR-303 requires the demo
to run with the network disabled.

Usage
-----
    python seed/fetch_weather.py --from 2024-08-22 --to 2026-08-22

Output
------
``seed/generated/weather/<tract>.json``  one payload per tract centroid

Three tracts rather than one point: Yamuna-par is the rain-fed Vindhyan tract and its
rainfall genuinely differs from the irrigated Ganga-par plain. Fetching a single district
centroid would erase the very heterogeneity the district was chosen for (D-24).
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

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

#: Approximate centroids per tract ⚠️ — plausible points within each, not surveyed centroids.
#: Good enough for a weather grid cell; not good enough to claim geographic precision.
TRACT_POINTS: dict[str, tuple[float, float]] = {
    "GANGA_PAR": (25.5400, 81.8500),   # Soraon / Phulpur side, north of the Ganga
    "DOAB": (25.4358, 81.8463),        # Prayagraj city / Sadar, between the rivers
    "YAMUNA_PAR": (25.1800, 81.7300),  # Meja / Bara side, south of the Yamuna
}

DAILY_FIELDS = (
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "relative_humidity_2m_mean",
    "et0_fao_evapotranspiration",
)

OUT = pathlib.Path(__file__).parent / "generated" / "weather"


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
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed https host
        return json.loads(response.read().decode())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()

    start = dt.date.fromisoformat(args.date_from)
    end = dt.date.fromisoformat(args.date_to)
    OUT.mkdir(parents=True, exist_ok=True)

    total_days = 0
    for tract, (lat, lon) in TRACT_POINTS.items():
        target = OUT / f"{tract}.json"
        try:
            payload = fetch(lat, lon, start, end)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"  {tract}: FAILED — {exc}", file=sys.stderr)
            continue
        payload["_tract"] = tract
        payload["_requested"] = {"lat": lat, "lon": lon, "from": str(start), "to": str(end)}
        target.write_text(json.dumps(payload, indent=1))
        days = len(payload.get("daily", {}).get("time", []))
        total_days += days
        print(f"  {tract:<12} {days:>5} days  ({payload.get('latitude')}, {payload.get('longitude')})")

    print(f"\n{total_days} tract-days -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
