"""POST /api/v1/translate — the page translator's one call (ADR-0023, UI-11).

Thin, like the other routers: everything behind ``translation.service.translate``.

Authentication is optional and decides one thing only: how many Sarvam calls the request may
spend on strings the translation memory has never seen. Signed in, no cap. Anonymous (the
sign-in page), a small budget shared by every anonymous caller per hour — enough for the
sign-in page to be translated once, after which it is served from memory, and not enough for
a script to turn a public endpoint into someone else's translation service (NFR-304). An
invalid token is treated as anonymous rather than refused; a translation request is never
the place to surface an expired session.
"""

from __future__ import annotations

import threading
import time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agrivardhak.api.auth import current_scope
from agrivardhak.config import get_settings
from agrivardhak.db.session import get_session
from agrivardhak.translation import glossary
from agrivardhak.translation.service import translate as translate_texts

router = APIRouter(prefix="/api/v1", tags=["translation"])

SessionDep = Annotated[Session, Depends(get_session)]

_optional_bearer = HTTPBearer(auto_error=False)


class TranslateRequest(BaseModel):
    target: Literal["hi-IN", "en-IN"]
    texts: list[str] = Field(min_length=1)


class TranslateResponse(BaseModel):
    target: str
    #: Same length and order as ``texts``. A string that could not be translated comes
    #: back as its (whitespace-normalised) source.
    translations: list[str]
    #: Per text: False when it came back untranslated because it could not be translated,
    #: as opposed to needing no translation. The page translator retries only these.
    resolved: list[bool]
    #: Version of the glossary these translations were checked against. The browser clears
    #: its cache when this changes, so an edited term never shows its old rendering.
    corpus_version: str


class _SharedBudget:
    """A fixed hourly allowance of machine translations, per API process.

    In memory on purpose: it is a spend cap, not an accounting record, and a restart that
    resets it costs at most one more hour's allowance.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._window_start = time.monotonic()
        self._used = 0

    def take(self, wanted: int, per_hour: int) -> int:
        with self._lock:
            now = time.monotonic()
            if now - self._window_start >= 3600:
                self._window_start, self._used = now, 0
            granted = max(0, min(wanted, per_hour - self._used))
            self._used += granted
            return granted

    def refund(self, unused: int) -> None:
        with self._lock:
            self._used = max(0, self._used - unused)


anonymous_budget = _SharedBudget()


def _signed_in(credentials: HTTPAuthorizationCredentials | None) -> bool:
    if credentials is None:
        return False
    try:
        current_scope(credentials)
    except HTTPException:
        return False
    return True


@router.get("/translate/version")
def corpus_version() -> dict[str, str]:
    """The glossary version, for a browser whose page was served entirely from its cache and
    so never saw a translate response. Cheap and unauthenticated: it reveals a hash."""
    return {"corpus_version": glossary.load().version}


@router.post("/translate", response_model=TranslateResponse)
def translate(
    body: TranslateRequest,
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_optional_bearer)],
) -> TranslateResponse:
    settings = get_settings()
    if len(body.texts) > settings.translate_max_texts_per_request:
        raise HTTPException(
            status_code=413,
            detail=f"at most {settings.translate_max_texts_per_request} texts per request",
        )
    if sum(len(t) for t in body.texts) > settings.translate_max_chars_per_request:
        raise HTTPException(
            status_code=413,
            detail=f"at most {settings.translate_max_chars_per_request} characters per request",
        )

    if _signed_in(credentials):
        result = translate_texts(session, body.texts, body.target, machine_budget=None)
    else:
        granted = anonymous_budget.take(
            len(body.texts), settings.translate_anonymous_budget_per_hour
        )
        result = translate_texts(session, body.texts, body.target, machine_budget=granted)
        anonymous_budget.refund(granted - result.machine_calls)
    return TranslateResponse(
        target=body.target,
        translations=result.translations,
        resolved=result.resolved,
        corpus_version=glossary.load().version,
    )
