"""The public totals endpoint — UI-12, ADR-0026.

Two things are being defended here. The first is that the route stays reachable without a
token: it backs the landing page, which is by definition read by people who have no
account, and a 401 here is a blank front door. The second is that the numbers are the
database's numbers — the web tier keeps hard-coded fallbacks for when the API is down, and
those only stay honest if this test fails the moment the seed and the constants diverge.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from agrivardhak.api.main import app
from agrivardhak.domain.models.crops import CropCycle
from agrivardhak.domain.models.land import Plot
from agrivardhak.domain.models.organization import Farmer, Organization
from agrivardhak.domain.units import sqm_to_acres

pytestmark = pytest.mark.usefixtures("db")

URL = "/api/v1/public/platform-stats"


@pytest.fixture(scope="module")
def truth() -> dict[str, int]:
    """The counts read straight from the database, to compare the payload against."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from agrivardhak.config import get_settings

    engine = create_engine(get_settings().database_url)
    with Session(engine) as session:
        if session.execute(select(Organization)).scalars().first() is None:
            engine.dispose()
            pytest.skip("database not seeded — run `make seed`")
        counts = {
            "farmers": session.execute(select(func.count()).select_from(Farmer)).scalar_one(),
            "cycles": session.execute(select(func.count()).select_from(CropCycle)).scalar_one(),
            "orgs": session.execute(select(func.count()).select_from(Organization)).scalar_one(),
            "acres": int(
                sqm_to_acres(
                    session.execute(
                        select(func.coalesce(func.sum(Plot.area_sqm), 0)).select_from(Plot)
                    ).scalar_one()
                )
            ),
        }
    engine.dispose()
    return counts


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_platform_stats_needs_no_token(client: TestClient) -> None:
    """The whole point of the route. A token requirement here breaks the landing page."""
    assert client.get(URL).status_code == 200


def test_a_garbage_token_is_ignored_rather_than_refused(client: TestClient) -> None:
    """No optional-auth branch. A route with no scope dependency never inspects the header,
    so a stale or malformed bearer from a previous session must not turn into a 401."""
    response = client.get(URL, headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 200


def test_platform_stats_counts_match_the_database(
    client: TestClient, truth: dict[str, int]
) -> None:
    body = client.get(URL).json()
    assert body["farmers_modelled"] == truth["farmers"]
    assert body["crop_cycles_analysed"] == truth["cycles"]
    assert body["organizations"] == truth["orgs"]


def test_platform_stats_acres_are_converted_from_square_metres(
    client: TestClient, truth: dict[str, int]
) -> None:
    """Naming the mistake so it cannot come back: the column is square metres, the tile
    says acres, and the conversion belongs here rather than in a React component."""
    assert client.get(URL).json()["acres_mapped"] == truth["acres"]


def test_platform_stats_says_the_dataset_is_synthetic(client: TestClient) -> None:
    """Every seeded organization carries ``is_synthetic``; while that is all there is, the
    flag is how the landing page's claim stays checkable rather than assumed."""
    assert client.get(URL).json()["is_synthetic"] is True


def test_the_published_totals_match_the_demo_context(client: TestClient) -> None:
    """The figures the web tier falls back to when this API is unreachable.

    ``apps/web/src/lib/public-stats.ts`` hard-codes these, and the landing page prints
    them whenever the API is down. There is no compile-time bond across the two languages,
    so this test is the bond: change the seed and this fails before anyone ships a page
    quoting numbers the database no longer holds.
    """
    body = client.get(URL).json()
    assert body["farmers_modelled"] == 1000
    assert body["acres_mapped"] == pytest.approx(2412, abs=2)
    assert body["crop_cycles_analysed"] >= 7000
