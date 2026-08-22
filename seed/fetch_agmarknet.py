#!/usr/bin/env python3
"""Pull real Agmarknet price and arrival data for the demo district.

Agmarknet 2.0 is a React SPA backed by a JSON API at ``https://api.agmarknet.gov.in/v1``.
The endpoints used here need no authentication. They were found by reading the published
front-end bundle; they are not a documented public API, so treat them as liable to change
and keep the fetched payloads (``seed/generated/agmarknet/``) as the durable artifact.

Usage
-----
    python seed/fetch_agmarknet.py --from 2026-06-01 --to 2026-08-22
    python seed/fetch_agmarknet.py --markets            # just print the market master

Output
------
``seed/generated/agmarknet/daily/<date>.json``   raw payload, one file per date
``seed/generated/agmarknet/series.csv``          flattened rows, ready for the seeder

Every row carries its market id, commodity id and date, so an EvidenceSnapshot can cite the
exact record a recommendation was built on (INV-2).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

API = "https://api.agmarknet.gov.in/v1"
HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://agmarknet.gov.in",
    "Referer": "https://agmarknet.gov.in/",
    "User-Agent": "AgriVardhak-seed/0.1 (hackathon research; contact via repo)",
}

# Verified 2026-08-22 from GET /market-district-state.
STATE_ID_UP = 34
DISTRICT_ID_PRAYAGRAJ = 646
PRAYAGRAJ_MARKETS = {
    298: "Prayagraj APMC",
    1724: "Ajuha APMC",
    1749: "Sirsa APMC",
    1764: "Jasra APMC",
    4389: "Lediyari APMC",
}

# Commodity ids from GET /daily-price-arrival/filters, for the demo crop portfolio.
COMMODITIES = {
    1: "Wheat",
    2: "Paddy(Common)",
    3: "Rice",
    12: "Mustard",
    24: "Potato",
    65: "Tomato",
    156: "Guava",
}

OUT = pathlib.Path(__file__).parent / "generated" / "agmarknet"


def _request(path: str, payload: dict | None = None) -> dict | list:
    url = f"{API}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=45) as resp:  # noqa: S310 - fixed https host
        return json.loads(resp.read().decode())


def market_master() -> list[dict]:
    """Full market → district → state master. ~4,600 markets nationally."""
    rows = _request("/market-district-state")
    assert isinstance(rows, list)
    return rows


def daily_report(date: dt.date, market_ids: list[int]) -> dict:
    """Market-wise, commodity-wise daily report for one date.

    Payload shape mirrors the front-end: ``marketIds`` and ``stateIds`` are arrays.
    """
    body = {
        "date": date.isoformat(),
        "marketIds": market_ids,
        "stateIds": [STATE_ID_UP],
        "includeExcel": False,
    }
    result = _request("/prices-and-arrivals/market-report/daily", body)
    assert isinstance(result, dict)
    return result


def flatten(payload: dict, date: dt.date) -> list[dict]:
    """Flatten the nested states → markets → commodities → data structure."""
    out: list[dict] = []
    for state in payload.get("states", []):
        for market in state.get("markets", []):
            for commodity in market.get("commodities", []):
                for row in commodity.get("data", []):
                    out.append(
                        {
                            "date": date.isoformat(),
                            "state_id": state.get("stateId"),
                            "state_name": state.get("stateName"),
                            "market_id": market.get("marketId"),
                            "market_name": market.get("marketName"),
                            "commodity_id": commodity.get("commodityId"),
                            "commodity_name": commodity.get("commodityName"),
                            "variety": row.get("variety"),
                            "grade": row.get("grade"),
                            "arrivals": row.get("arrivals"),
                            "unit_of_arrivals": row.get("unitOfArrivals"),
                            "min_price": row.get("minimumPrice"),
                            "max_price": row.get("maximumPrice"),
                            "modal_price": row.get("modalPrice"),
                            "unit_of_price": row.get("unitOfPrice"),
                        }
                    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="date_from", help="YYYY-MM-DD")
    ap.add_argument("--to", dest="date_to", help="YYYY-MM-DD")
    ap.add_argument("--markets", action="store_true", help="print the Prayagraj market master")
    ap.add_argument("--sleep", type=float, default=0.6, help="seconds between requests")
    args = ap.parse_args()

    if args.markets:
        rows = market_master()
        local = [
            r
            for r in rows
            if r.get("district_id") == DISTRICT_ID_PRAYAGRAJ or r.get("state_id") == STATE_ID_UP
        ]
        for r in sorted(
            (x for x in local if x.get("district_id") == DISTRICT_ID_PRAYAGRAJ),
            key=lambda x: str(x["market_name"]),
        ):
            print(f"{r['market_id']:>5}  {r['market_name']:<30} {r['district_name'].strip()}")
        print(f"\n({len(local)} markets in Uttar Pradesh)")
        return 0

    if not (args.date_from and args.date_to):
        ap.error("--from and --to are required unless --markets is given")

    start = dt.date.fromisoformat(args.date_from)
    end = dt.date.fromisoformat(args.date_to)
    if end < start:
        ap.error("--to must not precede --from")

    raw_dir = OUT / "daily"
    raw_dir.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []
    day, fetched, skipped = start, 0, 0
    while day <= end:
        cache = raw_dir / f"{day.isoformat()}.json"
        if cache.exists():
            payload = json.loads(cache.read_text())
            skipped += 1
        else:
            try:
                payload = daily_report(day, list(PRAYAGRAJ_MARKETS))
                cache.write_text(json.dumps(payload, indent=1))
                fetched += 1
                time.sleep(args.sleep)
            except (urllib.error.URLError, TimeoutError) as exc:
                # A missing day is normal — mandis close. Record and continue rather than
                # aborting a long backfill.
                print(f"  {day}  FAILED: {exc}", file=sys.stderr)
                day += dt.timedelta(days=1)
                continue
        rows = flatten(payload, day)
        all_rows.extend(rows)
        print(f"  {day}  {len(rows):>3} rows")
        day += dt.timedelta(days=1)

    csv_path = OUT / "series.csv"
    if all_rows:
        with csv_path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(all_rows[0]))
            writer.writeheader()
            writer.writerows(all_rows)

    print(f"\nfetched {fetched} days, reused {skipped} cached, {len(all_rows)} rows → {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
