"""JWT verification and the ContextScope dependency.

NFR-402 is the rule that matters here: the organization comes from the **verified token**,
never from a client-supplied parameter. An endpoint that accepted ``?org_id=`` as its
authorization basis would make the whole information boundary decorative.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from agrivardhak.api.scope import ContextScope, for_user
from agrivardhak.config import get_settings
from agrivardhak.domain.enums import Role

_bearer = HTTPBearer(auto_error=True)


def issue_token(
    *,
    user_id: uuid.UUID,
    roles: set[Role],
    organization_id: uuid.UUID | None,
    farmer_id: uuid.UUID | None = None,
) -> str:
    settings = get_settings()
    now = dt.datetime.now(dt.UTC)
    claims = {
        "sub": str(user_id),
        "roles": sorted(r.value for r in roles),
        "org_id": str(organization_id) if organization_id else None,
        "farmer_id": str(farmer_id) if farmer_id else None,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(seconds=settings.jwt_ttl_seconds)).timestamp()),
    }
    token: str = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token


def current_scope(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> ContextScope:
    """Resolve the caller's ContextScope from their bearer token.

    Every scoped endpoint depends on this. Nothing else may construct a ContextScope from
    request data.
    """
    settings = get_settings()
    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        roles = {Role(r) for r in claims.get("roles", [])}
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown role in token") from exc

    if not roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "token carries no roles")

    org_id = claims.get("org_id")
    farmer_id = claims.get("farmer_id")

    return for_user(
        user_id=uuid.UUID(claims["sub"]),
        roles=roles,
        organization_id=uuid.UUID(org_id) if org_id else None,
        farmer_id=uuid.UUID(farmer_id) if farmer_id else None,
    )


CurrentScope = Annotated[ContextScope, Depends(current_scope)]
