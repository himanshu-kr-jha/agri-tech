"""Is a plot's water assured? One answer, in one place.

This exists because the same test was written by hand in five places and every one of them
was wrong in the same way. Each read::

    (plot.irrigation_source or "").upper() not in ("", "RAINFED")

and the seed records rain-fed plots as ``"Rain-fed"``. Upper-cased that is ``"RAIN-FED"``,
which is not ``"RAINFED"``, so **all 510 rain-fed plots were classified as irrigated** — in
the Quality module, where it applies a 1.0 water factor instead of 0.72 to a third of the
collective's land, and in the Farm module's irrigated share.

The lesson is not that a hyphen is easy to miss. It is that a domain predicate copied to five
call sites will be wrong in five places at once, and that a comparison against a free-text
column needs a canonical list rather than a guess at the spelling in use today.
"""

from __future__ import annotations

from typing import Final

#: Every spelling that means "no assured water". Compared upper-cased and stripped, so only
#: distinct spellings need to appear. An unrecognised value is treated as *irrigated*, which
#: is the direction that fails loudly: a plot wrongly called rain-fed quietly lowers a yield
#: forecast, while one wrongly called irrigated shows up as an over-forecast against outcome.
RAINFED_MARKERS: Final[frozenset[str]] = frozenset(
    {
        "",
        "RAINFED",
        "RAIN-FED",
        "RAIN FED",
        "UNIRRIGATED",
        "NONE",
        "NIL",
    }
)


def normalise_source(irrigation_source: str | None) -> str:
    return (irrigation_source or "").strip().upper()


def water_assured(irrigation_source: str | None) -> bool:
    """True when this plot has a water source it can rely on."""
    return normalise_source(irrigation_source) not in RAINFED_MARKERS
