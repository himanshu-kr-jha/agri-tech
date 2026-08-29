#!/usr/bin/env python3
"""Fetch registered data.gov.in resources into batch folders, idempotently.

Every source is declared in ``seed/source_registry.py``; this script names no URLs of its own.
It is built to be re-run on a schedule rather than run once, because government data changes
and a seed that was true in August is not automatically true in March.

Access route
------------
``api.data.gov.in`` — the sanctioned programmatic route. The data.gov.in *website* returns an
Akamai block to non-browser clients; that is an anti-bot protection and we do not work around
it (``docs/DATA-SOURCING.md`` §Legal boundaries).

Requires ``DATA_GOV_IN_API_KEY`` in the environment. The key is never written to disk.

Usage
-----
    python seed/fetch_datagovin.py --status          # what exists, what is due
    python seed/fetch_datagovin.py --due             # fetch only what is past its cadence
    python seed/fetch_datagovin.py --batch 1         # fetch one batch regardless of cadence
    python seed/fetch_datagovin.py --source msp-rabi --force

Output
------
``seed/generated/batch<N>_<domain>/<key>.json``   raw payload, the durable artifact
``seed/generated/batch<N>_<domain>/MANIFEST.json`` per-batch provenance + SHA-256
``seed/generated/fetch_state.json``               last_checked / last_changed / hash per source
``seed/generated/fetch_log.jsonl``                append-only record of every attempt

Change detection
----------------
The content hash covers the ``records`` and ``field`` arrays only, **not** the response
envelope. data.gov.in returns volatile envelope fields (``version``, ``count``) that would
otherwise make every poll look like a change and rewrite the payload for nothing.

An unchanged fetch updates ``last_checked`` and leaves ``last_changed`` and the file alone.
That is the whole point: polling stays cheap, and "when did this actually change" stays true.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from fetch_common import (
    GENERATED,
    UA,
    digest,
    is_due,
    load_state,
    log,
    now,
    record_failure,
    record_success,
    save_state,
    write_manifest,
)
from source_registry import SOURCES, Source, batches, by_key, in_batch

API = "https://api.data.gov.in/resource"

#: Page size. Not every resource fits in one page — the district production series is 33k
#: rows for UP alone — so ``fetch`` always pages by offset rather than trusting one request.
PAGE_LIMIT = 5000
RETRIES = 3
BACKOFF_BASE = 2.0


def content_hash(payload: dict[str, object]) -> str:
    """Hash the data, not the envelope. See module docstring."""
    return digest({"records": payload.get("records", []), "field": payload.get("field", [])})


def _get_page(source: Source, api_key: str, offset: int) -> dict[str, object]:
    """One page, retrying with exponential backoff."""
    params: dict[str, object] = {
        "api-key": api_key,
        "format": "json",
        "limit": PAGE_LIMIT,
        "offset": offset,
    }
    for key, value in (source.filters or {}).items():
        params[f"filters[{key}]"] = value
    url = f"{API}/{source.resource_id}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": UA})

    last_error: Exception | None = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                result: dict[str, object] = json.loads(response.read())
                return result
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < RETRIES - 1:
                time.sleep(BACKOFF_BASE**attempt)
    raise RuntimeError(f"{source.key}: {RETRIES} attempts failed at offset {offset}: {last_error}")


def fetch(source: Source, api_key: str) -> dict[str, object]:
    """Fetch every record for a resource, paging by offset.

    Paging is not optional: the district crop-production series is 246k rows nationally and
    the API caps a page well below that, so a single request would silently return a prefix
    and look like a complete dataset.

    A source that fails is left alone: the previously fetched payload stays on disk and stays
    valid. We never delete good historical data because a portal had a bad afternoon.
    """
    records: list[object] = []
    field: object = None
    total = 0
    offset = 0

    while True:
        page = _get_page(source, api_key, offset)
        field = field or page.get("field")
        total = int(page.get("total") or 0)
        batch = list(page.get("records") or [])
        records.extend(batch)
        offset += len(batch)
        if not batch or offset >= total:
            break
        time.sleep(0.3)  # courtesy between pages

    return {"records": records, "field": field, "total": total, "fetched_count": len(records)}


def run(sources: list[Source], api_key: str, *, force: bool) -> int:
    state = load_state()
    counts: dict[str, int] = {}
    failures = 0

    for source in sources:
        directory = GENERATED / source.batch_dir
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{source.key}.json"
        started = now()

        try:
            payload = fetch(source, api_key)
        except RuntimeError as exc:
            failures += 1
            record_failure(state, source, error=str(exc), started=started)
            print(f"  {source.key:20} ERROR  {exc}")
            continue

        records = len(payload.get("records", []))
        counts[source.key] = records
        changed, rewrite = record_success(
            state,
            source,
            content_digest=content_hash(payload),
            started=started,
            records=records,
            force=force,
            path=path,
        )
        if rewrite:
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

        result = "changed" if changed else ("rewritten" if rewrite else "unchanged")
        log({"at": started.isoformat(), "source": source.key, "result": result, "records": records})
        print(f"  {source.key:20} {result:10} {records} rec")
        time.sleep(0.5)  # courtesy rate limit; no robots.txt is not permission

    save_state(state)
    for batch in sorted({s.batch for s in sources}):
        write_manifest([s for s in in_batch(batch) if s.fetcher == "datagovin"], counts)
    return failures


def show_status() -> None:
    state = load_state()
    print(
        f"{'source':30}{'b':3}{'domain':22}{'fetcher':12}"
        f"{'lang':6}{'health':13}{'last changed':22}due"
    )
    for source in SOURCES:
        entry = state.get(source.key, {})
        changed = str(entry.get("last_changed", "-"))[:19]
        health = str(entry.get("health", "never fetched"))
        due = "YES" if is_due(source, state) else f"in {source.cadence_days}d"
        print(
            f"{source.key:30}{source.batch:<3}{source.domain.value:22}{source.fetcher:12}"
            f"{source.language:6}{health:13}{changed:22}{due}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--batch", type=int, choices=batches(), help="fetch one batch")
    group.add_argument("--source", help="fetch one source by registry key")
    group.add_argument("--due", action="store_true", help="fetch only what is past cadence")
    group.add_argument("--status", action="store_true", help="show registry and staleness")
    parser.add_argument("--force", action="store_true", help="rewrite even if unchanged")
    args = parser.parse_args()

    if args.status:
        show_status()
        return 0

    api_key = os.environ.get("DATA_GOV_IN_API_KEY", "").strip()
    if not api_key:
        print("DATA_GOV_IN_API_KEY is not set.", file=sys.stderr)
        print("  export DATA_GOV_IN_API_KEY=...   (never commit it)", file=sys.stderr)
        return 2

    if args.source:
        selected = [by_key(args.source)]
    elif args.batch:
        selected = in_batch(args.batch)
    elif args.due:
        state = load_state()
        selected = [s for s in SOURCES if is_due(s, state)]
    else:
        selected = list(SOURCES)

    # Sources with their own scraper (batch 3's ASP.NET listing, say) are skipped rather than
    # fetched with a null resource id. `make fetch-due` runs every fetcher, so they are not
    # dropped — each one just handles its own.
    skipped = [s for s in selected if s.fetcher != "datagovin"]
    selected = [s for s in selected if s.fetcher == "datagovin"]
    for source in skipped:
        print(f"  {source.key:20} skipped    (handled by fetch_{source.fetcher}.py)")

    if not selected:
        print("nothing due for this fetcher.")
        return 0

    print(f"fetching {len(selected)} source(s) from api.data.gov.in")
    failures = run(selected, api_key, force=args.force)
    if failures:
        print(f"\n{failures} source(s) failed; previous payloads left intact.", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
