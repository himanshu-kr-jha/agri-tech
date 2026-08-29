"""extensions and uuid_generate_v7

The schema's prerequisites, as a migration rather than as a side effect of the local Docker
image. Every table in b8effdc6a2cb carries ``server_default=text("uuid_generate_v7()")``, and
plot boundaries are PostGIS geography columns — so before this revision existed, ``alembic
upgrade head`` against any database that had not run ``infra/initdb/01-extensions.sql`` failed
on the first CREATE TABLE. That is every managed Postgres, Supabase included.

Two portability decisions are load-bearing:

**Extensions go into an ``extensions`` schema.** That is where Supabase puts them, and the
schema is created here so the same statement works on a bare Docker database. ``IF NOT
EXISTS`` means an extension already installed in ``public`` by the initdb script is left
exactly where it is — this migration never relocates one. Both locations are covered by the
``search_path`` set in ``db/session.py`` and ``alembic/env.py``.

**The function pins its own search path.** ``uuid_generate_v7`` calls ``gen_random_bytes``,
which pgcrypto provides — from ``extensions`` on Supabase, possibly from ``public`` on a
Docker database created before this revision. Naming it unqualified under a function-level
``SET search_path`` resolves it in either place; qualifying it either way would break the
other.

Revision ID: a0000000boot
Revises:
Create Date: 2026-08-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a0000000boot"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Body copied verbatim from infra/initdb/01-extensions.sql, with the function-level
# search_path added. Postgres 18 ships uuidv7() natively; drop this when the managed
# database reaches 18 (ADR-0009).
UUID_V7 = """
CREATE OR REPLACE FUNCTION public.uuid_generate_v7()
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SET search_path = public, extensions
AS $$
DECLARE
    unix_ts_ms bytea;
    uuid_bytes bytea;
BEGIN
    unix_ts_ms := substring(int8send((extract(epoch FROM clock_timestamp()) * 1000)::bigint)
                            FROM 3);
    -- 10 random bytes for the rand_a / rand_b fields
    uuid_bytes := unix_ts_ms || gen_random_bytes(10);
    -- version 7: high nibble of byte 6
    uuid_bytes := set_byte(uuid_bytes, 6, (b'0111' || get_byte(uuid_bytes, 6)::bit(4))::bit(8)::int);
    -- variant 10xx: top two bits of byte 8
    uuid_bytes := set_byte(uuid_bytes, 8, (b'10'   || get_byte(uuid_bytes, 8)::bit(6))::bit(8)::int);
    RETURN encode(uuid_bytes, 'hex')::uuid;
END
$$;
"""


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS extensions")
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA extensions")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions")
    op.execute(UUID_V7)


def downgrade() -> None:
    # The function only. Dropping PostGIS out from under a database that has geography
    # columns is not a reversal anyone wants automated, and the extensions are harmless
    # when unused.
    op.execute("DROP FUNCTION IF EXISTS public.uuid_generate_v7()")
