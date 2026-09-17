"""The translation scorer — ``agrivardhak.translation.quality``.

The live accuracy eval (``make translation-eval``) is only as trustworthy as the thing that
scores it. These pin the scorer down offline: a check that silently passes everything would
report a perfect model forever.
"""

from __future__ import annotations

from agrivardhak.translation.quality import Case, chrf, fold, numbers, score


def test_fold_treats_nukta_and_chandrabindu_variants_as_one_spelling() -> None:
    assert fold("फ़सल") == fold("फसल")
    assert fold("सूचनाएँ") == fold("सूचनाएं")
    assert fold("  Crop   Insurance ") == "crop insurance"


def test_numbers_ignore_grouping_style_but_not_value() -> None:
    assert numbers("₹1,20,000 on 12 October") == numbers("₹120,000 on 12 अक्टूबर")
    assert numbers("2.5 acres") != numbers("25 acres")


def test_chrf_is_high_for_identical_and_low_for_unrelated() -> None:
    assert chrf("फ़सल की स्थिति", "फसल की स्थिति") == 100.0
    assert chrf("मौसम का पूर्वानुमान", "फ़सल की स्थिति") < 30
    assert chrf("", "anything") == 0.0


def test_a_changed_number_fails() -> None:
    case = Case("Apply 25 kg per acre", "hi-IN", "numbers")
    assert score(case, "प्रति एकड़ 25 किलो डालें").passed
    result = score(case, "प्रति एकड़ 52 किलो डालें")
    assert not result.passed
    assert "numbers lost" in result.failures[0]


def test_must_include_accepts_any_alternative_in_a_group() -> None:
    case = Case("Crop insurance", "hi-IN", "terms", must_include=(("फसल बीमा", "फ़सल बीमा"),))
    assert score(case, "फ़सल बीमा").passed
    assert not score(case, "फ़सल सुरक्षा").passed


def test_must_exclude_and_verbatim() -> None:
    case = Case(
        "PM-KISAN is not confirmed",
        "hi-IN",
        "safety",
        must_exclude=("पुष्टि हो गई",),
        verbatim=("PM-KISAN",),
    )
    assert score(case, "PM-KISAN की पुष्टि नहीं हुई है").passed
    failures = score(case, "पीएम-किसान की पुष्टि हो गई").failures
    assert any("forbidden" in f for f in failures)
    assert any("verbatim" in f for f in failures)


def test_min_chrf_gates_only_when_set() -> None:
    reported = Case("Grade", "hi-IN", "chrome", reference="श्रेणी")
    gated = Case("Grade", "hi-IN", "chrome", reference="श्रेणी", min_chrf=60)
    assert score(reported, "ग्रेड").passed
    assert not score(gated, "ग्रेड").passed


def test_no_output_is_a_failure() -> None:
    assert not score(Case("Seed", "hi-IN", "chrome"), None).passed
