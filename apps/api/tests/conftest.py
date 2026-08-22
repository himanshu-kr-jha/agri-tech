"""Shared test fixtures."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from agrivardhak.config import get_settings
from agrivardhak.domain.models.organization import User


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


@pytest.fixture
def session(db: Engine) -> Iterator[Session]:
    """A session whose writes are rolled back at the end of the test.

    Every test runs inside an outer transaction that is never committed, so tests share one
    database without seeing each other's rows. This matters more than usual here: the
    append-only triggers mean a test cannot tidy up after itself with DELETE.
    """
    connection = db.connect()
    transaction = connection.begin()
    sess = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield sess
    finally:
        sess.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def staff_user(session: Session) -> User:
    """A persisted user, for anything that records who acted.

    `verified_by`, `resolved_by` and the approval chain are real foreign keys — an audit
    trail pointing at a user id that does not exist would not be an audit trail.
    """
    user = User(display_name="Test Field Officer", email=f"officer-{uuid.uuid4().hex[:8]}@test")
    session.add(user)
    session.flush()
    return user
