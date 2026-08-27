#!/usr/bin/env python3
"""Shared machinery for the seed fetchers: state, logging, hashing, staleness.

There is one ``fetch_state.json`` and one ``fetch_log.jsonl`` across every fetcher, so
``--status`` answers "what do we have and what is stale" for all sources at once rather than
per script. A per-fetcher state file would make that question unanswerable, which is the
question the whole staleness design exists to answer (``docs/DATA-SOURCING.md`` §5).

stdlib only, matching the existing ``seed/fetch_*.py`` convention — these run without the API
venv.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
from typing import Any

from source_registry import Source

GENERATED = pathlib.Path(__file__).resolve().parent / "generated"
STATE_PATH = GENERATED / "fetch_state.json"
LOG_PATH = GENERATED / "fetch_log.jsonl"

UA = "AgriVardhak-seed/0.1 (agricultural research; contact via repo)"


def now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def load_state() -> dict[str, dict[str, Any]]:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text())


def save_state(state: dict[str, dict[str, Any]]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def log(entry: dict[str, Any]) -> None:
    """Append-only fetch log (DATA-SOURCING.md §5, health monitoring item ii)."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as fh:
        fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")


def digest(material: Any) -> str:
    """SHA-256 over canonical JSON of whatever identifies this content.

    Callers pass the *data*, never the response envelope: portals return volatile wrappers
    (timestamps, counts, VIEWSTATE) that would make every poll look like a change.
    """
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def is_due(source: Source, state: dict[str, dict[str, Any]]) -> bool:
    entry = state.get(source.key)
    if entry is None or not entry.get("last_checked"):
        return True
    last = dt.datetime.fromisoformat(str(entry["last_checked"]))
    return (now() - last).days >= source.cadence_days


def record_success(
    state: dict[str, dict[str, Any]],
    source: Source,
    *,
    content_digest: str,
    started: dt.datetime,
    records: int,
    force: bool,
    path: pathlib.Path,
    extra: dict[str, Any] | None = None,
) -> tuple[bool, bool]:
    """Update state for a successful fetch. Returns ``(changed, rewrite)``.

    ``changed`` means the *source* differs from what we last saw. ``rewrite`` means we will
    write the file. ``--force`` sets rewrite without setting changed: a forced re-download is
    not the source changing, and stamping ``last_changed`` for one would falsify the single
    field that answers "when did this actually change".
    """
    entry = dict(state.get(source.key, {}))
    changed = entry.get("content_hash") != content_digest
    rewrite = changed or force or not path.exists()

    entry["last_checked"] = started.isoformat()
    entry["health"] = "OK"
    entry.pop("last_error", None)
    entry.pop("last_error_at", None)
    if rewrite:
        entry["content_hash"] = content_digest
        entry["records"] = records
    if changed:
        entry["last_changed"] = started.isoformat()
    if extra:
        entry.update(extra)

    state[source.key] = entry
    return changed, rewrite


def record_failure(
    state: dict[str, dict[str, Any]],
    source: Source,
    *,
    error: str,
    started: dt.datetime,
) -> None:
    """Mark a source unhealthy without touching its previously fetched payload.

    We never delete good historical data because a portal had a bad afternoon.
    """
    entry = dict(state.get(source.key, {}))
    entry["last_error"] = error
    entry["last_error_at"] = started.isoformat()
    entry["health"] = "UNHEALTHY"
    state[source.key] = entry
    log({"at": started.isoformat(), "source": source.key, "result": "error", "detail": error})


def write_manifest(sources: list[Source], payload_records: dict[str, int]) -> None:
    """Per-batch provenance beside the payloads."""
    if not sources:
        return
    directory = GENERATED / sources[0].batch_dir
    directory.mkdir(parents=True, exist_ok=True)
    entries = []
    for source in sorted(sources, key=lambda s: s.key):
        path = directory / f"{source.key}.json"
        if not path.exists():
            continue
        raw = path.read_bytes()
        entries.append(
            {
                "key": source.key,
                "title": source.title,
                "publisher": source.publisher,
                "access_route": source.access_route,
                "resource_id": source.resource_id,
                "url": source.url,
                "language": source.language,
                "unit": source.unit,
                "temporal_coverage": source.temporal_coverage,
                "authority": source.authority.value,
                "licence": source.licence,
                "recheck_days": source.cadence_days,
                "records": payload_records.get(source.key, 0),
                "sha256_file": hashlib.sha256(raw).hexdigest(),
                "notes": source.notes,
            }
        )
    manifest = {
        "batch": sources[0].batch,
        "domain": sources[0].domain.value,
        "generated_at": now().isoformat(),
        "licence_note": (
            "An UNKNOWN licence blocks a confidence-cap lift under ADR-0014. Data is cached "
            "but inert until a human confirms the licence."
        ),
        "resources": entries,
    }
    (directory / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
