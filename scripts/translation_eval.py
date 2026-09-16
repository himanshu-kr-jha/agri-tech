#!/usr/bin/env python
"""Translation eval — how accurately does Sarvam translate what this product shows?

Deliberately **not** a pytest, for the same reason as ``routing_eval.py``: it calls a live
model, whose output varies with the provider and the day, and ``make test`` must stay
reproducible offline (NFR-303). The scorer itself is tested offline in
``tests/test_translation_quality.py``. This measures the model.

    make translation-eval                         # everything
    make translation-eval a="--category numbers --verbose"

Calls Sarvam directly, **bypassing the translation memory**, so it measures the model rather
than whatever is cached. Exits non-zero below ``--threshold`` so it can gate a model change.

What the cases check is what would hurt a reader if it went wrong — numbers, negations,
legal categories, scheme names, IPM safety wording — not stylistic preference. Alternatives
are generous on purpose: a case that fails because Sarvam wrote खेती where we thought of कृषि
is measuring our taste, not its accuracy.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from agrivardhak.translation import sarvam  # noqa: E402
from agrivardhak.translation.quality import Case, Result, score  # noqa: E402

HI, EN = "hi-IN", "en-IN"

#: Hindi for "woman" / "man". Our source text never states a gender for the approver.
GENDERED = ("महिला", "पुरुष")

#: Names written in Devanagari are how Hindi prints them (पीएम-किसान, डी.ए.पी.), so a case
#: accepts either script. Keeping them in Latin on screen is the UI's job (`translate="no"`),
#: not something to score the model on.
PM_KISAN = ("PM-KISAN", "पीएम-किसान", "पीएम किसान")
AGRIVARDHAK = ("AgriVardhak", "एग्रीवर्धक", "एग्रीवर्धन")
DAP = ("DAP", "डीएपी", "डी.ए.पी", "डी ए पी")


def _dictionary_cases() -> list[Case]:
    """Interface chrome with a human Hindi reference: the static dictionary itself.

    Reported with chrF, gated only on content-bearing checks. A short label can be rendered
    correctly in words the dictionary did not choose (ग्रेड vs श्रेणी), so a low chrF on a
    two-word label is information, not a failure.
    """
    strings = json.loads((ROOT / "apps/web/src/lib/strings.json").read_text(encoding="utf-8"))
    picks = ["today.myCrops", "today.expectedHarvest", "nav.notices", "login.password",
             "notices.inert", "ask.example.today", "console.humanApproves"]
    #: Measured failures worth pinning. "A human approves" came back as "a woman approves"
    #: from sarvam-translate:v1 (2026-09-16) — INV-1 is about *a person*, of any gender.
    exclude = {"console.humanApproves": GENDERED}
    return [
        Case(strings[k]["en"], HI, "chrome", reference=strings[k]["hi"],
             must_exclude=exclude.get(k, ()), note=k)
        for k in picks
    ]


CASES: list[Case] = [
    *_dictionary_cases(),
    # ---------------------------------------------------------------- numbers & units
    Case("Apply 50 kg of DAP per acre before sowing.", HI, "numbers",
         must_include=(("एकड़", "एकड"), ("बुवाई", "बोआई", "बुआई"), DAP)),
    Case("Expected harvest: 12 October, about 4.2 tonnes from 2.5 acres.", HI, "numbers",
         must_include=(("अक्टूबर",), ("टन",), ("एकड़", "एकड"))),
    Case("The collective will pay ₹2,300 per quintal for paddy.", HI, "numbers",
         must_include=(("क्विंटल", "कुंतल"), ("धान",))),
    Case("Crop health 82%, confidence 0.81.", HI, "numbers",
         must_include=(("फसल", "फ़सल"),)),
    Case("धान की अनुमानित उपज 45 क्विंटल प्रति हेक्टेयर है।", EN, "numbers",
         must_include=(("paddy", "rice"), ("quintal",), ("hectare",)),
         note="धान flattened to 'crop' loses which crop the number is about"),
    Case("आवेदन की अंतिम तिथि 31 जुलाई 2026 है।", EN, "numbers",
         must_include=(("july",), ("last date", "deadline", "due date", "final date"))),
    # ---------------------------------------------------------------- negation & safety
    Case("General departmental guidance, not confirmation of any benefit.", HI, "negation",
         must_include=(("नहीं", "न कि"),), note="notices.inert — dropping 'not' promises a benefit"),
    Case("This page does not tell you whether you qualify for anything.", HI, "negation",
         must_include=(("नहीं",), ("पात्र", "योग्य"))),
    Case("Do not spray during flowering or when rain is expected within 24 hours.", HI, "negation",
         must_include=(("न ", "नहीं", "मत"), ("फूल",), ("बारिश", "वर्षा"))),
    Case("यह पृष्ठ यह नहीं बताता कि आप किसी योजना के पात्र हैं या नहीं।", EN, "negation",
         must_include=(("not", "n't"), ("eligible", "qualify", "entitled"))),
    Case("AgriVardhak recommends. A human approves before anything executes.", HI, "safety",
         must_include=(("स्वीकृ", "मंज़ूर", "मंजूर", "अनुमोदन"), AGRIVARDHAK),
         must_exclude=GENDERED, note="INV-1 wording"),
    Case("Chemical control is a last resort: consult the product label and your local agronomist.",
         HI, "safety",
         must_include=(("लेबल",), ("रासायनिक",), ("कृषि विशेषज्ञ", "कृषि वैज्ञानिक", "कृषि विज्ञानी",
                                               "कृषि अधिकारी", "कृषिविज्ञानी", "कृषि सलाहकार"))),
    # ---------------------------------------------------------------- legal & scheme terms
    Case("लघु एवं सीमांत कृषकों को बीज पर 50 प्रतिशत अनुदान देय है।", EN, "legal",
         must_include=(("small and marginal",), ("seed",), ("subsidy", "grant", "assistance")),
         note="लघु एवं सीमांत कृषक is a legal category (ADR-0015)"),
    Case("प्रधानमंत्री फसल बीमा योजना के अंतर्गत खरीफ फसलों का बीमा कराएं।", EN, "legal",
         must_include=(("pradhan mantri fasal bima", "pmfby", "crop insurance"), ("kharif",),
                       ("insur",))),
    Case("Register for PM-KISAN at your block office.", HI, "legal",
         must_include=(("विकास खंड", "ब्लॉक", "प्रखंड", "खंड विकास"), PM_KISAN)),
    Case("मृदा परीक्षण हेतु नमूना कृषि रक्षा इकाई पर जमा करें।", EN, "legal",
         must_include=(("soil",), ("sample",), ("plant protection", "crop protection",
                                                "agriculture protection", "agricultural protection")),
         note="कृषि रक्षा इकाई is the block's plant protection unit, not 'defence' or 'research'"),
    # ---------------------------------------------------------------- agronomy content
    Case("Irrigate the wheat plot lightly; the soil moisture is low.", HI, "agronomy",
         must_include=(("गेहूं", "गेहूँ"), ("सिंचाई", "सींच", "पानी दें", "पानी दे"), ("नमी",))),
    Case("Yellow leaves on mustard may indicate aphid attack.", HI, "agronomy",
         must_include=(("सरसों",), ("पत्ति", "पत्ते"), ("माहू", "एफिड", "चेपा", "एफिड्स", "माहो"))),
    Case("फसल में झुलसा रोग के लक्षण दिखें तो खेत का निरीक्षण करें।", EN, "agronomy",
         must_include=(("blight",), ("inspect", "check", "examine", "survey")),
         must_exclude=("bollworm", "daily"),
         note="sarvam-translate:v1 returned 'Inspect the field daily for any sign of bollworm'"),
    Case("Sell now or hold: prices at Prayagraj mandi rose this week.", HI, "agronomy",
         must_include=(("मंडी",), ("प्रयागराज",), ("कीमत", "भाव", "दाम", "मूल्य"))),
    # ---------------------------------------------------------------- mixed & fragments
    Case("Given to the collective", HI, "fragment",
         must_include=(("सामूहिक", "समिति", "समूह", "संगठन"),)),
    Case("Sign in as", HI, "fragment", must_include=(("साइन इन", "लॉग इन"),)),
]


def run_case(case: Case) -> tuple[Result, float]:
    source = "hi-IN" if case.target == EN else "en-IN"
    started = time.perf_counter()
    translated = sarvam.translate_many([case.source], source, case.target).get(case.source)
    return score(case, translated), time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--category", help="only cases in this category")
    parser.add_argument("--verbose", action="store_true", help="print every output")
    parser.add_argument("--threshold", type=float, default=0.85, help="minimum pass rate")
    args = parser.parse_args()

    if not sarvam.available():
        print("No Sarvam key (AGRI_SARVAM_API_KEY) or AGRI_USE_FIXTURES=true — nothing to measure.")
        return 2

    cases = [c for c in CASES if not args.category or c.category == args.category]
    results: list[tuple[Result, float]] = [run_case(c) for c in cases]

    by_category: dict[str, list[Result]] = {}
    for result, seconds in results:
        by_category.setdefault(result.case.category, []).append(result)
        mark = "PASS" if result.passed else "FAIL"
        if args.verbose or not result.passed:
            chrf_note = f"  chrF {result.chrf:5.1f}" if result.chrf is not None else ""
            print(f"[{mark}] {result.case.category:<9} {seconds:4.1f}s{chrf_note}")
            print(f"        {result.case.source}")
            print(f"     →  {result.output}")
            for failure in result.failures:
                print(f"        ✗ {failure}")
            if result.case.note:
                print(f"        ({result.case.note})")

    print("\ncategory   pass  total")
    for category, rs in by_category.items():
        print(f"{category:<10} {sum(r.passed for r in rs):>4}  {len(rs):>5}")

    passed = sum(r.passed for r, _ in results)
    rate = passed / len(results) if results else 0.0
    chrfs = [r.chrf for r, _ in results if r.chrf is not None]
    mean_latency = sum(s for _, s in results) / len(results) if results else 0.0
    print(f"\npassed {passed}/{len(results)} ({rate:.0%}) · threshold {args.threshold:.0%}")
    if chrfs:
        print(f"mean chrF vs the hand-written dictionary: {sum(chrfs) / len(chrfs):.1f}")
    print(f"mean latency per case: {mean_latency:.2f}s")
    return 0 if rate >= args.threshold else 1


if __name__ == "__main__":
    raise SystemExit(main())
