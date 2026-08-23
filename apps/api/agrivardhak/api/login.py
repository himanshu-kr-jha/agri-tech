"""Sign-in — FR-104, NFR-401.

A username and a password become the same JWT the rest of the API already verifies, so
nothing downstream changes: the token still carries the roles, the organization and (for a
farmer) the farmer id, and every endpoint still resolves its ContextScope from the verified
token rather than from anything the client sent (NFR-402).

**The role is decided here, from role grants in the database.** The client does not say who
it is; it proves who it is and is told. That distinction is the whole reason the information
boundary holds — a login that accepted a requested role would make every `403` elsewhere
decorative.

Demo accounts
-------------
The seed creates accounts so the demo has something to sign in with. They are marked
``is_demo_account`` in the database, the login response says so, and they exist only because
this system is presented before it is deployed. :data:`DEMO_PASSWORD` is in the repository on
purpose — a credential that is documented, fixed and flagged is safer than one that looks
like a secret while being equally guessable.

Before this is deployed anywhere real, `make seed` must not run against that database.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agrivardhak.api.auth import CurrentScope, issue_token
from agrivardhak.api.passwords import dummy_verify, verify_password
from agrivardhak.config import get_settings
from agrivardhak.db.session import get_session
from agrivardhak.domain import enums
from agrivardhak.domain.models.operations import AuditRecord
from agrivardhak.domain.models.organization import Farmer, RoleGrant, User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

SessionDep = Annotated[Session, Depends(get_session)]

#: The password every seeded demo account shares. See the module docstring.
DEMO_PASSWORD = "agrivardhak"

#: Roles that get the organization console.
STAFF_ROLES = frozenset(
    {
        enums.Role.FPO_CEO,
        enums.Role.FIELD_OFFICER,
        enums.Role.MARKET_OFFICER,
        enums.Role.FINANCE_OFFICER,
    }
)

#: Roles that belong to neither dashboard and are not offered as a demo sign-in.
#:
#: A platform administrator operates the software; they are not a member of the collective
#: and have no farmer id, so the farmer view would refuse them and the FPO console would be
#: an overreach — they are already barred from approving an organization's decisions
#: (see orchestrator.lifecycle.assert_may_approve). An earlier version of this endpoint let
#: them fall through to ``audience: FARMER``, which offered a demo login that could only
#: ever produce a 403.
NON_DASHBOARD_ROLES = frozenset({enums.Role.PLATFORM_ADMIN, enums.Role.RESEARCHER})


@router.post("/login")
def login(session: SessionDep, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Exchange a username and password for a bearer token.

    The failure response is deliberately uniform: an unknown username, a wrong password and
    a deactivated account all return the same 401 with the same message. Distinguishing them
    would turn this endpoint into a way to enumerate who has an account — and on a platform
    where the usernames are farmers' names, that is a privacy leak before it is a security
    one.
    """
    username = str(body.get("username", "")).strip().lower()
    password = str(body.get("password", ""))
    if not username or not password:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "username and password required")

    user = session.execute(select(User).where(func.lower(User.email) == username)).scalars().first()
    # The same hashing work happens whether or not the username resolved, so a bad username
    # and a bad password take the same time. Without this the endpoint answers "does this
    # account exist?" by responding four times faster — see passwords._DUMMY_HASH.
    ok = verify_password(password, user.password_hash) if user else dummy_verify(password)

    if user is None or not ok or not user.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Wrong username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    grants = list(session.execute(select(RoleGrant).where(RoleGrant.user_id == user.id)).scalars())
    if not grants:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This account has no roles. An administrator has to grant one before you can sign in.",
        )

    roles = {g.role for g in grants}
    organization_id = next((g.organization_id for g in grants if g.organization_id), None)

    token = issue_token(
        user_id=user.id,
        roles=roles,
        organization_id=organization_id,
        farmer_id=user.farmer_id,
    )

    session.add(
        AuditRecord(
            organization_id=organization_id,
            actor_id=user.id,
            actor_kind=enums.ActorKind.HUMAN,
            action="sign_in",
            subject_type="app_user",
            subject_id=user.id,
            authority=sorted(r.value for r in roles)[0],
            occurred_at=dt.datetime.now(dt.UTC),
            detail={"demo_account": user.is_demo_account},
        )
    )
    session.commit()

    return {
        "token": token,
        "expires_in": get_settings().jwt_ttl_seconds,
        "user": _profile(session, user, roles, organization_id),
    }


@router.get("/me")
def me(session: SessionDep, scope: CurrentScope) -> dict[str, Any]:
    """Who the bearer token says you are. Used by the web tier to route and to render a name."""
    user = session.get(User, scope.actor_user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no such user")
    return _profile(session, user, set(scope.roles), scope.organization_id)


@router.get("/demo-accounts")
def demo_accounts(session: SessionDep) -> dict[str, Any]:
    """List the seeded demo logins, so the sign-in page can offer them.

    Only ever returns accounts flagged ``is_demo_account``, and only outside production. A
    real deployment either has no such rows or is not running in an environment where this
    responds at all.
    """
    settings = get_settings()
    if settings.environment not in ("local", "demo", "test"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not available")

    rows = list(
        session.execute(
            select(User).where(User.is_demo_account.is_(True), User.is_active.is_(True))
        ).scalars()
    )
    accounts = []
    for user in rows:
        grants = list(
            session.execute(select(RoleGrant).where(RoleGrant.user_id == user.id)).scalars()
        )
        roles = {g.role for g in grants}
        if not roles or roles & NON_DASHBOARD_ROLES:
            continue
        accounts.append(
            {
                "username": user.email,
                "password": DEMO_PASSWORD,
                "display_name": user.display_name,
                "roles": sorted(r.value for r in roles),
                "audience": audience_for(roles),
                "description": _describe(roles),
            }
        )
    accounts.sort(key=lambda a: (a["audience"] != "FPO", a["display_name"]))
    return {"accounts": accounts, "password": DEMO_PASSWORD}


def audience_for(roles: set[enums.Role]) -> str:
    """Which dashboard this set of roles belongs to.

    Decided on the server and returned to the client, so "which view do I get" has exactly
    one implementation. A web tier that re-derived it from the role list would eventually
    disagree with the API about who a person is, and the disagreement would be a leak.
    """
    if roles & STAFF_ROLES:
        return "FPO"
    if enums.Role.FARMER in roles:
        return "FARMER"
    return "NONE"


def _describe(roles: set[enums.Role]) -> str:
    if enums.Role.FPO_CEO in roles:
        return (
            "Runs the collective. Sees the whole organization: the assistant, every member, "
            "buyer negotiations, the risk register and the decision history — and is the only "
            "one who can approve a crop plan."
        )
    if enums.Role.FIELD_OFFICER in roles:
        return (
            "Works the field. Sees members and crop health, and can approve crop-protection "
            "actions — but not a funding allocation."
        )
    if enums.Role.FARMER in roles:
        return (
            "A member of the collective. Sees their own farm and nothing else — not the "
            "member list, not the buyer negotiations, not the organization's decisions."
        )
    return "Signed-in user."


def _profile(
    session: Session, user: User, roles: set[enums.Role], organization_id: Any
) -> dict[str, Any]:
    farmer = session.get(Farmer, user.farmer_id) if user.farmer_id else None
    return {
        "id": str(user.id),
        "display_name": user.display_name,
        "email": user.email,
        "locale": user.locale,
        "roles": sorted(r.value for r in roles),
        # The web tier routes on this rather than re-deriving it from the role list, so
        # "which dashboard" is decided in one place on the server.
        "audience": audience_for(roles),
        "organization_id": str(organization_id) if organization_id else None,
        "farmer_id": str(user.farmer_id) if user.farmer_id else None,
        "farmer_name": farmer.full_name if farmer else None,
        "is_demo_account": user.is_demo_account,
    }
