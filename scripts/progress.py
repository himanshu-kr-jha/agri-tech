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
    Deliverable("M4c", "Weather ingestion + crop-stress index", "1", "FR-401, FR-406",
                Evidence(symbols=["agrivardhak.ingestion.weather:load_weather",
                                  "agrivardhak.ingestion.weather:stress_index"],
                         tests=["test_monsoon_reads_wetter_than_the_dry_season",
                                "test_composite_does_not_let_stresses_cancel"])),
    Deliverable("M6", "Quality Intelligence module", "1", "FR-531…534",
                Evidence(symbols=["agrivardhak.intelligence.quality:run",
                                  "agrivardhak.intelligence.quality:predict_cycle",
                                  "agrivardhak.intelligence.quality:prediction_error"],
                         tests=["test_confidence_never_exceeds_the_observation_it_rests_on",
                                "test_grade_is_a_distribution_not_a_verdict",
                                "test_aggregate_confidence_is_a_weighted_mean_not_the_minimum"])),
    Deliverable("M7", "Market Intelligence module (effective price, scoring, allocation)", "1",
                "FR-541…545",
                Evidence(symbols=["agrivardhak.intelligence.market:run",
                                  "agrivardhak.intelligence.market:effective_price"],
                         tests=["test_nearby_cheaper_buyer_beats_distant_dearer_one",
                                "test_rejection_risk_dominates_the_deduction",
                                "test_module_is_pure_and_replayable"])),
    Deliverable("M7b", "Market data plumbing: lots, offers, price ingestion", "1", "FR-546, EXT-02",
                Evidence(symbols=["agrivardhak.ingestion.agmarknet:load_series",
                                  "agrivardhak.ingestion.agmarknet:price_points",
                                  "agrivardhak.seed.generator:_seed_lots"],
                         tests=["test_price_points_carry_resolvable_evidence",
                                "test_offers_are_anchored_to_the_real_modal_price",
                                "test_lot_quantity_equals_the_sum_of_its_items"])),
    Deliverable("M15a", "FPO dashboard: 10 cards", "1", "UI-01",
                Evidence(files=["apps/web/src/app/(fpo)/dashboard/page.tsx",
                                "apps/api/agrivardhak/api/dashboard.py"],
                         tests=["test_dashboard_returns_exactly_ten_cards",
                                "test_dashboard_distinguishes_unknown_from_zero"])),
    Deliverable("M15b", "Farmer list + drill-down", "1", "FR-806, NFR-103",
                Evidence(files=["apps/web/src/app/(fpo)/farmers/page.tsx",
                                "apps/web/src/app/(fpo)/farmers/[id]/page.tsx"],
                         tests=["test_farmer_list_filters_by_tract",
                                "test_farmer_detail_carries_provenance_on_every_plot"])),
    Deliverable("M15f", "Information boundary enforced at the API", "1", "INV-5, FR-809",
                Evidence(tests=["test_farmer_is_refused_organization_wide_views",
                                "test_farmer_may_not_open_another_farmers_record",
                                "test_unauthenticated_and_forbidden_are_distinguished"])),

    # ---- Phase 2
    Deliverable("M8", "Risk Intelligence module", "2", "FR-551…555",
                Evidence(symbols=["agrivardhak.intelligence.risk:run"])),
    Deliverable("M9", "Scheme Intelligence module", "2", "FR-561…565",
                Evidence(symbols=["agrivardhak.intelligence.scheme:run"])),
    Deliverable("M10", "Farm Intelligence module", "2", "FR-511, FR-512",
                Evidence(symbols=["agrivardhak.intelligence.farm:run"])),
    Deliverable("M11", "Crop Health Intelligence module", "2", "FR-521…526, INV-8",
                Evidence(symbols=["agrivardhak.intelligence.crop_health:run",
                                  "agrivardhak.intelligence.crop_health:build_plan"],
                         tests=["test_no_product_or_dose_is_ever_prescribed",
                                "test_two_close_candidates_produce_no_diagnosis"])),
    Deliverable("M8b", "Hazard climatology (30y ERA5) + risk register", "2", "FR-552, FR-554",
                Evidence(symbols=["agrivardhak.orchestrator.gather:load_climatology"],
                         tests=["test_a_near_certain_climate_event_is_not_ranked_as_a_risk"])),
    Deliverable("M13a", "Gather layer: database to pure module inputs", "2", "FR-500, INV-3",
                Evidence(symbols=["agrivardhak.orchestrator.gather:for_quality",
                                  "agrivardhak.orchestrator.gather:for_market",
                                  "agrivardhak.orchestrator.gather:for_risk",
                                  "agrivardhak.orchestrator.gather:for_farm",
                                  "agrivardhak.orchestrator.gather:for_scheme",
                                  "agrivardhak.orchestrator.gather:for_crop_health"])),
    Deliverable("M13b", "Reconciliation: ranking + visible override", "2", "FR-802, FR-804",
                Evidence(symbols=["agrivardhak.orchestrator.reconcile:reconcile",
                                  "agrivardhak.orchestrator.reconcile:detect_overrides"],
                         tests=["test_the_status_quo_can_be_overridden_not_only_a_proposal",
                                "test_an_override_shows_the_evidence_that_beat_the_thing_it_overrode",
                                "test_every_claim_carries_evidence"])),
    Deliverable("M13", "Orchestrator + evidence freezing", "2", "FR-801…806, FR-704",
                Evidence(symbols=["agrivardhak.orchestrator.engine:ask",
                                  "agrivardhak.orchestrator.engine:freeze",
                                  "agrivardhak.orchestrator.engine:replay"],
                         tests=["test_the_ceos_question_produces_a_packet_with_every_section",
                                "test_the_evidence_snapshot_is_hashed_over_its_content"])),
    Deliverable("M13c", "LLM narration, optional and off the critical path", "2",
                "FR-807, NFR-302, NFR-303",
                Evidence(symbols=["agrivardhak.orchestrator.narrator:narrate"],
                         tests=["test_narration_failure_returns_the_packet_unchanged"])),
    Deliverable("M14", "Approval lifecycle", "2", "FR-705…710, INV-1",
                Evidence(symbols=["agrivardhak.orchestrator.lifecycle:decide",
                                  "agrivardhak.orchestrator.lifecycle:execute"],
                         tests=["test_an_unapproved_recommendation_cannot_execute",
                                "test_the_whole_loop_runs_and_records_who_authorised_what",
                                "test_a_role_without_authority_cannot_approve"])),
    Deliverable("M14b", "Assistant + approval API", "2", "API-05, FR-807, FR-705",
                Evidence(symbols=["agrivardhak.api.assistant:ask",
                                  "agrivardhak.api.assistant:ask_stream",
                                  "agrivardhak.api.assistant:approve"],
                         tests=["test_a_farmer_cannot_ask_the_organization_assistant"])),
    Deliverable("M4d", "Scheme catalog with official portals", "2", "FR-403, FR-561",
                Evidence(symbols=["agrivardhak.intelligence.scheme:SCHEMES",
                                  "agrivardhak.intelligence.scheme:assess"],
                         tests=["test_no_application_is_ever_auto_submitted"])),
    Deliverable("M0e", "Domain-event outbox dispatcher", "2", "DR-05, ADR-0007",
                Evidence(symbols=["agrivardhak.outbox:dispatch_pending"],
                         tests=["test_a_failing_handler_does_not_stall_the_queue",
                                "test_approving_a_recommendation_creates_owned_work"])),

    # ---- Phase 3
    Deliverable("M12", "Funding requirement (thin)", "3", "FR-601…606, SAF-04",
                Evidence(symbols=["agrivardhak.intelligence.funding:run"],
                         tests=["test_no_farmer_is_ever_ranked_for_withholding_support",
                                "test_a_shortfall_is_answered_with_timing_and_sourcing"])),
    Deliverable("M15c", "Assistant view + SSE streaming", "3", "API-05, FR-807",
                Evidence(files=["apps/web/src/app/(fpo)/assistant/page.tsx",
                                "apps/web/src/components/packet.tsx"])),
    Deliverable("M15d", "Risk register + market screens", "3", "UI-08, FR-544",
                Evidence(files=["apps/web/src/app/(fpo)/risk/page.tsx",
                                "apps/web/src/app/(fpo)/market/page.tsx"])),
    Deliverable("M15e", "Decision history + frozen evidence viewer", "3", "FR-710",
                Evidence(files=["apps/web/src/app/(fpo)/decisions/page.tsx",
                                "apps/web/src/app/(fpo)/decisions/[id]/page.tsx"])),
    Deliverable("M15g", "Approval gate in the UI", "3", "INV-1, UI-11",
                Evidence(files=["apps/web/src/components/approval.tsx"])),
    Deliverable("M16", "Farmer portal (Hi/En)", "3", "UI-05, UI-06, FR-808",
                Evidence(files=["apps/web/src/app/(farmer)/today/page.tsx",
                                "apps/web/src/app/(farmer)/layout.tsx"],
                         symbols=["agrivardhak.api.assistant:farmer_today"])),
    Deliverable("M17", "Unified calendar + approval gate", "3", "FR-901…906",
                Evidence(symbols=["agrivardhak.orchestrator.lifecycle:schedule_from",
                                  "agrivardhak.orchestrator.lifecycle:task_from"],
                         tests=["test_a_calendar_event_from_a_recommendation_lands_pending_approval"])),
    Deliverable("M18", "Outcome, adherence, attribution", "3", "FR-1001…1004, INV-7, SAF-12",
                Evidence(symbols=["agrivardhak.learning.attribution:attribute",
                                  "agrivardhak.learning.attribution:record_outcome",
                                  "agrivardhak.learning.attribution:record_adherence"],
                         tests=["test_advice_that_was_never_followed_is_not_scored_as_failed",
                                "test_a_favourable_season_confounds_the_claim_rather_than_confirming_it",
                                "test_attribution_requires_adherence"])),
    Deliverable("M19", "Morning briefing", "3", "FR-811",
                Evidence(symbols=["agrivardhak.orchestrator.briefing:build"],
                         tests=["test_the_briefing_leads_with_what_needs_a_decision"])),
    Deliverable("M20", "Impact metrics panel", "3", "FR-1201…1203",
                Evidence(files=["apps/web/src/app/(fpo)/impact/page.tsx"],
                         symbols=["agrivardhak.learning.attribution:summarise"],
                         tests=["test_the_impact_summary_reports_what_it_could_not_attribute"])),

    # ---- Phase 4
    Deliverable("M21", "Every invariant asserted, no placeholders", "4", "SRS §8.2",
                Evidence(tests=["test_finding_requires_evidence",
                                "test_no_execution_without_approval",
                                "test_only_an_authorised_role_can_approve",
                                "test_attribution_requires_adherence",
                                "test_superseded_not_mutated",
                                "test_chemical_recommendation_has_citation_or_caution",
                                "test_prediction_and_recommendation_are_separate_lifecycles",
                                "test_farmer_scope_excludes_org_internal"])),
    Deliverable("M22", "Replay test (module purity)", "4", "ARCHITECTURE §9, INV-2",
                Evidence(tests=["test_a_module_run_twice_on_the_same_input_gives_the_same_answer",
                                "test_a_module_never_reaches_for_the_clock",
                                "test_a_module_never_touches_the_database",
                                "test_a_snapshot_replays_to_the_same_packet",
                                "test_reconciliation_is_deterministic"])),
    Deliverable("M23", "Offline demo run (no network)", "4", "NFR-303",
                Evidence(tests=["test_the_whole_pipeline_runs_with_the_network_unplugged",
                                "test_no_api_key_skips_narration_rather_than_erroring"])),

    # ---- Stretch (docs/MVP-SCOPE.md §3 "build if ahead of schedule")
    # ---- Phase 5: the conversational assistant (docs/adr/0011)
    Deliverable("M24", "Assistant contracts + NIM provider adapter", "5", "FR-807, NFR-302",
                Evidence(symbols=["agrivardhak.orchestrator.assistant_contracts:AssistantAnswer",
                                  "agrivardhak.orchestrator.assistant_contracts:IntentPlan",
                                  "agrivardhak.orchestrator.llm:structured"],
                         tests=["test_the_lookup_vocabulary_covers_both_audiences_and_nothing_else"])),
    Deliverable("M25", "Intent router with keyword fallback", "5", "FR-807, NFR-303",
                Evidence(symbols=["agrivardhak.orchestrator.router:plan"],
                         tests=["test_a_farmer_is_never_routed_to_a_decision",
                                "test_a_farmer_can_never_be_routed_to_an_organization_lookup"])),
    Deliverable("M26", "Named lookups, organization and farmer", "5", "FR-806, INV-5",
                Evidence(symbols=["agrivardhak.orchestrator.lookups.fpo:run",
                                  "agrivardhak.orchestrator.lookups.farmer:run"],
                         tests=["test_every_lookup_key_is_answerable",
                                "test_every_claim_carries_evidence",
                                "test_the_farmer_module_exposes_no_organization_query"])),
    Deliverable("M27", "Review gate: deterministic grounding, order-only selector", "5",
                "FR-802, FR-804",
                Evidence(symbols=["agrivardhak.orchestrator.review:grounded",
                                  "agrivardhak.orchestrator.review:select_sections"],
                         tests=["test_grounding_rejects_a_claim_that_cites_evidence_nobody_produced",
                                "test_the_selector_cannot_drop_a_protected_section"])),
    Deliverable("M28", "Chat endpoint + conversation turns", "5", "API-05, FR-709",
                Evidence(symbols=["agrivardhak.orchestrator.chat:answer",
                                  "agrivardhak.domain.models:ConversationTurn"],
                         files=["apps/web/src/components/chat.tsx",
                                "apps/web/src/app/(farmer)/ask/page.tsx"],
                         tests=["test_every_turn_is_recorded_whatever_shape_it_took",
                                "test_the_whole_chat_works_with_no_model_configured"])),
    Deliverable("M12b", "Funding intelligence reachable + announcements shared", "5",
                "FR-601…606, FR-105, INV-5",
                Evidence(symbols=["agrivardhak.orchestrator.gather:for_funding"],
                         tests=["test_internal_announcements_never_reach_a_farmer"])),
    Deliverable("S1", "Outbreak clustering", "S", "FR-525",
                Evidence(symbols=["agrivardhak.intelligence.crop_health:cluster"],
                         tests=["test_clustered_reports_raise_an_outbreak_signal",
                                "test_scattered_reports_do_not_raise_an_outbreak"]), "SHOULD"),
    Deliverable("S2", "Sell-now vs hold + break-even", "S", "FR-547",
                Evidence(symbols=["agrivardhak.intelligence.market:hold_analysis"]), "SHOULD"),
    Deliverable("S3", "Supply/demand gap", "S", "FR-548",
                Evidence(symbols=["agrivardhak.intelligence.market:supply_gap"]), "SHOULD"),
    Deliverable("S5", "WhatsApp inbound Q&A", "S", "ADR-0008",
                Evidence(symbols=["agrivardhak.channels.whatsapp:handle_inbound"]), "SHOULD"),

    # ---- Deployment: the hosted pilot (docs/adr/0018, spec 2026-08-29)
    Deliverable("M-DEPLOY", "Self-sufficient schema + API image (Supabase/Render/Vercel)",
                "D", "ADR-0018, NFR-403",
                Evidence(symbols=["agrivardhak.db.base:SEARCH_PATH_OPTION"],
                         files=["apps/api/alembic/versions/a0000000boot_extensions_and_uuidv7.py",
                                "Dockerfile", ".dockerignore"],
                         tests=["test_the_chain_has_one_base_and_it_creates_the_extensions",
                                "test_the_chain_is_linear_and_ends_in_one_head",
                                "test_alembic_and_the_runtime_engine_share_one_search_path",
                                "test_the_api_image_ships_the_runtime_fixtures"])),
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
    # "tests/test_x.py::test_name PASSED [ 12%]"          -> "test_name"
    # "tests/test_x.py::test_name[/some/path] PASSED [12%]" -> "test_name"
    # The parametrize suffix is stripped so a parametrized test can be named as evidence;
    # a partly-failing parametrization simply will not appear, since only PASSED is read.
    passing = {
        line.split("::")[-1].split(" PASSED")[0].split("[")[0].strip()
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
        "5": "Phase 5 — Conversational assistant (docs/adr/0011)",
        "S": "Stretch — build if ahead of schedule",
        "D": "Deployment — hosted pilot (docs/adr/0018)",
    }
    for phase in ("0", "1", "2", "3", "4", "5", "S", "D"):
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
