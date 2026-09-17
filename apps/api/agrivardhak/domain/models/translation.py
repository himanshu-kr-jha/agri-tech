"""The bilingual corpus: every interface translation we have ever made or been given (ADR-0023).

One row is one normalised source text in one direction. The web tier's page translator asks
for a batch of strings; the rows here are what makes the second request for the same string
free, and what makes the corpus grow as people use the product rather than being written in
advance.

Two origins, and the difference is the point of the table. ``HUMAN`` rows are hand-written
(seeded from the static dictionary in ``apps/web/src/lib/i18n.ts``) and are never overwritten
by a machine. ``MACHINE`` rows came from Sarvam and may be refreshed.

This is **not** where the text of a government order lives. ``KnowledgeChunk.text_hi`` stays
the canonical published wording (ADR-0015); a row here is only ever a *display* rendering of
whatever was on screen, and nothing downstream may read a rule from it.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from agrivardhak.db.base import Base, TimestampMixin, UuidPk

ORIGIN_HUMAN = "HUMAN"
ORIGIN_MACHINE = "MACHINE"


class TranslationMemory(TimestampMixin, Base):
    __tablename__ = "translation_memory"
    __table_args__ = (
        UniqueConstraint("source_lang", "target_lang", "source_hash"),
        CheckConstraint("origin in ('HUMAN', 'MACHINE')", name="origin"),
        CheckConstraint("source_lang <> target_lang", name="direction"),
    )

    id: Mapped[UuidPk]
    #: BCP-47 as Sarvam spells it: ``en-IN`` | ``hi-IN``.
    source_lang: Mapped[str] = mapped_column(String(8), nullable=False)
    target_lang: Mapped[str] = mapped_column(String(8), nullable=False)
    #: SHA-256 hex of the *normalised* source text — see ``translation.service.normalise``.
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    translated_text: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    #: ``sarvam`` for machine rows, ``i18n.ts`` for the seeded human ones.
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Glossary version a MACHINE row was produced under (``translation.glossary``). A row whose
    #: source contains a glossary term is served only under that same version. NULL for HUMAN.
    corpus_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
