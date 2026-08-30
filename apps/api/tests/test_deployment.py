"""What has to stay true for the hosted pilot (ADR-0019).

None of these need a database. They guard three things that break silently — the kind of
break that builds clean, starts clean, passes a health check, and fails on a real request:

  * the migration chain is self-sufficient, so ``alembic upgrade head`` is enough on an empty
    managed Postgres that will never run ``infra/initdb/01-extensions.sql``;
  * the runtime engine and Alembic agree on one ``search_path``, because a divergence
    reproduces exactly the Supabase failure the constant exists to prevent;
  * the API image still ships ``seed/generated/``, which the ingestion adapters read at
    runtime rather than at build time.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from agrivardhak.db.base import SEARCH_PATH_OPTION

ROOT = pathlib.Path(__file__).resolve().parents[3]
VERSIONS = ROOT / "apps" / "api" / "alembic" / "versions"


def _revisions() -> dict[str, str | None]:
    """{revision: down_revision} parsed from the migration files, without importing them."""
    chain: dict[str, str | None] = {}
    for path in VERSIONS.glob("*.py"):
        text = path.read_text()
        rev = re.search(r"^revision: str = ['\"]([^'\"]+)['\"]", text, re.M)
        down = re.search(r"^down_revision: str \| None = (?:['\"]([^'\"]+)['\"]|None)", text, re.M)
        assert rev and down, f"{path.name} declares no revision/down_revision"
        chain[rev.group(1)] = down.group(1)
    return chain


def test_the_chain_has_one_base_and_it_creates_the_extensions() -> None:
    chain = _revisions()
    bases = [rev for rev, down in chain.items() if down is None]
    assert bases == ["a0000000boot"], f"expected one base revision, found {bases}"

    body = (VERSIONS / "a0000000boot_extensions_and_uuidv7.py").read_text()
    for statement in (
        "CREATE SCHEMA IF NOT EXISTS extensions",
        "CREATE EXTENSION IF NOT EXISTS postgis",
        "CREATE EXTENSION IF NOT EXISTS pgcrypto",
        "CREATE EXTENSION IF NOT EXISTS vector",
    ):
        assert statement in body, f"the base revision no longer runs: {statement}"
    # gen_random_bytes lives in a different schema on Supabase than on an older Docker
    # database, so the function has to pin its own search path rather than qualify the call.
    assert "SET search_path = public, extensions" in body


def test_the_chain_is_linear_and_ends_in_one_head() -> None:
    chain = _revisions()
    heads = set(chain) - {down for down in chain.values() if down}
    assert len(heads) == 1, f"branched migration chain, heads: {sorted(heads)}"
    for rev, down in chain.items():
        assert down is None or down in chain, f"{rev} revises {down}, which does not exist"


@pytest.mark.parametrize("rel", ["apps/api/agrivardhak/db/session.py", "apps/api/alembic/env.py"])
def test_alembic_and_the_runtime_engine_share_one_search_path(rel: str) -> None:
    source = (ROOT / rel).read_text()
    assert "SEARCH_PATH_OPTION" in source, f"{rel} no longer uses the shared constant"
    # A literal here would be a second source of truth; a divergence between the two is the
    # Supabase failure this constant prevents.
    assert "-csearch_path" not in source.replace(SEARCH_PATH_OPTION, ""), (
        f"{rel} hardcodes a search_path instead of importing SEARCH_PATH_OPTION"
    )
    # It must reach the driver as a connection option. Executed as a statement after connect,
    # it opens a transaction that Alembic then nests inside — six revisions "applied", exit 0,
    # zero tables created. See SEARCH_PATH_OPTION in db/base.py.
    assert "connect_args" in source


def test_the_search_path_covers_both_extension_locations() -> None:
    assert SEARCH_PATH_OPTION == "-csearch_path=public,extensions"


def test_the_api_image_ships_the_runtime_fixtures() -> None:
    """``ingestion`` resolves fixtures as ``parents[4]`` at runtime, not at build time."""
    ignored = [
        line.strip()
        for line in (ROOT / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    for pattern in ignored:
        assert not pattern.rstrip("/").startswith("seed"), (
            f".dockerignore excludes {pattern!r}; the image would build clean and fail on "
            "the first weather or market question"
        )
    assert (ROOT / "seed" / "generated").is_dir()

    dockerfile = (ROOT / "Dockerfile").read_text()
    # Build context is the repo root — an apps/api-only image cannot satisfy parents[4].
    assert "COPY . ." in dockerfile
    assert "uv pip install --system -e apps/api" in dockerfile
