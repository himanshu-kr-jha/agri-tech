"""Weather ingestion and the crop-stress index — M4c, FR-401, FR-406."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import func, select

from agrivardhak.domain.models.provenance import ExternalRecord
from agrivardhak.ingestion import weather

pytestmark = pytest.mark.usefixtures("db")

KHARIF = (dt.date(2025, 6, 20), dt.date(2025, 11, 5))
RABI = (dt.date(2025, 11, 5), dt.date(2026, 4, 1))


@pytest.fixture(scope="module")
def seeded() -> None:
    from sqlalchemy import create_engine

    from agrivardhak.config import get_settings

    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        count = conn.execute(
            select(func.count()).select_from(ExternalRecord).where(ExternalRecord.kind == "WEATHER")
        ).scalar_one()
    engine.dispose()
    if not count:
        pytest.skip("no weather loaded — run `make seed`")


def test_weather_is_loaded_for_all_three_tracts(session, seeded) -> None:
    for tract in weather.TRACTS:
        days = weather.daily_weather(session, tract=tract, start=KHARIF[0], end=KHARIF[1])
        assert len(days) > 100, f"{tract} has too little weather to compute a normal"


def test_loading_twice_inserts_nothing(session, seeded) -> None:
    assert weather.load_weather(session) == 0


def test_stress_index_carries_resolvable_evidence(session, seeded) -> None:
    index = weather.stress_index(session, tract="DOAB", start=KHARIF[0], end=KHARIF[1])
    assert index is not None
    assert index.evidence is not None
    assert session.get(ExternalRecord, index.evidence.id) is not None


def test_monsoon_reads_wetter_than_the_dry_season(session, seeded) -> None:
    """The index has to track reality before it can be trusted to flag a deviation."""
    kharif = weather.stress_index(session, tract="DOAB", start=KHARIF[0], end=KHARIF[1])
    rabi = weather.stress_index(session, tract="DOAB", start=RABI[0], end=RABI[1])
    assert kharif is not None and rabi is not None
    assert kharif.rainfall_sd > rabi.rainfall_sd
    assert kharif.humidity_sd > rabi.humidity_sd


def test_composite_does_not_let_stresses_cancel(session, seeded) -> None:
    """Root-sum-square, not a signed sum.

    A dry *and* hot season is worse than either alone. A signed sum would let a negative
    rainfall deviation and a positive heat one cancel into a falsely calm number — which is
    exactly the season an FPO most needs flagged.
    """
    index = weather.stress_index(session, tract="DOAB", start=RABI[0], end=RABI[1])
    assert index is not None
    assert index.rainfall_sd < 0 < abs(index.heat_sd), "expected a dry season for this test"
    assert index.composite_sd >= max(abs(index.rainfall_sd), abs(index.heat_sd))


def test_cold_is_flagged_as_a_rabi_hazard_not_ignored(session, seeded) -> None:
    """Frost damages gram, mustard and potato. A one-sided heat check would miss it."""
    index = weather.stress_index(session, tract="DOAB", start=RABI[0], end=RABI[1])
    assert index is not None
    if index.heat_sd < -1.0:
        assert any("cold-wave" in note for note in index.notes)


def test_too_little_weather_returns_none_rather_than_assuming_a_normal_season(
    session, seeded
) -> None:
    """ "We do not know" and "it was fine" are different answers (NFR-301)."""
    index = weather.stress_index(
        session, tract="DOAB", start=dt.date(2030, 1, 1), end=dt.date(2030, 1, 20)
    )
    assert index is None


def test_unknown_tract_returns_none(session, seeded) -> None:
    assert weather.stress_index(session, tract="ATLANTIS", start=KHARIF[0], end=KHARIF[1]) is None


def test_tracts_are_not_claimed_to_have_different_weather(session, seeded) -> None:
    """Documents a real limitation rather than papering over it.

    The three centroids are ~40 km apart and ERA5's grid is coarse, so they see essentially
    the same season. The tract model still holds — but through irrigation coverage, not
    rainfall. If this test ever fails because the spread widened, the docs in
    `docs/DEMO-CONTEXT.md` §2 need revisiting, not deleting.
    """
    composites = []
    for tract in weather.TRACTS:
        index = weather.stress_index(session, tract=tract, start=KHARIF[0], end=KHARIF[1])
        assert index is not None
        composites.append(index.composite_sd)
    spread = max(composites) - min(composites)
    assert spread < 0.5, (
        "tracts now differ materially in weather — update the claim in DEMO-CONTEXT §2"
    )
