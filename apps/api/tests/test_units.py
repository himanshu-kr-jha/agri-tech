"""Unit conversion tests (ADR-0009).

Money and unit bugs are the class of error that is expensive and invisible: nothing crashes,
the number is just wrong by a factor of 100, and it renders perfectly.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from agrivardhak.domain import units


def test_rupees_per_quintal_and_paise_per_kg_are_numerically_identical() -> None:
    """The conversion that looks like a bug.

    Agmarknet gives ₹/quintal, we store paise/kg, and the numbers are the same. Anyone who
    "fixes" this by multiplying will be wrong by 100x, so the identity is pinned here.
    """
    for rs_per_qtl in (700, 2495, 6193, 38456):
        assert units.rupees_per_quintal_to_paise_per_kg(rs_per_qtl) == rs_per_qtl


def test_quintal_conversion_round_trips() -> None:
    for rs_per_qtl in (700, 2495, 6193):
        paise = units.rupees_per_quintal_to_paise_per_kg(rs_per_qtl)
        assert units.paise_per_kg_to_rupees_per_quintal(paise) == Decimal(rs_per_qtl)


def test_real_potato_price_reads_correctly() -> None:
    """August 2026 Prayagraj modal was ₹700/qtl. That is ₹7/kg, not ₹700/kg."""
    paise = units.rupees_per_quintal_to_paise_per_kg(700)
    assert paise == 700
    assert units.paise_to_rupees(paise) == Decimal(7)


def test_money_never_touches_a_float() -> None:
    """0.1 + 0.2 problems in a funding allocation are not recoverable."""
    assert units.rupees_to_paise("0.07") == 7
    assert units.rupees_to_paise(Decimal("35000.55")) == 3_500_055
    total = sum(units.rupees_to_paise("0.1") for _ in range(10))
    assert total == 100, "exactly ₹1, with no drift"


def test_area_round_trips_between_acres_and_sqm() -> None:
    assert units.sqm_to_acres(units.acres_to_sqm(2.5)) == pytest.approx(Decimal("2.5"))
    assert units.sqm_to_hectares(units.hectares_to_sqm(1.0)) == pytest.approx(Decimal("1"))


def test_the_demo_acreage_converts_as_documented() -> None:
    """docs/DEMO-CONTEXT.md §5.1: 976.2 ha is 2,412 acres."""
    sqm = units.hectares_to_sqm(Decimal("976.2"))
    assert float(units.sqm_to_acres(sqm)) == pytest.approx(2412, abs=1)


def test_indian_grouping_uses_lakh_and_crore() -> None:
    """NFR-504. ₹12,34,567 — not ₹1,234,567."""
    assert units.format_inr(123_456_700) == "₹12,34,567"
    assert units.format_inr(100_000_00) == "₹1,00,000"
    assert units.format_inr(999_00) == "₹999"


def test_western_grouping_is_available_for_english_views() -> None:
    assert units.format_inr(123_456_700, indian_grouping=False) == "₹1,234,567"


def test_negative_money_formats_with_the_sign_outside() -> None:
    assert units.format_inr(-50_000_00).startswith("-₹")


def test_mass_conversions() -> None:
    assert units.kg_to_tonne(1500) == Decimal("1.5")
    assert units.kg_to_quintal(250) == Decimal("2.5")
    assert units.tonne_to_kg(2) == Decimal("2000")
