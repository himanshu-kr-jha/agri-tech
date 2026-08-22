"""append-only guards on immutable tables

DR-04 and INV-2: Observation, Prediction, EvidenceSnapshot, Approval, Intervention,
Outcome, Attribution and AuditRecord are append-only. Correction is a new row plus
supersession — never an UPDATE, never a DELETE.

Enforced with triggers rather than GRANTs because the application may connect as the table
owner, and an owner bypasses column privileges. A trigger holds for every role including
superuser, and it fails loudly with a message that names the invariant.

A small allowlist of columns stays mutable, because some append-only rows legitimately gain
information later without their claim changing:

  * ``observation.superseded_by`` / verification fields — a later observation supersedes an
    earlier one, and a human verifies a claim, but the claimed value never changes.
  * ``prediction.actual_value`` / ``error`` — realized outcomes are written once (FR-702).
  * ``domain_event.published_at`` — the outbox dispatcher marks a row as fanned out.
  * ``consent.revoked_at`` — revocation is recorded on the grant row (FR-1102).

Revision ID: b9000000guard
Revises: b8effdc6a2cb
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b9000000guard"
down_revision: str | None = "b8effdc6a2cb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# table -> columns that may still change after insert
APPEND_ONLY: dict[str, list[str]] = {
    "observation": ["superseded_by", "verification_status", "verified_by", "verified_at"],
    "prediction": ["actual_value", "actual_recorded_at", "error"],
    "evidence_snapshot": [],
    "approval": [],
    "intervention": [],
    "outcome": [],
    "attribution": [],
    "audit_record": [],
    "external_record": [],
    "eligibility_assessment": [],
    "buyer_match": [],
    "funding_requirement": [],
    "demand_signal": [],
    "news_event": [],
    "llm_call_log": [],
    "domain_event": ["published_at"],
    "consent": ["revoked_at"],
}

GUARD_FN = """
CREATE OR REPLACE FUNCTION agrivardhak_append_only_guard()
RETURNS trigger AS $$
DECLARE
    allowed text[] := TG_ARGV;
    col     text;
    old_val text;
    new_val text;
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'append-only violation: % is append-only (DR-04); rows may not be deleted',
            TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
    END IF;

    FOR col IN
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = TG_TABLE_SCHEMA AND table_name = TG_TABLE_NAME
    LOOP
        IF col = ANY(allowed) THEN
            CONTINUE;
        END IF;
        EXECUTE format('SELECT ($1).%I::text', col) INTO old_val USING OLD;
        EXECUTE format('SELECT ($1).%I::text', col) INTO new_val USING NEW;
        IF old_val IS DISTINCT FROM new_val THEN
            RAISE EXCEPTION
                'append-only violation: %.% may not be updated (DR-04); '
                'write a new row and supersede the old one instead',
                TG_TABLE_NAME, col
                USING ERRCODE = 'restrict_violation';
        END IF;
    END LOOP;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(GUARD_FN)
    for table, mutable in APPEND_ONLY.items():
        args = ", ".join(f"'{c}'" for c in mutable)
        op.execute(
            f"""
            CREATE TRIGGER {table}_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION agrivardhak_append_only_guard({args});
            """
        )


def downgrade() -> None:
    for table in APPEND_ONLY:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table};")
    op.execute("DROP FUNCTION IF EXISTS agrivardhak_append_only_guard();")
