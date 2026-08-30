"""Retrievable text derived from external records — the Data Observer's output (ADR-0018).

``ExternalRecord`` keeps the raw payload so evidence can cite it (FR-405). It is the wrong
thing to search: one row is a 61 KB JSON document holding 75 government orders. A
``KnowledgeChunk`` is one retrievable passage from that payload, indexed for both lexical
and vector search, and pointing back at the record it came from.

Three rules shape this table.

**Hindi is canonical (ADR-0015).** ``text_hi`` is the published wording, byte-for-byte.
``text_en`` may only ever hold the *publisher's own* English — the agridarshan CMS ships
bilingual fields — and ``translation_source`` says which. We do not machine-translate on
ingest, because लघु एवं सीमांत कृषक is a legal category a fluent translation destroys
invisibly.

**There is no trust score column.** ``provenance/trust.py`` is a pure module taking
``as_of``, and decay is computed at the point of use. Storing a decayed number here would
break append-only *and* make a replay against a stored EvidenceSnapshot disagree with the
confidence it produced on the day (INV-2).

**``extracted`` is a proposal, never an authority.** A model reading a Hindi government
order and emitting structured fields cannot assert that its transcription is faithful. Under
ADR-0014 the fields stay ``UNVERIFIED`` until a named human says otherwise, and
``knowledge/gates.py`` keeps unverified text below the orchestrator's confidence floor.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from agrivardhak.db.base import (
    AppendOnlyMixin,
    Base,
    Json,
    Timestamp,
    UuidPk,
)
from agrivardhak.domain import enums

#: Dimensionality of paraphrase-multilingual-MiniLM-L12-v2. Changing the encoder means a
#: migration, not a config flag — every stored vector would otherwise be meaningless.
EMBEDDING_DIM = 384


class KnowledgeChunk(Base, AppendOnlyMixin):
    """One retrievable passage of external text, traceable to a raw payload."""

    __tablename__ = "knowledge_chunk"
    __table_args__ = (
        UniqueConstraint("external_record_id", "chunk_index", name="chunk_of_record"),
        Index("ix_knowledge_chunk_kind_noise", "kind", "is_noise"),
        Index("ix_knowledge_chunk_source", "source_key", "observed_at"),
        Index("ix_knowledge_chunk_domain", "news_domain", "observed_at"),
        # Lexical half of retrieval. Cosine similarity is soft on rare legal terms, and
        # "लघु एवं सीमांत कृषक" is precisely the kind of phrase that must match exactly or
        # not at all.
        Index(
            "ix_knowledge_chunk_search",
            "search_doc",
            postgresql_using="gin",
        ),
        # Dense half. HNSW over cosine distance; the corpus is small, so this buys ordering
        # semantics rather than speed.
        Index(
            "ix_knowledge_chunk_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[UuidPk]
    external_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("external_record.id"), nullable=False
    )
    #: Registry key from ``seed/source_registry.py``. Resolves to licence and authority,
    #: which is what the confidence gate needs and what a citation must name.
    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[enums.ExternalRecordKind] = mapped_column(
        Enum(enums.ExternalRecordKind, name="external_record_kind"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: The published wording. Canonical (ADR-0015) even when the publisher writes English.
    text_hi: Mapped[str] = mapped_column(Text, nullable=False)
    #: The publisher's own English, where they provide one. Never our translation.
    text_en: Mapped[str | None] = mapped_column(Text)
    #: "publisher" when text_en came from the source. NULL when there is no English at all.
    translation_source: Mapped[str | None] = mapped_column(String(32))

    #: Structured fields proposed from the text. UNVERIFIED until ADR-0014 is satisfied.
    extracted: Mapped[Json | None]

    is_noise: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    noise_reason: Mapped[str | None] = mapped_column(Text)
    news_domain: Mapped[enums.NewsDomain | None] = mapped_column(
        Enum(enums.NewsDomain, name="news_domain")
    )

    #: NULL when no encoder was available at observe time. Retrieval falls back to lexical
    #: search rather than failing, so the demo runs without the model on disk (NFR-303).
    embedding: Mapped[Any | None] = mapped_column(Vector(EMBEDDING_DIM))

    #: When the source published it — the government order's date, not our fetch time.
    #: This is what decays.
    observed_at: Mapped[Timestamp] = mapped_column(nullable=False)

    verification_status: Mapped[enums.VerificationStatus] = mapped_column(
        Enum(enums.VerificationStatus, name="verification_status"),
        nullable=False,
        default=enums.VerificationStatus.UNVERIFIED,
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    #: Re-observing a changed record supersedes rather than rewrites, so a packet that cited
    #: the old wording still resolves to the wording it cited.
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("knowledge_chunk.id"))

    #: Generated, not written. ``simple`` rather than a language configuration on purpose:
    #: Postgres ships no Hindi dictionary, and stemming English would fold the exact
    #: statutory wording we most need to match. ``simple`` folds case and tokenises, nothing
    #: more, which is the right behaviour for Devanagari and for legal terms alike.
    search_doc: Mapped[Any | None] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', coalesce(text_hi, '') || ' ' || coalesce(text_en, ''))",
            persisted=True,
        ),
        nullable=True,
    )
