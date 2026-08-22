#!/usr/bin/env python3
"""Regenerate the machine-verified section of PROGRESS.md.

A hand-maintained progress table rots: someone finishes a thing and forgets the row, or
marks a row done that was never wired up. So PROGRESS.md has two layers:

  * the **intent layer** (hand-written, above the marker) — what we mean to build and why;
  * the **reality layer** (this script, below the marker) — what the repository can prove.

Each deliverable declares *evidence*: a symbol that must import, a test that must pass, or
a database fact that must hold. A row goes green only when its evidence does. Nobody can
mark something done by editing a table.

Usage:
    python scripts/progress.py            # rewrite PROGRESS.md
    python scripts/progress.py --check    # exit 1 if the file is stale (for CI)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import re
import subprocess
import sys
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parent.parent
API = ROOT / "apps" / "api"
WEB = ROOT / "apps" / "web"
PROGRESS = ROOT / "PROGRESS.md"
START = "<!-- BEGIN GENERATED — do not edit below this line; run `make progress` -->"
END = "<!-- END GENERATED -->"


# --------------------------------------------------------------------------- evidence


@dataclass
class Evidence:
    """How a deliverable proves it exists. All declared probes must pass."""

    #: "module.path:symbol" — must import and have the attribute.
    symbols: list[str] = field(default_factory=list)
    #: Paths relative to the repo root that must exist and be non-trivial.
    files: list[str] = field(default_factory=list)
    #: pytest node-id substrings that must appear as PASSED.
    tests: list[str] = field(default_factory=list)
    #: Minimum row counts, as {table: n}.
    rows: dict[str, int] = field(default_factory=dict)


@dataclass
class Deliverable:
    id: str
    title: str
    phase: str
    requirements: str
    evidence: Evidence
    #: MUST | SHOULD | POST-MVP
    priority: str = "MUST"


# The M/S ids match docs/MVP-SCOPE.md §3. Adding a deliverable = adding a row here.
DELIVERABLES: list[Deliverable] = [
    # ---- Phase 0
    Deliverable("M1", "Schema + Alembic migrations", "0", "DR-01…09",
                Evidence(symbols=["agrivardhak.domain.models:Organization"], rows={"__tables__": 49})),
    Deliverable("M0a", "Append-only enforcement (DB triggers)", "0", "DR-04, INV-2",
                Evidence(tests=["test_observation_value_cannot_be_updated",
                                "test_evidence_snapshot_cannot_be_updated"])),
    Deliverable("M0b", "Module + DecisionPacket contracts", "0", "FR-500, FR-801",
                Evidence(symbols=["agrivardhak.intelligence.contracts:ModuleOutput",
                                  "agrivardhak.orchestrator.packet:DecisionPacket"],
                         tests=["test_finding_requires_evidence"])),
    Deliverable("M5", "Auth, roles and ContextScope enforcement", "0", "FR-104, FR-809, NFR-401",
                Evidence(symbols=["agrivardhak.api.scope:ContextScope",
                                  "agrivardhak.db.repository:ScopedRepository",
                                  "agrivardhak.api.auth:current_scope"],
                         tests=["test_farmer_scope_excludes_org_internal",
                                "test_farmer_cannot_see_another_farmer"])),
    Deliverable("M0c", "FastAPI app + health", "0", "API-01",
                Evidence(symbols=["agrivardhak.api.main:app"])),
    Deliverable("M0d", "Next.js app + invariant components", "0", "UI-02, UI-04",
                Evidence(files=["apps/web/src/components/invariants.tsx"])),

    # ---- Phase 1
    Deliverable("M2", "Provenance: trust, decay, resolution", "1", "FR-301…307",
                Evidence(symbols=["agrivardhak.provenance.trust:effective_confidence",
                                  "agrivardhak.provenance.resolver:resolve"],
                         tests=["test_confidence_halves_over_one_half_life",
                                "test_records_and_resolves_a_single_observation"])),
    Deliverable("M3", "Discrepancy detection + resolution", "1", "FR-304, FR-305, INV-4",
                Evidence(symbols=["agrivardhak.provenance.resolver:detect_conflict",
                                  "agrivardhak.provenance.resolver:resolve_discrepancy"],
                         tests=["test_three_way_conflict_raises_a_discrepancy_and_picks_no_winner",
                                "test_human_resolution_closes_the_conflict_and_keeps_the_trail"])),
    Deliverable("M0f", "Canonical units + conversions", "0", "DR-02, ADR-0009",
                Evidence(symbols=["agrivardhak.domain.units:rupees_per_quintal_to_paise_per_kg"],
                         tests=["test_rupees_per_quintal_and_paise_per_kg_are_numerically_identical",
                                "test_money_never_touches_a_float"])),
    Deliverable("M4", "Seed: Prayagraj FPO, 1,000 farmers", "1", "DR-09, C-2",
                Evidence(symbols=["agrivardhak.seed:seed_all"],
                         tests=["test_membership_is_one_thousand_farmers",
                                "test_total_area_matches_the_documented_acreage"],
                         rows={"farmer": 1000, "crop_cycle": 7000})),
    Deliverable("M4b", "Agmarknet ingestion + 24-month backfill", "1", "FR-402, EXT-02",
                Evidence(files=["seed/fetch_agmarknet.py", "seed/generated/agmarknet/series.csv"])),
    Deliverable("M4c", "Weather adapter (Open-Meteo) + fixture fallback", "1", "FR-401, FR-406",
                Evidence(symbols=["agrivardhak.ingestion.weather:fetch_weather"])),
    Deliverable("M6", "Quality Intelligence module", "1", "FR-531…534",
                Evidence(symbols=["agrivardhak.intelligence.quality:run"])),
    Deliverable("M7", "Market Intelligence module (effective price, scoring, allocation)", "1",
                "FR-541…545",
                Evidence(symbols=["agrivardhak.intelligence.market:run",
                                  "agrivardhak.intelligence.market:effective_price"],
                         tests=["test_nearby_cheaper_buyer_beats_distant_dearer_one",
                                "test_rejection_risk_dominates_the_deduction",
                                "test_module_is_pure_and_replayable"])),
    Deliverable("M7b", "Market data plumbing: lots, offers, price ingestion", "1", "FR-546, EXT-02",
                Evidence(symbols=["agrivardhak.ingestion.agmarknet:load_series",
                                  "agrivardhak.seed.generator:_seed_lots"])),
    Deliverable("M15a", "FPO dashboard: 10 cards", "1", "UI-01",
                Evidence(files=["apps/web/src/app/(fpo)/dashboard/page.tsx"])),
    Deliverable("M15b", "Farmer list + drill-down", "1", "FR-806, NFR-103",
                Evidence(files=["apps/web/src/app/(fpo)/farmers/page.tsx"])),

    # ---- Phase 2
    Deliverable("M8", "Risk Intelligence module", "2", "FR-551…555",
                Evidence(symbols=["agrivardhak.intelligence.risk:run"])),
    Deliverable("M9", "Scheme Intelligence module", "2", "FR-561…565",
                Evidence(symbols=["agrivardhak.intelligence.scheme:run"])),
    Deliverable("M10", "Farm Intelligence module", "2", "FR-511, FR-512",
                Evidence(symbols=["agrivardhak.intelligence.farm:run"])),
    Deliverable("M11", "Crop Health Intelligence module", "2", "FR-521…524, INV-8",
                Evidence(symbols=["agrivardhak.intelligence.crop_health:run"],
                         tests=["test_chemical_recommendation_has_citation_or_caution"])),
    Deliverable("M13", "Orchestrator + evidence freezing", "2", "FR-801…806, FR-704",
                Evidence(symbols=["agrivardhak.orchestrator.engine:build_packet",
                                  "agrivardhak.orchestrator.snapshot:freeze"])),
    Deliverable("M14", "Approval lifecycle", "2", "FR-705…710, INV-1",
                Evidence(symbols=["agrivardhak.decisions.lifecycle:approve"],
                         tests=["test_no_execution_without_approval"])),
    Deliverable("M4d", "Scheme + news ingestion, embeddings", "2", "FR-403, FR-404",
                Evidence(symbols=["agrivardhak.ingestion.schemes:ingest"])),
    Deliverable("M0e", "Domain-event outbox dispatcher", "2", "DR-05, ADR-0007",
                Evidence(symbols=["agrivardhak.events.outbox:dispatch"])),

    # ---- Phase 3
    Deliverable("M12", "Funding requirement (thin)", "3", "FR-601…606",
                Evidence(symbols=["agrivardhak.intelligence.funding:run"])),
    Deliverable("M15c", "Assistant view + SSE streaming", "3", "API-05, FR-807",
                Evidence(files=["apps/web/src/app/(fpo)/assistant/page.tsx"])),
    Deliverable("M15d", "Risk register + market screens", "3", "UI-08, FR-544",
                Evidence(files=["apps/web/src/app/(fpo)/risk/page.tsx"])),
    Deliverable("M15e", "Decision history + frozen evidence viewer", "3", "FR-710",
                Evidence(files=["apps/web/src/app/(fpo)/decisions/page.tsx"])),
    Deliverable("M16", "Farmer portal (Hi/En) + voice", "3", "UI-05, UI-06, FR-808",
                Evidence(files=["apps/web/src/app/(farmer)/today/page.tsx"])),
    Deliverable("M17", "Unified calendar + approval gate", "3", "FR-901…906",
                Evidence(symbols=["agrivardhak.calendar.service:propose_event"])),
    Deliverable("M18", "Outcome, adherence, attribution", "3", "FR-1001…1004, INV-7",
                Evidence(symbols=["agrivardhak.learning.attribution:compute"],
                         tests=["test_attribution_requires_adherence"])),
    Deliverable("M19", "Morning briefing", "3", "FR-811",
                Evidence(symbols=["agrivardhak.orchestrator.briefing:build"])),
    Deliverable("M20", "Impact metrics panel", "3", "FR-1201…1203",
                Evidence(files=["apps/web/src/app/(fpo)/impact/page.tsx"])),

    # ---- Phase 4
    Deliverable("M21", "All nine invariant tests green", "4", "SRS §8.2",
                Evidence(tests=["test_no_execution_without_approval",
                                "test_attribution_requires_adherence",
                                "test_superseded_not_mutated",
                                "test_chemical_recommendation_has_citation_or_caution"])),
    Deliverable("M22", "Replay test (module purity)", "4", "ARCHITECTURE §9",
                Evidence(tests=["test_module_replay_is_byte_identical"])),
    Deliverable("M23", "Offline demo run (fixtures, no network)", "4", "NFR-303",
                Evidence(tests=["test_demo_runs_offline"])),

    # ---- Stretch (docs/MVP-SCOPE.md §3 "build if ahead of schedule")
    Deliverable("S1", "Outbreak clustering", "S", "FR-525",
                Evidence(symbols=["agrivardhak.intelligence.crop_health:detect_outbreak"]), "SHOULD"),
    Deliverable("S2", "Sell-now vs hold + break-even", "S", "FR-547",
                Evidence(symbols=["agrivardhak.intelligence.market:hold_analysis"]), "SHOULD"),
    Deliverable("S3", "Supply/demand gap", "S", "FR-548",
                Evidence(symbols=["agrivardhak.intelligence.market:supply_gap"]), "SHOULD"),
    Deliverable("S5", "WhatsApp inbound Q&A", "S", "ADR-0008",
                Evidence(symbols=["agrivardhak.channels.whatsapp:handle_inbound"]), "SHOULD"),
]


# --------------------------------------------------------------------------- probes


def _import_ok(spec: str) -> bool:
    """Whether ``module:symbol`` imports cleanly.

    ``find_spec`` raises rather than returning None when a *parent* package is missing, so
    the whole thing is wrapped — a not-yet-written module is a normal state here, not an
    error.
    """
    module_name, _, symbol = spec.partition(":")
    try:
        if importlib.util.find_spec(module_name) is None:
            return False
        module = importlib.import_module(module_name)
    except Exception:
        return False
    return hasattr(module, symbol) if symbol else True


def _file_ok(rel: str) -> bool:
    path = ROOT / rel
    # 200 bytes filters out an empty placeholder someone created to make a row go green.
    return path.is_file() and path.stat().st_size > 200


def collect_passing_tests() -> tuple[set[str], dict[str, int]]:
    """Run the suite verbosely and return the names that actually PASSED, plus a tally.

    Only PASSED counts. An xfail placeholder is collected and reported, but it is a promise
    rather than an implementation — treating it as evidence would let an unwritten feature
    turn a row green.
    """
    proc = subprocess.run(
        [str(API / ".venv" / "bin" / "python"), "-m", "pytest", "-v", "--tb=no",
         "-p", "no:cacheprovider", "--no-header"],
        cwd=API, capture_output=True, text=True,
    )
    passing = {
        # "tests/test_x.py::test_name PASSED [ 12%]" -> "test_name"
        line.split("::")[-1].split(" PASSED")[0].strip()
        for line in proc.stdout.splitlines()
        if "::" in line and " PASSED" in line
    }
    tally = {"passed": 0, "failed": 0, "xfailed": 0, "skipped": 0, "error": 0}
    for key in tally:
        match = re.search(rf"(\d+) {key}", proc.stdout)
        if match:
            tally[key] = int(match.group(1))
    return passing, tally


def collect_row_counts() -> dict[str, int]:
    script = (
        "import json;"
        "from sqlalchemy import create_engine, text;"
        "from agrivardhak.config import get_settings;"
        "e=create_engine(get_settings().database_url);"
        "out={};"
        "c=e.connect();"
        "out['__tables__']=c.execute(text(\"select count(*) from information_schema.tables "
        "where table_schema='public' and table_type='BASE TABLE'\")).scalar_one();"
        "out['farmer']=c.execute(text('select count(*) from farmer')).scalar_one();"
        "out['crop_cycle']=c.execute(text('select count(*) from crop_cycle')).scalar_one();"
        "out['observation']=c.execute(text('select count(*) from observation')).scalar_one();"
        "out['data_discrepancy']=c.execute(text('select count(*) from data_discrepancy')).scalar_one();"
        "print(json.dumps(out))"
    )
    proc = subprocess.run(
        [str(API / ".venv" / "bin" / "python"), "-c", script],
        cwd=API, capture_output=True, text=True,
    )
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        return {}


def evaluate(deliverable: Deliverable, passing: set[str], rows: dict[str, int]) -> tuple[str, str]:
    """Return (status, why). Status is one of: done, partial, todo, blocked."""
    checks: list[tuple[str, bool]] = []
    for spec in deliverable.evidence.symbols:
        checks.append((spec, _import_ok(spec)))
    for rel in deliverable.evidence.files:
        checks.append((rel, _file_ok(rel)))
    for name in deliverable.evidence.tests:
        checks.append((f"test:{name}", name in passing))
    for table, minimum in deliverable.evidence.rows.items():
        checks.append((f"{table}>={minimum}", rows.get(table, 0) >= minimum))

    if not checks:
        return "todo", "no evidence declared"
    passed = [c for c, ok in checks if ok]
    failed = [c for c, ok in checks if not ok]
    if not failed:
        return "done", f"{len(passed)}/{len(checks)} checks"
    if passed:
        return "partial", f"missing: {', '.join(failed[:2])}"
    return "todo", ""


ICON = {"done": "✅", "partial": "🟡", "todo": "⬜", "blocked": "🚧"}


def backfill_stats() -> tuple[int, int]:
    daily = ROOT / "seed" / "generated" / "agmarknet" / "daily"
    csv_path = ROOT / "seed" / "generated" / "agmarknet" / "series.csv"
    days = len(list(daily.glob("*.json"))) if daily.is_dir() else 0
    lines = 0
    if csv_path.is_file():
        with csv_path.open() as fh:
            lines = sum(1 for _ in fh) - 1
    return days, max(0, lines)


def render() -> str:
    sys.path.insert(0, str(API))
    passing, tally = collect_passing_tests()
    rows = collect_row_counts()

    by_phase: dict[str, list[tuple[Deliverable, str, str]]] = {}
    counts = {"done": 0, "partial": 0, "todo": 0}
    must_counts = {"done": 0, "partial": 0, "todo": 0}
    for deliverable in DELIVERABLES:
        status, why = evaluate(deliverable, passing, rows)
        by_phase.setdefault(deliverable.phase, []).append((deliverable, status, why))
        counts[status] = counts.get(status, 0) + 1
        if deliverable.priority == "MUST":
            must_counts[status] = must_counts.get(status, 0) + 1

    must_total = sum(must_counts.values())
    pct = round(100 * must_counts["done"] / must_total) if must_total else 0
    filled = round(pct / 5)
    bar = "█" * filled + "░" * (20 - filled)

    days, price_rows = backfill_stats()
    suite = "green" if tally["failed"] == 0 and tally["error"] == 0 else "**RED**"

    out: list[str] = [START, ""]
    out.append(f"_Generated by `make progress`. Every row below is verified against the "
               f"repository — a status cannot be set by editing this table._")
    out.append("")
    out.append(f"## MVP progress: {must_counts['done']}/{must_total} MUST deliverables ({pct}%)")
    out.append("")
    out.append(f"```\n{bar}  {pct}%\n```")
    out.append("")
    out.append("| | Done | In progress | Not started |")
    out.append("|---|---:|---:|---:|")
    out.append(f"| **MUST** | {must_counts['done']} | {must_counts['partial']} | {must_counts['todo']} |")
    out.append(f"| All | {counts['done']} | {counts['partial']} | {counts['todo']} |")
    out.append("")

    out.append("### Repository facts")
    out.append("")
    out.append("| Fact | Value |")
    out.append("|---|---|")
    out.append(f"| Test suite | {suite} — {tally['passed']} passed, {tally['failed']} failed, "
               f"{tally['xfailed']} xfail placeholders |")
    out.append(f"| Database tables | {rows.get('__tables__', '?')} |")
    out.append(f"| Seeded farmers | {rows.get('farmer', 0):,} |")
    out.append(f"| Seeded crop cycles | {rows.get('crop_cycle', 0):,} |")
    out.append(f"| Observations | {rows.get('observation', 0):,} |")
    out.append(f"| Open discrepancies | {rows.get('data_discrepancy', 0):,} |")
    out.append(f"| Agmarknet backfill | {days} days, {price_rows:,} price rows |")
    out.append("")

    phase_titles = {
        "0": "Phase 0 — Foundation (hours 0–6)",
        "1": "Phase 1 — Provenance & data (hours 6–18)",
        "2": "Phase 2 — Intelligence (hours 18–36)",
        "3": "Phase 3 — The loop closes (hours 36–52)",
        "4": "Phase 4 — Hardening (hours 52–66)",
        "S": "Stretch — build if ahead of schedule",
    }
    for phase in ("0", "1", "2", "3", "4", "S"):
        items = by_phase.get(phase, [])
        if not items:
            continue
        done = sum(1 for _, s, _ in items if s == "done")
        out.append(f"### {phase_titles[phase]} — {done}/{len(items)}")
        out.append("")
        out.append("| | ID | Deliverable | Requirements | Evidence |")
        out.append("|---|---|---|---|---|")
        for deliverable, status, why in items:
            out.append(
                f"| {ICON[status]} | {deliverable.id} | {deliverable.title} | "
                f"`{deliverable.requirements}` | {why} |"
            )
        out.append("")

    out.append("---")
    out.append("")
    out.append("**Adding a deliverable:** add a `Deliverable(...)` to `scripts/progress.py` with "
               "the evidence that proves it — a symbol that must import, a test that must pass, "
               "or a row count that must hold — then run `make progress`. A row with no evidence "
               "stays ⬜ regardless of what anyone writes here.")
    out.append("")
    out.append(END)
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if PROGRESS.md is stale")
    args = parser.parse_args()

    generated = render()
    current = PROGRESS.read_text() if PROGRESS.exists() else ""

    if START in current and END in current:
        head = current.split(START)[0]
        tail = current.split(END, 1)[1]
        updated = head + generated + tail
    else:
        updated = current.rstrip() + "\n\n" + generated + "\n"

    if args.check:
        if updated != current:
            print("PROGRESS.md is stale — run `make progress`", file=sys.stderr)
            return 1
        print("PROGRESS.md is current.")
        return 0

    PROGRESS.write_text(updated)
    print(f"Wrote {PROGRESS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
