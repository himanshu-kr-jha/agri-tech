"""Alembic environment.

Importing ``agrivardhak.domain.models`` is what puts every table on ``Base.metadata`` —
a model not imported there is invisible to autogenerate.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from agrivardhak.config import get_settings
from agrivardhak.db.base import Base, SEARCH_PATH_OPTION
from agrivardhak.domain import models  # noqa: F401  — registers all tables

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata

# PostGIS and pgvector create their own tables and types; autogenerate must not try to
# manage them or every migration will contain spurious drops.
EXCLUDED_TABLES = {"spatial_ref_sys", "geography_columns", "geometry_columns"}


def include_object(obj, name, type_, reflected, compare_to):  # noqa: ANN001, ANN201
    if type_ == "table" and name in EXCLUDED_TABLES:
        return False
    # GeoAlchemy2 creates spatial indexes itself via a DDL listener on table creation.
    # Autogenerate also sees them, so without this the migration emits a duplicate
    # CREATE INDEX and fails. GeoAlchemy2 marks the ones it manages with ``_column_flag``.
    if type_ == "index" and getattr(obj, "_column_flag", False):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        # The same search path the runtime engine uses, supplied here because
        # engine_from_config does not inherit db/session.py's connect_args. Without it the
        # geography columns in b8effdc6a2cb cannot resolve wherever PostGIS lives outside
        # public — which is every Supabase database. It must be a connection *option* and
        # not a ``SET`` statement; SEARCH_PATH_OPTION documents why.
        connect_args={"options": SEARCH_PATH_OPTION},
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
