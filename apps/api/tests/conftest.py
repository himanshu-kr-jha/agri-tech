"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text

from agrivardhak.config import get_settings


@pytest.fixture(scope="session")
def db() -> Iterator[Engine]:
    """Engine against the local database.

    Skips rather than fails when Postgres is not up, so ``pytest`` stays useful for the
    pure-function tests (contracts, scope, units) without Docker running.
    """
    engine = create_engine(get_settings().database_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"database unavailable: {exc}")
    yield engine
    engine.dispose()
