"""knowledge_chunk: retrievable text derived from external records

DR-07 — "Scheme and news text is embedded with pgvector for retrieval; the raw text is
retained." The extension has been created at initdb since the first commit and until now
nothing used it.

Hand-finished after autogenerate, for three reasons autogenerate gets wrong:

* it emits ``sa.Enum(...)`` for ``external_record_kind``, ``news_domain`` and
  ``verification_status``, which would try to ``CREATE TYPE`` types the initial schema
  already created. They are declared here with ``create_type=False``.
* it does not know how to write the pgvector import, and renders a bare
  ``pgvector.sqlalchemy.vector.VECTOR`` reference that fails at import time.
* it skips both retrieval indexes — the GIN index over the generated tsvector and the HNSW
  index over the embedding — because ``env.py`` deliberately excludes extension-managed
  index objects.

Revision ID: c2000000knowchunk
Revises: c1000000extkinds
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "c2000000knowchunk"
down_revision: str | None = "c1000000extkinds"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 384

# Types the initial schema already created. Referenced, never redefined.
external_record_kind = postgresql.ENUM(name="external_record_kind", create_type=False)
news_domain = postgresql.ENUM(name="news_domain", create_type=False)
verification_status = postgresql.ENUM(name="verification_status", create_type=False)


def upgrade() -> None:
    op.create_table(
        "knowledge_chunk",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("uuid_generate_v7()"), nullable=False
        ),
        sa.Column("external_record_id", sa.UUID(), nullable=False),
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column("kind", external_record_kind, nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text_hi", sa.Text(), nullable=False),
        sa.Column("text_en", sa.Text(), nullable=True),
        sa.Column("translation_source", sa.String(length=32), nullable=True),
        sa.Column("extracted", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_noise", sa.Boolean(), nullable=False),
        sa.Column("noise_reason", sa.Text(), nullable=True),
        sa.Column("news_domain", news_domain, nullable=True),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verification_status", verification_status, nullable=False),
        sa.Column("verified_by", sa.UUID(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by", sa.UUID(), nullable=True),
        sa.Column(
            "search_doc",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple', coalesce(text_hi, '') || ' ' || coalesce(text_en, ''))",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["external_record_id"], ["external_record.id"],
            name=op.f("fk_knowledge_chunk_external_record_id_external_record"),
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by"], ["knowledge_chunk.id"],
            name=op.f("fk_knowledge_chunk_superseded_by_knowledge_chunk"),
        ),
        sa.ForeignKeyConstraint(
            ["verified_by"], ["app_user.id"],
            name=op.f("fk_knowledge_chunk_verified_by_app_user"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_chunk")),
        sa.UniqueConstraint("external_record_id", "chunk_index", name="chunk_of_record"),
    )
    op.create_index(
        "ix_knowledge_chunk_domain", "knowledge_chunk", ["news_domain", "observed_at"]
    )
    op.create_index(
        "ix_knowledge_chunk_kind_noise", "knowledge_chunk", ["kind", "is_noise"]
    )
    op.create_index(
        "ix_knowledge_chunk_source", "knowledge_chunk", ["source_key", "observed_at"]
    )
    op.create_index(
        "ix_knowledge_chunk_search", "knowledge_chunk", ["search_doc"], postgresql_using="gin"
    )
    op.create_index(
        "ix_knowledge_chunk_embedding",
        "knowledge_chunk",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunk_embedding", table_name="knowledge_chunk")
    op.drop_index("ix_knowledge_chunk_search", table_name="knowledge_chunk")
    op.drop_index("ix_knowledge_chunk_source", table_name="knowledge_chunk")
    op.drop_index("ix_knowledge_chunk_kind_noise", table_name="knowledge_chunk")
    op.drop_index("ix_knowledge_chunk_domain", table_name="knowledge_chunk")
    op.drop_table("knowledge_chunk")
