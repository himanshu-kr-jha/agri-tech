"""FastAPI application.

The web tier never touches the database (ADR-0001): every read and write comes through here
so that authorization, provenance resolution and the information boundary have exactly one
enforcement point.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from agrivardhak.api import assistant, chat, dashboard, knowledge, login, translate
from agrivardhak.api.auth import CurrentScope
from agrivardhak.api.scope import ScopeViolation
from agrivardhak.config import get_settings
from agrivardhak.db.session import get_session

settings = get_settings()

app = FastAPI(
    title="AgriVardhak API",
    version="0.1.0",
    description=(
        "AI decision & orchestration platform for farmer collectives. "
        "Every consequential value carries provenance; every recommendation is "
        "human-approved before execution."
    ),
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ScopeViolation)
async def _scope_violation_handler(_: Request, exc: ScopeViolation) -> JSONResponse:
    """RFC 9457 problem details (API-04).

    A scope violation is 403, not 404: the caller is authenticated and we are telling them
    their scope does not cover this, without saying whether the row exists.
    """
    return JSONResponse(
        status_code=403,
        content={
            "type": "https://agrivardhak.dev/problems/scope-violation",
            "title": "Outside your access scope",
            "status": 403,
            "detail": str(exc),
        },
        media_type="application/problem+json",
    )


SessionDep = Annotated[Session, Depends(get_session)]

v1 = APIRouter(prefix="/api/v1")


@v1.get("/ping", tags=["meta"])
def ping() -> dict[str, str]:
    """Liveness only: no database, no settings work, no I/O.

    This is the endpoint an uptime monitor or keep-alive cron should hit on an interval.
    It answers exactly one question - is the process accepting requests - so it stays cheap
    enough to call every minute forever. Use /health when you need to know whether the
    process can actually serve traffic.
    """
    return {"status": "ok"}


@v1.get("/health", tags=["meta"])
def health(session: SessionDep) -> dict[str, Any]:
    """Liveness plus the things the demo actually depends on."""
    checks: dict[str, str] = {}
    try:
        session.execute(text("select 1"))
        checks["database"] = "ok"
    except Exception as exc:  # pragma: no cover - surfaced in the response
        checks["database"] = f"error: {exc}"

    for ext in ("postgis", "vector"):
        try:
            version = session.execute(
                text("select extversion from pg_extension where extname = :n"), {"n": ext}
            ).scalar_one_or_none()
            checks[ext] = version or "missing"
        except Exception as exc:  # pragma: no cover
            checks[ext] = f"error: {exc}"

    healthy = all(not v.startswith("error") and v != "missing" for v in checks.values())
    return {
        "status": "ok" if healthy else "degraded",
        "environment": settings.environment,
        "use_fixtures": settings.use_fixtures,
        "checks": checks,
    }


@v1.get("/me", tags=["meta"])
def me(scope: CurrentScope) -> dict[str, Any]:
    """Echo the resolved scope. Useful for verifying the boundary during development."""
    return {
        "user_id": str(scope.actor_user_id),
        "roles": sorted(r.value for r in scope.roles),
        "organization_id": str(scope.organization_id) if scope.organization_id else None,
        "farmer_id": str(scope.farmer_id) if scope.farmer_id else None,
        "audience": scope.audience,
        "visible_scopes": sorted(s.value for s in scope.visible_scopes()),
    }


app.include_router(v1)
app.include_router(dashboard.router)
app.include_router(assistant.router)
app.include_router(chat.router)
app.include_router(knowledge.router)
app.include_router(login.router)
app.include_router(translate.router)
