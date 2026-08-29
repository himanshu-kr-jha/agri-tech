"""append-only guard on knowledge_chunk

DR-04. A chunk is a record of what a source said, so re-observing changed text must write a
new row and supersede the old one — otherwise a DecisionPacket that cited a chunk last week
would silently resolve to different wording today, and INV-2 would be a claim rather than a
property.

Five columns stay mutable, and each earns it:

* ``verification_status`` / ``verified_by`` / ``verified_at`` — ADR-0014's named verifier.
  A human confirming a transcription does not change what the source said.
* ``superseded_by`` — set when a later chunk replaces this one, exactly as on ``observation``.
* ``embedding`` — the vector is a derived index over ``text_hi``, not a claim. The encoder is
  an optional local model (NFR-303), so a chunk may be written with a NULL embedding and
  filled in after ``make embed-model``. Re-encoding must not require rewriting history.
* ``search_doc`` — **required for the guard to work at all on this table**, and the reason is
  not obvious. It is a ``GENERATED ALWAYS`` column, and Postgres computes generated columns
  *after* BEFORE-row triggers run, so inside the guard ``NEW.search_doc`` is always NULL
  while ``OLD.search_doc`` holds the stored tsvector. Every UPDATE therefore looks like an
  attempt to blank it, and the first embedding backfill failed with
  "knowledge_chunk.search_doc may not be updated". Allowlisting it weakens nothing: a
  generated column cannot be written directly — Postgres rejects the attempt itself — and
  its value is a pure function of ``text_hi``, which stays guarded.

  ``knowledge_chunk`` is the first table here with a generated column, which is why
  ``b9000000append_only_guards.py`` never had to account for this.

Revision ID: c3000000chunkguard
Revises: c2000000knowchunk
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c3000000chunkguard"
down_revision: str | None = "c2000000knowchunk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "knowledge_chunk"
MUTABLE = [
    "verification_status",
    "verified_by",
    "verified_at",
    "superseded_by",
    "embedding",
    "search_doc",
]


def upgrade() -> None:
    args = ", ".join(f"'{c}'" for c in MUTABLE)
    op.execute(
        f"""
        CREATE TRIGGER {TABLE}_append_only
        BEFORE UPDATE OR DELETE ON {TABLE}
        FOR EACH ROW EXECUTE FUNCTION agrivardhak_append_only_guard({args});
        """
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_append_only ON {TABLE};")
