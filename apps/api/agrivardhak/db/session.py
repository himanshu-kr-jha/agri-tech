"""Database engine and session management."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from agrivardhak.config import get_settings
from agrivardhak.db.base import SEARCH_PATH_OPTION

_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
    # A pooler reaps idle server connections; recycling below that horizon turns a stale
    # socket into a new connection rather than into a request-time error.
    pool_recycle=300,
    pool_size=5,
    max_overflow=5,
    connect_args={"options": SEARCH_PATH_OPTION},
    echo=False,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope.

    Domain events are written inside the same transaction as the state change they describe
    (ADR-0007), so this boundary is also the outbox boundary — commit publishes both or
    neither.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with session_scope() as session:
        yield session
