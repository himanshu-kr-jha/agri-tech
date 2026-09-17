"""translation_memory.corpus_version: which glossary a machine row was checked against

ADR-0023 §9. A machine translation made before a glossary term existed can pass a presence
check by coincidence ("Runs the collective. Sees the whole organization" → "सामूहिक रूप से
चलता है। पूरे संगठन को…": संगठन is there, but for "organization"). Rows whose source
contains a glossary term are only served when they were produced under the current glossary.
NULL for human rows and for rows written before this column existed.

Revision ID: c5000000tmcorpus
Revises: c4000000transmem
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c5000000tmcorpus"
down_revision: str | None = "c4000000transmem"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "translation_memory", sa.Column("corpus_version", sa.String(length=16), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("translation_memory", "corpus_version")
