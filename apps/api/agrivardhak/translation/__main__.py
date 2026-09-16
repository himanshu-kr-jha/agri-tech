"""``python -m agrivardhak.translation seed`` — load the static dictionary as HUMAN rows.

The dictionary is ``apps/web/src/lib/strings.json``: the hand-written interface text the web
tier renders on the server. Loading it into ``translation_memory`` means a string that
appears both in the dictionary and somewhere the page translator reaches (a client component,
text React re-renders) resolves to the human wording, not to a machine one.

Idempotent: re-running updates the rows in place. Skips with a message rather than failing
when the web tree is not present, as in the API-only deployment image (ADR-0019).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agrivardhak.db.session import session_scope
from agrivardhak.translation.service import seed_human

STRINGS = Path(__file__).resolve().parents[4] / "apps" / "web" / "src" / "lib" / "strings.json"


def load_entries(path: Path = STRINGS) -> list[tuple[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [(entry["en"], entry["hi"]) for entry in data.values()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["seed"])
    parser.add_argument("--strings", type=Path, default=STRINGS)
    args = parser.parse_args()

    if not args.strings.exists():
        print(f"No dictionary at {args.strings}; skipping translation seed.")
        return 0
    entries = load_entries(args.strings)
    with session_scope() as session:
        written = seed_human(session, entries)
    print(f"Translation memory: {written} human rows from {len(entries)} dictionary entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
