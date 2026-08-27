#!/usr/bin/env python3
"""Scrape Uttar Pradesh agriculture government orders (शासनादेश) from shasanadesh.up.gov.in.

This is the route to the UP state schemes ``seed/sources.md`` §7 lists as S9-S12. They are
published in Hindi and largely nowhere else, which is why Hindi is not optional here.

**Hindi is canonical** (ADR-0015). Every field is stored verbatim as published. Nothing is
translated on ingest, and no rule may be transcribed from a translation — a scheme rule that
cannot be traced back to the published Hindi is a rule we should not be applying to anyone's
benefits.

**What this deliberately does not touch.** ``agridarshan.up.gov.in`` has a JSON API, found by
reading its Angular bundle. Its endpoints are ``beneficiaryMgt/getBenfById``,
``farmerRegister/getVerifier``, ``grantWiseBill/getFarmerList`` and similar: an internal DBT
beneficiary administration system holding personal farmer records. It is reachable and it is
out of bounds (INV-9). Public government orders are the correct source and contain no personal
data.

Licence
-------
shasanadesh.up.gov.in's own Copyright Policy permits reproduction for **non-commercial
research and private study, with attribution**; anything else needs department permission.
That is recorded on the source and is **not** a blanket open licence — commercial use of this
material is not cleared.

Usage
-----
    python seed/fetch_up_schemes.py                 # incremental: stop at the last GO we saw
    python seed/fetch_up_schemes.py --max-pages 20  # deepen the archive
    python seed/fetch_up_schemes.py --full          # ignore the cursor, re-walk everything

Output
------
``seed/generated/batch3_scheme/up-go-agriculture.json``

Incremental fetching
--------------------
The listing is newest-first, so the cursor is simply the newest GO number already stored. A
normal run walks pages until it meets that GO and stops, which keeps a quarterly poll to one
or two page fetches instead of the whole archive.
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

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
from source_registry import by_key, in_batch

SOURCE_KEY = "up-go-agriculture"
CMS_KEY = "up-agridarshan-cms"
RETRIES = 3
BACKOFF_BASE = 2.0
COURTESY_DELAY = 1.0  # no robots.txt is not permission; be a polite guest

#: Column order of the GridView, verified 2026-08-28.
COLUMNS = ("sl_no", "go_number", "go_date", "section", "category", "subject")


def _hidden(name: str, doc: str) -> str:
    """Pull an ASP.NET hidden field out of the rendered page."""
    match = re.search(rf'id="{name}"[^>]*value="([^"]*)"', doc) or re.search(
        rf'name="{name}"[^>]*value="([^"]*)"', doc
    )
    return html.unescape(match.group(1)) if match else ""


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse_rows(doc: str) -> list[dict[str, str]]:
    """Extract GO rows. A data row starts with a numeric serial; layout rows do not."""
    rows: list[dict[str, str]] = []
    for raw in re.findall(r"<tr[^>]*>(.*?)</tr>", doc, re.S):
        cells = [_text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", raw, re.S)]
        cells = [c for c in cells if c]
        if len(cells) >= len(COLUMNS) and re.fullmatch(r"\d+", cells[0]):
            rows.append(dict(zip(COLUMNS, cells[: len(COLUMNS)], strict=False)))
    return rows


def pager_targets(doc: str) -> list[str]:
    """Discover the pager's postback targets rather than assuming their numbering.

    The control indices do not map to page numbers in the obvious way — ``ctl02`` returns the
    third page, not the second. Reading them off the page and de-duplicating by GO number is
    robust to that; hardcoding an offset is not.
    """
    found = re.findall(r"__doPostBack\(&#39;([^&]*ItemDataPager[^&]*)&#39;", doc)
    seen: list[str] = []
    for target in found:
        if target not in seen:
            seen.append(target)
    return seen


def _post(url: str, fields: dict[str, str]) -> str:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(fields).encode(),
        headers={
            "User-Agent": UA,
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": url,
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", "replace")


def _get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", "replace")


def _with_retries(fn: Any, *args: Any) -> str:
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            return str(fn(*args))
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt < RETRIES - 1:
                time.sleep(BACKOFF_BASE**attempt)
    raise RuntimeError(f"{RETRIES} attempts failed: {last}")


def walk(url: str, *, max_pages: int, stop_at: str | None) -> tuple[list[dict[str, str]], bool]:
    """Walk the paginated listing newest-first. Returns (rows, reached_cursor)."""
    first = _with_retries(_get, url)
    collected = parse_rows(first)
    reached = any(row["go_number"] == stop_at for row in collected) if stop_at else False
    if reached:
        collected = [r for r in collected if r["go_number"] != stop_at]
        return collected, True

    targets = pager_targets(first)
    seen_numbers = {row["go_number"] for row in collected}
    page = 1

    for target in targets:
        if page >= max_pages:
            break
        time.sleep(COURTESY_DELAY)
        fields = {
            "__EVENTTARGET": target,
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": _hidden("__VIEWSTATE", first),
            "__VIEWSTATEGENERATOR": _hidden("__VIEWSTATEGENERATOR", first),
            "__EVENTVALIDATION": _hidden("__EVENTVALIDATION", first),
        }
        try:
            doc = _with_retries(_post, url, fields)
        except RuntimeError:
            break
        page += 1
        fresh = [r for r in parse_rows(doc) if r["go_number"] not in seen_numbers]
        if not fresh:
            continue
        for row in fresh:
            if stop_at and row["go_number"] == stop_at:
                return collected, True
            collected.append(row)
            seen_numbers.add(row["go_number"])

    return collected, False


def fetch_cms(state: dict[str, Any], *, force: bool) -> None:
    """The one public agridarshan endpoint: circulars, advisories, FAQs.

    Everything else on that API is either 403 (authentication-gated, so not public data and
    not something we work around) or a beneficiary endpoint holding personal farmer records,
    which we never touch. ``leaders`` is dropped on ingest: it carries officials' contact
    details, which we have no use for and no reason to copy.
    """
    source = by_key(CMS_KEY)
    assert source.url is not None
    started = now()
    path = GENERATED / source.batch_dir / f"{CMS_KEY}.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        raw = json.loads(_with_retries(_get, source.url))
    except (RuntimeError, json.JSONDecodeError) as exc:
        record_failure(state, source, error=str(exc), started=started)
        print(f"  {CMS_KEY}: FAILED ({exc}); previous payload left intact.")
        return

    data = {k: v for k, v in (raw.get("data") or {}).items() if k != "leaders"}
    counts = {k: len(v) if isinstance(v, list) else 0 for k, v in data.items()}
    payload = {
        "source_key": CMS_KEY,
        "publisher": source.publisher,
        "access_route": source.access_route,
        "url": source.url,
        "language": "hi",
        "language_note": (
            "Bilingual fields as published. Hindi is canonical; the English field is the "
            "publisher's own, not a translation we made (ADR-0015)."
        ),
        "authority": source.authority.value,
        "authority_note": (
            "Advisory tier (ADR-0012): FAQs and circulars are guidance, not eligibility text "
            "a rule may be transcribed from."
        ),
        "excluded": ["leaders (officials' contact details, not needed)"],
        "section_counts": counts,
        "data": data,
    }

    total = sum(counts.values())
    changed, rewrite = record_success(
        state,
        source,
        content_digest=digest(data),
        started=started,
        records=total,
        force=force,
        path=path,
    )
    if rewrite:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    result = "changed" if changed else ("rewritten" if rewrite else "unchanged")
    log({"at": started.isoformat(), "source": CMS_KEY, "result": result, "records": total})
    print(f"  {CMS_KEY}: {result} — " + ", ".join(f"{k}={v}" for k, v in counts.items() if v))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--max-pages", type=int, default=6, help="pages to walk (default 6)")
    parser.add_argument("--full", action="store_true", help="ignore the cursor, re-walk all")
    parser.add_argument("--force", action="store_true", help="rewrite even if unchanged")
    parser.add_argument("--due", action="store_true", help="no-op unless past the recheck cadence")
    args = parser.parse_args()

    source = by_key(SOURCE_KEY)
    assert source.url is not None
    state = load_state()
    if args.due and not is_due(source, state):
        print(f"{SOURCE_KEY}: not due (recheck every {source.cadence_days}d).")
        return 0
    entry = state.get(SOURCE_KEY, {})
    cursor = None if args.full else entry.get("cursor_go_number")
    started = now()

    directory = GENERATED / source.batch_dir
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{SOURCE_KEY}.json"

    print(f"walking {source.access_route} (dept 37), cursor={cursor or 'none'}")
    try:
        rows, reached = walk(
            source.url, max_pages=args.max_pages, stop_at=str(cursor) if cursor else None
        )
    except RuntimeError as exc:
        record_failure(state, source, error=str(exc), started=started)
        save_state(state)
        print(f"  FAILED: {exc}; previous payload left intact.", file=sys.stderr)
        return 1

    existing: list[dict[str, str]] = []
    if path.exists() and not args.full:
        existing = json.loads(path.read_text())["orders"]

    known = {row["go_number"] for row in existing}
    merged = [r for r in rows if r["go_number"] not in known] + existing

    payload = {
        "source_key": SOURCE_KEY,
        "publisher": source.publisher,
        "access_route": source.access_route,
        "url": source.url,
        "language": "hi",
        "language_note": (
            "Hindi as published, verbatim. Not translated on ingest; no rule may be "
            "transcribed from a translation (ADR-0015)."
        ),
        "licence": source.licence,
        "columns": list(COLUMNS),
        "orders": merged,
    }

    changed, rewrite = record_success(
        state,
        source,
        content_digest=digest(merged),
        started=started,
        records=len(merged),
        force=args.force,
        path=path,
        extra={"cursor_go_number": merged[0]["go_number"] if merged else None},
    )
    if rewrite:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    result = "changed" if changed else ("rewritten" if rewrite else "unchanged")
    log(
        {
            "at": started.isoformat(),
            "source": SOURCE_KEY,
            "result": result,
            "records": len(merged),
            "new_this_run": len(merged) - len(existing),
            "reached_cursor": reached,
        }
    )
    fetch_cms(state, force=args.force)
    save_state(state)
    write_manifest(
        in_batch(3),
        {SOURCE_KEY: len(merged), CMS_KEY: state.get(CMS_KEY, {}).get("records", 0)},
    )

    print(f"  {result}: {len(merged)} orders ({len(merged) - len(existing)} new this run)")
    if merged:
        print(f"  newest: {merged[0]['go_date']}  {merged[0]['subject'][:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
