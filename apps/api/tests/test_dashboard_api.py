"""FPO console API — UI-01, FR-806, and the boundary that guards them.

The boundary tests are the important half. A dashboard that leaks is worse than no
dashboard, and INV-5 says the enforcement lives here rather than in the UI.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from agrivardhak.api.auth import issue_token
from agrivardhak.api.main import app
from agrivardhak.domain.enums import Role
from agrivardhak.domain.models.organization import Farmer, Organization, RoleGrant

pytestmark = pytest.mark.usefixtures("db")


@pytest.fixture(scope="module")
def seeded() -> dict[str, uuid.UUID]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from agrivardhak.config import get_settings

    engine = create_engine(get_settings().database_url)
    with Session(engine) as session:
        org = session.execute(select(Organization)).scalars().first()
        if org is None:
            engine.dispose()
            pytest.skip("database not seeded — run `make seed`")
        grant = (
            session.execute(select(RoleGrant).where(RoleGrant.role == Role.FPO_CEO))
            .scalars()
            .first()
        )
        farmers = list(session.execute(select(Farmer).limit(2)).scalars())
        total = session.execute(select(func.count()).select_from(Farmer)).scalar_one()
    engine.dispose()
    if grant is None or len(farmers) < 2:
        pytest.skip("seed incomplete")
    return {
        "org_id": org.id,
        "ceo_user_id": grant.user_id,
        "farmer_id": farmers[0].id,
        "other_farmer_id": farmers[1].id,
        "farmer_count": total,
    }


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _ceo(seeded) -> dict[str, str]:
    token = issue_token(
        user_id=seeded["ceo_user_id"], roles={Role.FPO_CEO}, organization_id=seeded["org_id"]
    )
    return {"Authorization": f"Bearer {token}"}


def _farmer(seeded) -> dict[str, str]:
    token = issue_token(
        user_id=uuid.uuid4(),
        roles={Role.FARMER},
        organization_id=seeded["org_id"],
        farmer_id=seeded["farmer_id"],
    )
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- dashboard


def test_dashboard_returns_exactly_ten_cards(client, seeded) -> None:
    """UI-01 fixes ten. A dashboard with forty tiles is one nobody reads."""
    response = client.get("/api/v1/fpo/dashboard", headers=_ceo(seeded))
    assert response.status_code == 200
    assert len(response.json()["cards"]) == 10


def test_dashboard_labels_itself_as_demo_data(client, seeded) -> None:
    """C-2 / UI-04: nothing here may present itself as a real collective."""
    body = client.get("/api/v1/fpo/dashboard", headers=_ceo(seeded)).json()
    assert body["organization"]["is_synthetic"] is True


def test_dashboard_reports_the_documented_membership_and_acreage(client, seeded) -> None:
    cards = {
        c["key"]: c
        for c in client.get("/api/v1/fpo/dashboard", headers=_ceo(seeded)).json()["cards"]
    }
    assert cards["farmers"]["value"] == 1000
    assert cards["area"]["value"] == pytest.approx(2412, abs=2)


def test_dashboard_distinguishes_unknown_from_zero(client, seeded) -> None:
    """FR-103. Cold-store capacity is unknown, and the card has to say so."""
    cards = {
        c["key"]: c
        for c in client.get("/api/v1/fpo/dashboard", headers=_ceo(seeded)).json()["cards"]
    }
    assert "unknown" in (cards["capital"]["detail"] or "")


def test_dashboard_surfaces_open_data_conflicts(client, seeded) -> None:
    """UI-10: conflicts belong at the point of use, not buried in an admin screen."""
    cards = {
        c["key"]: c
        for c in client.get("/api/v1/fpo/dashboard", headers=_ceo(seeded)).json()["cards"]
    }
    assert cards["data_conflicts"]["value"] > 0


def test_dashboard_hrefs_are_built_routes(client, seeded) -> None:
    """A tile may not advertise a screen the web app does not serve.

    This is a regression test with a scar behind it. Four of the ten tiles linked to
    ``/production``, ``/schemes`` and ``/discrepancies``; only the last of those was ever
    built, so three tiles were clickable 404s on the primary screen of the product. Nothing
    caught it because the API was, by itself, perfectly correct.

    The route list is maintained by hand, which is the honest cost of the API deciding web
    routes at all. Adding a page? Add it here. Removing one? This test tells you which
    tiles now point nowhere.
    """
    built = {
        "/dashboard",
        "/assistant",
        "/decisions",
        "/discrepancies",
        "/farmers",
        "/impact",
        "/market",
        "/risk",
        "/today",
    }
    cards = client.get("/api/v1/fpo/dashboard", headers=_ceo(seeded)).json()["cards"]
    dangling = {c["key"]: c["href"] for c in cards if c["href"] and c["href"] not in built}
    assert not dangling, f"dashboard tiles link to routes that do not exist: {dangling}"


def test_briefing_hrefs_are_built_routes(client, seeded) -> None:
    """Same rule for the briefing: every link on it must resolve."""
    built = {
        "/dashboard",
        "/assistant",
        "/decisions",
        "/discrepancies",
        "/farmers",
        "/impact",
        "/market",
        "/risk",
        "/today",
    }
    briefing = client.get("/api/v1/briefing", headers=_ceo(seeded)).json()
    dangling = []
    for group in ("needs_decision", "closing_soon", "watch", "data_health"):
        for item in briefing.get(group) or []:
            href = item.get("href")
            if href and href.split("/")[1:2] and f"/{href.split('/')[1]}" not in built:
                dangling.append((group, href))
    assert not dangling, f"briefing items link to routes that do not exist: {dangling}"


# --------------------------------------------------------------------------- drill-down


def test_farmer_list_filters_by_tract(client, seeded) -> None:
    """The filter the risk story needs: "show me the exposed farmers" resolves to a tract."""
    all_farmers = client.get("/api/v1/fpo/farmers?limit=1", headers=_ceo(seeded)).json()
    yamuna = client.get(
        "/api/v1/fpo/farmers?tract=YAMUNA_PAR&limit=200", headers=_ceo(seeded)
    ).json()
    assert 0 < yamuna["total"] < all_farmers["total"]
    assert all(f["tract"] == "YAMUNA_PAR" for f in yamuna["farmers"])


def test_farmer_detail_carries_provenance_on_every_plot(client, seeded) -> None:
    """UI-02: a number cannot reach a screen without what says how much to trust it."""
    body = client.get(f"/api/v1/fpo/farmers/{seeded['farmer_id']}", headers=_ceo(seeded)).json()
    assert body["plots"]
    for plot in body["plots"]:
        provenance = plot["provenance"]
        assert provenance is not None, "a plot area without provenance must not render"
        assert 0.0 <= provenance["confidence"] <= 1.0
        assert provenance["source_type"]
        assert "is_stale" in provenance and "has_open_discrepancy" in provenance


def test_farmer_detail_reaches_crop_cycles_and_lot_contributions(client, seeded) -> None:
    """The bottom of the drill-down: organization aggregate down to one farmer's produce."""
    body = client.get(f"/api/v1/fpo/farmers/{seeded['farmer_id']}", headers=_ceo(seeded)).json()
    assert body["crop_cycles"]
    assert "lot_contributions" in body


def test_missing_farmer_is_404_not_500(client, seeded) -> None:
    response = client.get(f"/api/v1/fpo/farmers/{uuid.uuid4()}", headers=_ceo(seeded))
    assert response.status_code == 404


# --------------------------------------------------------------------------- boundary


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/fpo/dashboard",
        "/api/v1/fpo/farmers",
        "/api/v1/fpo/market",
        "/api/v1/fpo/discrepancies",
    ],
)
def test_farmer_is_refused_organization_wide_views(client, seeded, path) -> None:
    """INV-5. A farmer is told no, not shown a filtered version.

    A partial org view is still an org view. The boundary is meant to be a wall.
    """
    assert client.get(path, headers=_farmer(seeded)).status_code == 403


def test_farmer_may_open_their_own_record(client, seeded) -> None:
    response = client.get(f"/api/v1/fpo/farmers/{seeded['farmer_id']}", headers=_farmer(seeded))
    assert response.status_code == 200
    assert response.json()["farmer"]["id"] == str(seeded["farmer_id"])


def test_farmer_may_not_open_another_farmers_record(client, seeded) -> None:
    response = client.get(
        f"/api/v1/fpo/farmers/{seeded['other_farmer_id']}", headers=_farmer(seeded)
    )
    assert response.status_code == 403


def test_unauthenticated_and_forbidden_are_distinguished(client, seeded) -> None:
    """401 means "who are you"; 403 means "not you". They are different answers.

    Collapsing them would tell an anonymous caller they are forbidden (implying the resource
    exists for someone) and tell a signed-in farmer to log in again.
    """
    assert client.get("/api/v1/fpo/dashboard").status_code == 401
    assert client.get("/api/v1/fpo/dashboard", headers=_farmer(seeded)).status_code == 403


def test_scope_violation_returns_problem_details(client, seeded) -> None:
    """API-04: errors are machine-readable, and say what happened."""
    response = client.get("/api/v1/fpo/dashboard", headers=_farmer(seeded))
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "scope" in response.json()["type"]
