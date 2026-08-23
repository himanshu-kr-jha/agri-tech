"""Sign-in — FR-104, NFR-401, NFR-402, INV-5.

Authentication decides who sees what, so these tests are mostly about what the endpoint
*refuses* to do: leak whether an account exists, let a client choose its own role, or hand
the organization console to a member.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from agrivardhak.api import login as login_api
from agrivardhak.api.main import app
from agrivardhak.api.passwords import hash_password, verify_password
from agrivardhak.domain.models.organization import User

pytestmark = pytest.mark.usefixtures("db")

CEO = "ceo@demo.agrivardhak"
FARMER = "farmer@demo.agrivardhak"
PASSWORD = login_api.DEMO_PASSWORD


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def seeded() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from agrivardhak.config import get_settings

    db = create_engine(get_settings().database_url)
    with Session(db) as session:
        user = session.execute(select(User).where(User.email == CEO)).scalars().first()
    db.dispose()
    if user is None or not user.password_hash:
        pytest.skip("demo accounts not seeded — run `make seed-reset`")


def _login(client, username: str, password: str = PASSWORD):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


# --------------------------------------------------------------------------- hashing


def test_a_password_never_round_trips_in_the_clear() -> None:
    stored = hash_password("correct horse", iterations=1000)
    assert "correct horse" not in stored
    assert stored.startswith("pbkdf2_sha256$")


def test_the_same_password_hashes_differently_every_time() -> None:
    """Salted. Two users with the same password must not share a hash."""
    a = hash_password("same", iterations=1000)
    b = hash_password("same", iterations=1000)
    assert a != b
    assert verify_password("same", a) and verify_password("same", b)


@pytest.mark.parametrize(
    "stored",
    [None, "", "not-a-hash", "bcrypt$12$whatever", "pbkdf2_sha256$notanumber$a$b"],
)
def test_an_unusable_stored_hash_denies_rather_than_raises(stored) -> None:
    """A hash we cannot parse means nobody signs in as that user — the safe direction."""
    assert verify_password("anything", stored) is False


def test_an_empty_password_is_refused_at_hashing_time() -> None:
    with pytest.raises(ValueError):
        hash_password("")


# --------------------------------------------------------------------------- the endpoint


def test_the_ceo_can_sign_in_and_is_told_which_dashboard(client, seeded) -> None:
    body = _login(client, CEO).json()
    assert body["token"]
    assert body["user"]["audience"] == "FPO"
    assert "FPO_CEO" in body["user"]["roles"]


def test_the_farmer_can_sign_in_and_carries_their_farmer_id(client, seeded) -> None:
    body = _login(client, FARMER).json()
    assert body["user"]["audience"] == "FARMER"
    assert body["user"]["farmer_id"], "without this the farmer view cannot scope to them"
    assert body["user"]["farmer_name"]


def test_a_wrong_password_and_an_unknown_user_are_indistinguishable(client, seeded) -> None:
    """Otherwise this endpoint enumerates who has an account.

    On a platform where usernames are farmers' names, that is a privacy leak before it is a
    security one.
    """
    wrong = _login(client, CEO, "definitely-not-it")
    unknown = _login(client, "nobody@nowhere.invalid")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


def test_an_unknown_user_takes_comparable_time_to_a_wrong_password(client, seeded) -> None:
    """The password is verified even when the user is missing.

    Skipping the hash for an unknown username answers "does this account exist?" in about
    200 ms — a timing oracle that needs no special tooling to read.
    """

    def elapsed(username: str) -> float:
        start = time.perf_counter()
        _login(client, username, "wrong-password")
        return time.perf_counter() - start

    known = min(elapsed(CEO) for _ in range(3))
    unknown = min(elapsed("nobody@nowhere.invalid") for _ in range(3))
    # Generous: this asserts the hash is not skipped, not a precise constant time.
    assert unknown > known * 0.5, (
        f"unknown user answered in {unknown:.3f}s against {known:.3f}s for a known one — "
        "the password check is being skipped, which leaks account existence"
    )


def test_a_client_cannot_ask_for_a_role(client, seeded) -> None:
    """NFR-402. The client proves who it is and is told; it does not declare.

    A login that honoured a requested role would make every 403 elsewhere decorative.
    """
    body = client.post(
        "/api/v1/auth/login",
        json={
            "username": FARMER,
            "password": PASSWORD,
            "roles": ["FPO_CEO"],
            "org_id": "01a02b27-c70c-7389-935f-15ca0c072c95",
            "audience": "FPO",
        },
    ).json()
    assert body["user"]["roles"] == ["FARMER"]
    assert body["user"]["audience"] == "FARMER"


def test_missing_credentials_are_422_not_401(client) -> None:
    assert client.post("/api/v1/auth/login", json={}).status_code == 422
    assert client.post("/api/v1/auth/login", json={"username": CEO}).status_code == 422


def test_the_username_is_case_insensitive(client, seeded) -> None:
    assert _login(client, CEO.upper()).status_code == 200


# --------------------------------------------------------------------------- the boundary


ORG_PATHS = [
    "/api/v1/fpo/dashboard",
    "/api/v1/fpo/farmers",
    "/api/v1/fpo/market",
    "/api/v1/decisions",
    "/api/v1/risk-register",
    "/api/v1/audit",
    "/api/v1/briefing",
    "/api/v1/impact",
]


@pytest.mark.parametrize("path", ORG_PATHS)
def test_a_signed_in_farmer_is_still_refused_the_organization(client, seeded, path) -> None:
    """INV-5. Signing in changes who you are, not what a member may see."""
    token = _login(client, FARMER).json()["token"]
    response = client.get(path, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


@pytest.mark.parametrize("path", ORG_PATHS)
def test_the_ceo_reaches_the_organization(client, seeded, path) -> None:
    token = _login(client, CEO).json()["token"]
    assert client.get(path, headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_the_ceo_is_refused_the_farmer_view(client, seeded) -> None:
    """It inverts. Staff are not members, and /today is scoped to a farmer id they lack."""
    token = _login(client, CEO).json()["token"]
    assert (
        client.get("/api/v1/farmer/today", headers={"Authorization": f"Bearer {token}"}).status_code
        == 403
    )


def test_me_reports_the_same_identity_the_login_did(client, seeded) -> None:
    body = _login(client, FARMER).json()
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['token']}"}).json()
    assert me["audience"] == body["user"]["audience"]
    assert me["farmer_id"] == body["user"]["farmer_id"]


# --------------------------------------------------------------------------- demo accounts


def test_demo_accounts_are_offered_only_for_flagged_rows(client, seeded) -> None:
    body = client.get("/api/v1/auth/demo-accounts").json()
    usernames = {a["username"] for a in body["accounts"]}
    assert CEO in usernames and FARMER in usernames
    assert body["password"] == PASSWORD


def test_a_platform_admin_is_not_offered_as_a_demo_login(client, seeded) -> None:
    """It belongs to neither dashboard and has no farmer id, so it could only produce a 403.

    An earlier version let it fall through to `audience: FARMER` and advertised a sign-in
    that was guaranteed to fail.
    """
    accounts = client.get("/api/v1/auth/demo-accounts").json()["accounts"]
    assert not any("PLATFORM_ADMIN" in a["roles"] for a in accounts)
    assert all(a["audience"] in ("FPO", "FARMER") for a in accounts)


def test_every_offered_demo_account_actually_signs_in(client, seeded) -> None:
    """The list on the sign-in page must not advertise a credential that does not work."""
    for account in client.get("/api/v1/auth/demo-accounts").json()["accounts"]:
        response = _login(client, account["username"], account["password"])
        assert response.status_code == 200, account["username"]
        assert response.json()["user"]["audience"] == account["audience"]


def test_demo_accounts_are_hidden_outside_a_local_environment(client, seeded, monkeypatch) -> None:
    """A production deployment must not publish credentials, flagged or not."""
    from agrivardhak.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "environment", "production")
    try:
        assert client.get("/api/v1/auth/demo-accounts").status_code == 404
    finally:
        monkeypatch.setattr(settings, "environment", "local")
