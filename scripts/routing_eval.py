#!/usr/bin/env python
"""Routing eval — how well does the intent router understand real questions?

Deliberately **not** a pytest. The router calls a language model, so its answers vary with
the provider, the model and the weather; wiring that into ``make test`` would mean a red
build because an 8B had an off day, and a suite people learn to ignore. The invariants that
must *always* hold — closed vocabulary, audience filtering, keyword fallback — are asserted
deterministically in ``tests/test_assistant_chat.py``. This measures the thing that can only
be measured empirically: accuracy on questions a real person would type.

    make routing-eval                 # everything
    make routing-eval a="--audience FARMER --verbose"

Exits non-zero below ``--threshold`` so it *can* gate a release when someone chooses to run
it, without gating every commit.

Cases carry a set of acceptable answers, not one. "What is happening with prices?" is
legitimately either MARKET_SNAPSHOT or WHATS_CHANGED, and marking one wrong would be scoring
the router against our own arbitrary preference rather than against usefulness.
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from agrivardhak.orchestrator import llm, router


@dataclass(frozen=True)
class Case:
    question: str
    #: Acceptable outcomes — a LookupKey value, a shape when no lookup should be chosen, or
    #: ``UNKNOWN_CROP`` when the question names a crop this collective does not grow.
    expect: frozenset[str]
    audience: str = "FPO"
    note: str = ""


def one(question: str, *expect: str, audience: str = "FPO", note: str = "") -> Case:
    return Case(question, frozenset(expect), audience, note)


CASES: list[Case] = [
    # -- plain facts. The gap that started this: these used to return a crop plan.
    one("how many farmers do we have", "MEMBERSHIP_SUMMARY"),
    one("how many members are in the FPO", "MEMBERSHIP_SUMMARY"),
    one("how many women farmers are registered with us", "MEMBERSHIP_SUMMARY"),
    one("how many villages do our members come from", "MEMBERSHIP_SUMMARY"),
    one("give me a breakdown of our membership", "MEMBERSHIP_SUMMARY"),
    one("kitne kisan hain hamare paas", "MEMBERSHIP_SUMMARY", note="Hinglish"),
    one("how much land does the collective farm", "LAND_SUMMARY"),
    one("how many acres do we have", "LAND_SUMMARY"),
    one("how many plots are registered", "LAND_SUMMARY"),
    one("how much of our land is irrigated", "LAND_SUMMARY"),
    one("what is our average holding size", "LAND_SUMMARY", "MEMBERSHIP_SUMMARY"),
    # -- priorities
    one("what should I prioritize today", "TODAYS_PRIORITIES"),
    one(
        "what needs my attention right now",
        "TODAYS_PRIORITIES",
        "FARMERS_NEEDING_ATTENTION",
    ),
    one("is anything waiting on a decision from me", "TODAYS_PRIORITIES"),
    one("what is on my plate this morning", "TODAYS_PRIORITIES"),
    # -- members needing help
    one("which farmers require attention", "FARMERS_NEEDING_ATTENTION"),
    one("which members are struggling", "FARMERS_NEEDING_ATTENTION"),
    one("whose crops look unhealthy", "FARMERS_NEEDING_ATTENTION"),
    one("who should the field officer visit this week", "FARMERS_NEEDING_ATTENTION"),
    # -- production
    one(
        "how much production do we expect over the next 30 days", "PRODUCTION_FORECAST"
    ),
    one("what tonnage are we expecting this season", "PRODUCTION_FORECAST"),
    one("what is the expected yield", "PRODUCTION_FORECAST"),
    # -- risk
    one("what are the biggest risks facing our FPO this month", "RISK_SUMMARY"),
    one("what could go wrong this season", "RISK_SUMMARY"),
    one("how exposed are we to a price fall", "RISK_SUMMARY", "MARKET_SNAPSHOT"),
    # -- schemes
    one("which farmers may benefit from government schemes", "SCHEME_ELIGIBILITY"),
    one("what subsidies can our members claim", "SCHEME_ELIGIBILITY"),
    one("are our members eligible for crop insurance", "SCHEME_ELIGIBILITY"),
    # -- market
    one("what are potato prices right now", "MARKET_SNAPSHOT"),
    one("what offers do we have on the table", "MARKET_SNAPSHOT"),
    one("what is happening with prices", "MARKET_SNAPSHOT", "WHATS_CHANGED"),
    # -- funding
    one("can we afford this season", "FUNDING_POSITION"),
    one("what is our working capital position", "FUNDING_POSITION"),
    one("do we have enough cash for inputs", "FUNDING_POSITION"),
    # -- change
    one(
        "what changed in the agricultural environment that could affect us",
        "WHATS_CHANGED",
    ),
    one("anything new since last week", "WHATS_CHANGED"),
    # -- decisions: these commit money, land or a season
    one(
        "what should we do this season to maximize sustainable farmer income",
        "DECISION",
    ),
    one("who should we sell the paddy to", "DECISION"),
    one("who should we sell our expected tomato production to", "UNKNOWN_CROP"),
    one("should we hold the potato in cold storage or sell now", "DECISION"),
    one("what should we plant in Yamuna-Par next season", "DECISION"),
    one("how will we increase guava sales this year", "DECISION"),
    # -- crops this collective does not grow. Answering about paddy instead is the failure
    #    that started this; the router must name the crop so the caller can say "not on record".
    one("how grapes production be increased", "UNKNOWN_CROP"),
    one("how can we increase tomato sales", "UNKNOWN_CROP"),
    one("should we plant sugarcane next season", "UNKNOWN_CROP"),
    one("what about our apple orchards", "UNKNOWN_CROP"),
    one("how is the soybean doing", "UNKNOWN_CROP"),
    # -- out of scope
    one("what is the capital of France", "REFUSE"),
    one("write me a poem about tractors", "REFUSE"),
    # -- farmer: their own plain facts
    one("how much land do I have", "MY_FARM_PROFILE", audience="FARMER"),
    one("how many plots do I farm", "MY_FARM_PROFILE", audience="FARMER"),
    one(
        "what am I growing right now",
        "MY_FARM_PROFILE",
        "MY_YIELD_GAP",
        audience="FARMER",
    ),
    # -- farmer: yield
    one("how can I increase the yield of my crops", "MY_YIELD_GAP", audience="FARMER"),
    one(
        "why is my harvest lower than my neighbour's", "MY_YIELD_GAP", audience="FARMER"
    ),
    one("how is my crop doing", "MY_YIELD_GAP", "MY_FARM_PROFILE", audience="FARMER"),
    # -- farmer: today
    one("what should I do on my farm today", "MY_TASKS_TODAY", audience="FARMER"),
    one("is there anything scheduled for me", "MY_TASKS_TODAY", audience="FARMER"),
    # -- farmer: schemes and announcements
    one("what schemes may apply to me", "MY_SCHEMES", audience="FARMER"),
    one("can I get the kisan credit card", "MY_SCHEMES", audience="FARMER"),
    one("what has the FPO told members", "MY_ANNOUNCEMENTS", audience="FARMER"),
    one("any news from the collective", "MY_ANNOUNCEMENTS", audience="FARMER"),
    # -- farmer: the information boundary
    one("what is the FPO negotiating with buyers", "REFUSE", audience="FARMER"),
    one("what did other farmers in my village earn", "REFUSE", audience="FARMER"),
    one("show me the collective's bank balance", "REFUSE", audience="FARMER"),
]


def evaluate(
    case: Case, *, delay: float = 0.0, retries: int = 2
) -> tuple[Case, str, bool, bool]:
    """Route one case, retrying when the provider throttles us.

    The retry lives here and deliberately **not** in ``orchestrator/llm.py``. In production a
    429 should degrade to keyword routing immediately — a CEO waiting an extra five seconds
    for a backoff is worse than a slightly worse route. In an eval the opposite is true: an
    unmeasured case is worthless, and nobody is waiting.
    """
    for attempt in range(retries + 1):
        if delay:
            time.sleep(delay)
        plan = router.plan(question=case.question, audience=case.audience)
        if not plan.fell_back or attempt == retries:
            # UNKNOWN_CROP is not a shape the router returns — it is what the router
            # *reporting an unrecognised crop* means downstream, where chat.answer turns it
            # into "nothing on record is about grapes". The eval scores the router's job,
            # which is capturing the crop name, not the answer that follows from it.
            if plan.entities.get("unknown_crop"):
                got = "UNKNOWN_CROP"
            else:
                got = plan.lookup.value if plan.lookup else plan.shape.value
            return case, got, got in case.expect, plan.fell_back
        time.sleep(4.0 * (attempt + 1))
    raise AssertionError("unreachable")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--audience", choices=("FPO", "FARMER"), help="run only one audience"
    )
    parser.add_argument(
        "--threshold", type=float, default=0.85, help="minimum pass rate"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="print passes as well as misses"
    )
    # Three, not eight. The provider rate-limits, and a 429 makes the router fall back to
    # keywords, which then reads as a routing miss. The eval is slow on purpose.
    parser.add_argument("--workers", type=int, default=2, help="concurrent requests")
    parser.add_argument(
        "--delay", type=float, default=0.35, help="seconds to pace each request"
    )
    args = parser.parse_args()

    if not llm.available():
        print(
            "No model configured, so this would measure the keyword fallback rather than the\n"
            "router. Set AGRI_NVIDIA_API_KEY in apps/api/.env and try again.",
            file=sys.stderr,
        )
        return 2

    cases = [c for c in CASES if not args.audience or c.audience == args.audience]
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        results = list(pool.map(lambda c: evaluate(c, delay=args.delay), cases))

    # A case that fell back measured the keyword planner, not the router. Scoring it either
    # way would be dishonest: as a miss it blames the model for a 429, as a pass it hides an
    # outage. Excluded from the denominator and reported separately.
    scored = [r for r in results if not r[3]]
    degraded = [r for r in results if r[3]]
    misses = [r for r in scored if not r[2]]

    for case, got, ok, fell_back in results:
        if fell_back:
            print(
                f"skip [{case.audience:6s}] {case.question[:56]:58s} (model unreachable)"
            )
            continue
        if ok and not args.verbose:
            continue
        mark = "ok  " if ok else "MISS"
        want = " | ".join(sorted(case.expect))
        print(
            f"{mark} [{case.audience:6s}] {case.question[:56]:58s} got={got:26s} want={want}"
        )

    passed = len(scored) - len(misses)
    rate = passed / len(scored) if scored else 0.0
    print(f"\n{passed}/{len(scored)} routed correctly ({rate:.0%})")
    if degraded:
        print(
            f"{len(degraded)} of {len(results)} cases never reached the model and were not "
            f"scored — rate limiting, most likely. Re-run with --workers 1."
        )
        if len(degraded) / len(results) > 0.2:
            print(
                "\nMore than a fifth of the run never reached the model. This is an "
                "unmeasured run, not a low score.",
                file=sys.stderr,
            )
            return 2

    by_target: dict[str, list[bool]] = {}
    for case, _got, ok, _fb in scored:
        by_target.setdefault(" | ".join(sorted(case.expect)), []).append(ok)
    weak = {t: v for t, v in by_target.items() if not all(v)}
    if weak:
        print("\nWeakest targets:")
        for target, oks in sorted(weak.items(), key=lambda kv: sum(kv[1]) / len(kv[1])):
            print(f"  {sum(oks)}/{len(oks)}  {target}")

    if rate < args.threshold:
        print(f"\nBelow the {args.threshold:.0%} threshold.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
