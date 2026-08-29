"""``make ingest`` — land the fetched batches, then observe the text-bearing ones.

Separate from ``make seed`` so the corpus can be refreshed without regenerating the
synthetic FPO. Both are idempotent, so running either twice is a no-op rather than a
duplicate, and an external cron can call this after ``make fetch-due`` without coordination.
"""

from __future__ import annotations

import argparse

from agrivardhak.db.session import session_scope
from agrivardhak.ingestion.policy import load_policy_events
from agrivardhak.ingestion.registry import load_all
from agrivardhak.knowledge.embed import available as encoder_available
from agrivardhak.knowledge.extract import apply_fixture
from agrivardhak.knowledge.pipeline import backfill_embeddings, observe


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--observe-only",
        action="store_true",
        help="skip landing; re-run the observer over records already present",
    )
    args = parser.parse_args()

    with session_scope() as session:
        landed = 0 if args.observe_only else sum(load_all(session).values())
        result = observe(session)
        backfilled = backfill_embeddings(session)
        attached = apply_fixture(session)
        events = load_policy_events(session)

    print(f"  external records  {landed:,} new")
    print(f"  observer          {result}")
    if backfilled:
        print(f"  backfill          {backfilled:,} chunks embedded retrospectively")
    print(f"  extractions       {attached:,} proposals attached (UNVERIFIED — ADR-0014)")
    print(f"  policy events     {events:,} new")
    if not encoder_available():
        print()
        print("  No sentence encoder on disk, so chunks were written without embeddings and")
        print("  retrieval is lexical-only. Run `make embed-model` to enable vector search;")
        print("  everything above works either way (NFR-303).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
