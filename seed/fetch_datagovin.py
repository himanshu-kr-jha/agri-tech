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
import datetime as dt
import hashlib
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from source_registry import SOURCES, Source, batches, by_key, in_batch

API = "https://api.data.gov.in/resource"
UA = "AgriVardhak-seed/0.1 (agricultural research; contact via repo)"
GENERATED = pathlib.Path(__file__).resolve().parent / "generated"
STATE_PATH = GENERATED / "fetch_state.json"
LOG_PATH = GENERATED / "fetch_log.jsonl"

#: data.gov.in caps page size; every registered resource is far below this.
PAGE_LIMIT = 5000
RETRIES = 3
BACKOFF_BASE = 2.0


def now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def load_state() -> dict[str, dict[str, object]]:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text())


def save_state(state: dict[str, dict[str, object]]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def log(entry: dict[str, object]) -> None:
    """Append-only fetch log (DATA-SOURCING.md §5, health monitoring item ii)."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")


def content_hash(payload: dict[str, object]) -> str:
    """Hash the data, not the envelope. See module docstring."""
    material = {"records": payload.get("records", []), "field": payload.get("field", [])}
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def is_due(source: Source, state: dict[str, dict[str, object]]) -> bool:
    entry = state.get(source.key)
    if entry is None or not entry.get("last_checked"):
        return True
    last = dt.datetime.fromisoformat(str(entry["last_checked"]))
    return (now() - last).days >= source.cadence_days


def fetch(source: Source, api_key: str) -> dict[str, object]:
    """GET one resource, retrying with exponential backoff.

    A source that fails is left alone: the previously fetched payload stays on disk and stays
    valid. We never delete good historical data because a portal had a bad afternoon.
    """
    query = urllib.parse.urlencode({"api-key": api_key, "format": "json", "limit": PAGE_LIMIT})
    url = f"{API}/{source.resource_id}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": UA})

    last_error: Exception | None = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < RETRIES - 1:
                time.sleep(BACKOFF_BASE**attempt)
    raise RuntimeError(f"{source.key}: {RETRIES} attempts failed: {last_error}")


def write_manifest(batch: int, sources: list[Source]) -> None:
    """Per-batch provenance. Regenerated from whatever payloads are present."""
    directory = GENERATED / sources[0].batch_dir
    entries = []
    for source in sorted(sources, key=lambda s: s.key):
        path = directory / f"{source.key}.json"
        if not path.exists():
            continue
        raw = path.read_bytes()
        payload = json.loads(raw)
        entries.append(
            {
                "key": source.key,
                "title": source.title,
                "publisher": source.publisher,
                "access_route": source.access_route,
                "resource_id": source.resource_id,
                "unit": source.unit,
                "temporal_coverage": source.temporal_coverage,
                "authority": source.authority.value,
                "licence": source.licence,
                "recheck_days": source.cadence_days,
                "records": len(payload.get("records", [])),
                "fields": [f["id"] for f in payload.get("field", [])],
                "sha256_file": hashlib.sha256(raw).hexdigest(),
                "sha256_content": content_hash(payload),
                "notes": source.notes,
            }
        )
    manifest = {
        "batch": batch,
        "domain": sources[0].domain.value,
        "generated_at": now().isoformat(),
        "licence_note": (
            "UNKNOWN licences block a confidence-cap lift under ADR-0014. "
            "Data here is cached but inert until a human confirms the licence."
        ),
        "resources": entries,
    }
    (directory / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")


def run(sources: list[Source], api_key: str, *, force: bool) -> int:
    state = load_state()
    touched_batches: set[int] = set()
    failures = 0

    for source in sources:
        directory = GENERATED / source.batch_dir
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{source.key}.json"
        entry = dict(state.get(source.key, {}))
        started = now()

        try:
            payload = fetch(source, api_key)
        except RuntimeError as exc:
            failures += 1
            entry["last_error"] = str(exc)
            entry["last_error_at"] = started.isoformat()
            entry["health"] = "UNHEALTHY"
            state[source.key] = entry
            log(
                {
                    "at": started.isoformat(),
                    "source": source.key,
                    "result": "error",
                    "detail": str(exc),
                }
            )
            print(f"  {source.key:14} ERROR  {exc}")
            continue

        digest = content_hash(payload)
        #: Whether the *source* changed, which is not the same as whether we rewrite the file.
        #: ``--force`` rewrites, but must never claim the source changed — ``last_changed`` is
        #: the field that answers "when did this actually change", and a forced re-download
        #: would otherwise falsify it.
        changed = entry.get("content_hash") != digest
        rewrite = changed or force or not path.exists()

        entry["last_checked"] = started.isoformat()
        entry["health"] = "OK"
        entry.pop("last_error", None)
        entry.pop("last_error_at", None)

        if rewrite:
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            entry["content_hash"] = digest
            entry["records"] = len(payload.get("records", []))
            touched_batches.add(source.batch)
        if changed:
            entry["last_changed"] = started.isoformat()

        result = "changed" if changed else ("rewritten" if rewrite else "unchanged")
        log(
            {
                "at": started.isoformat(),
                "source": source.key,
                "result": result,
                "records": len(payload.get("records", [])),
                "sha256_content": digest,
            }
        )
        print(f"  {source.key:14} {result:10} {len(payload.get('records', []))} rec")

        state[source.key] = entry
        time.sleep(0.5)  # courtesy rate limit; no robots.txt is not permission

    save_state(state)
    for batch in sorted(touched_batches | {s.batch for s in sources}):
        members = in_batch(batch)
        if members:
            write_manifest(batch, members)
    return failures


def show_status() -> None:
    state = load_state()
    print(f"{'source':16}{'batch':6}{'domain':22}{'health':10}{'last changed':22}due")
    for source in SOURCES:
        entry = state.get(source.key, {})
        changed = str(entry.get("last_changed", "-"))[:19]
        health = str(entry.get("health", "never fetched"))
        due = "YES" if is_due(source, state) else f"in {source.cadence_days}d"
        print(
            f"{source.key:16}{source.batch:<6}{source.domain.value:22}{health:10}{changed:22}{due}"
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
        if not selected:
            print("nothing due.")
            return 0
    else:
        selected = list(SOURCES)

    print(f"fetching {len(selected)} source(s) from api.data.gov.in")
    failures = run(selected, api_key, force=args.force)
    if failures:
        print(f"\n{failures} source(s) failed; previous payloads left intact.", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
