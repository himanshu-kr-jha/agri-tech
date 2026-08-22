"""Canonical units (ADR-0009).

Storage is always: money in paise, area in square metres, mass in kilograms, price in
paise per kilogram. Conversion happens only at the presentation edge.

The verbosity is deliberate. A formula that reads ``area_sqm`` cannot silently be fed
acres, and a total that reads ``_paise`` cannot silently be added to rupees.
"""

from decimal import Decimal
from typing import Final

# --------------------------------------------------------------------------- constants

SQM_PER_ACRE: Final = Decimal("4046.8564224")
SQM_PER_HECTARE: Final = Decimal("10000")
PAISE_PER_RUPEE: Final = 100
KG_PER_QUINTAL: Final = Decimal("100")
KG_PER_TONNE: Final = Decimal("1000")


# --------------------------------------------------------------------------- area


def acres_to_sqm(acres: Decimal | float | int) -> Decimal:
    return Decimal(str(acres)) * SQM_PER_ACRE


def sqm_to_acres(sqm: Decimal | float | int) -> Decimal:
    return Decimal(str(sqm)) / SQM_PER_ACRE


def hectares_to_sqm(ha: Decimal | float | int) -> Decimal:
    return Decimal(str(ha)) * SQM_PER_HECTARE


def sqm_to_hectares(sqm: Decimal | float | int) -> Decimal:
    return Decimal(str(sqm)) / SQM_PER_HECTARE


# --------------------------------------------------------------------------- money


def rupees_to_paise(rupees: Decimal | float | int | str) -> int:
    """Exact conversion. Never let a float hold money."""
    return int((Decimal(str(rupees)) * PAISE_PER_RUPEE).to_integral_value())


def paise_to_rupees(paise: int) -> Decimal:
    return Decimal(paise) / PAISE_PER_RUPEE


def format_inr(paise: int, *, indian_grouping: bool = True) -> str:
    """Render paise as ₹, using lakh/crore grouping for Indian views (NFR-504)."""
    rupees = paise_to_rupees(paise)
    negative = rupees < 0
    whole = int(abs(rupees))
    fraction = abs(rupees) - whole

    if not indian_grouping:
        body = f"{whole:,}"
    else:
        s = str(whole)
        if len(s) <= 3:
            body = s
        else:
            head, tail = s[:-3], s[-3:]
            groups: list[str] = []
            while len(head) > 2:
                groups.insert(0, head[-2:])
                head = head[:-2]
            if head:
                groups.insert(0, head)
            body = ",".join([*groups, tail])

    out = f"₹{body}"
    if fraction:
        out += f"{fraction:.2f}"[1:]
    return f"-{out}" if negative else out


# --------------------------------------------------------------------------- mass


def rupees_per_quintal_to_paise_per_kg(rs_per_qtl: Decimal | float | int) -> int:
    """Agmarknet publishes ₹/quintal; our canonical unit is paise/kg.

    **The two are numerically identical**, and that is a trap rather than a convenience::

        ₹700/qtl  ->  70,000 paise/qtl  ->  70,000 / 100 kg  =  700 paise/kg

    Because the conversion looks like a no-op, someone will eventually "fix" the missing
    multiplication and be wrong by a factor of 100. This function exists so the conversion
    has a name, a docstring and a test — call it rather than assigning the value across.
    """
    return round(Decimal(str(rs_per_qtl)) * 100 / KG_PER_QUINTAL)


def paise_per_kg_to_rupees_per_quintal(paise_per_kg: int) -> Decimal:
    """Inverse of :func:`rupees_per_quintal_to_paise_per_kg`, for display in mandi terms."""
    return Decimal(paise_per_kg) * KG_PER_QUINTAL / 100


def kg_to_quintal(kg: Decimal | float | int) -> Decimal:
    return Decimal(str(kg)) / KG_PER_QUINTAL


def kg_to_tonne(kg: Decimal | float | int) -> Decimal:
    return Decimal(str(kg)) / KG_PER_TONNE


def tonne_to_kg(tonne: Decimal | float | int) -> Decimal:
    return Decimal(str(tonne)) * KG_PER_TONNE
