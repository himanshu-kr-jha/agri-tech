"""Proposing structured scheme fields from Hindi order text (ADR-0014, ADR-0015).

This is the one step in the observer where a language model earns its keep, and it runs
**offline, once, as a batch** — never in the request path:

    make extract-schemes      # writes seed/generated/batch3_scheme/extracted.json
                              # commit it; review it; the demo never calls a model

Three constraints shape that.

**Its output is a proposal.** ADR-0014 is explicit that a fetch cannot assert that a
transcription faithfully represents the published text, and neither can a model — *"it makes
parser bugs indistinguishable from verified facts."* Everything written here lands
``UNVERIFIED`` and is capped by ``knowledge/gates.py`` until a named human confirms it.

**The demo must run with the network unplugged (NFR-303).** So the pipeline reads a committed
fixture, and only this script talks to a provider. A missing fixture means no extractions,
not a failure.

**Tool use, not free-text parsing.** CLAUDE.md §6 requires it, and nothing in the repository
did it before this. A JSON schema the model must fill is the difference between a null field
and a hallucinated deadline.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
import pathlib
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from agrivardhak.config import get_settings
from agrivardhak.domain.models.knowledge import KnowledgeChunk

if TYPE_CHECKING:  # pragma: no cover - typing only
    from anthropic.types import MessageParam, ToolChoiceToolParam, ToolParam

log = logging.getLogger(__name__)

PROMPT_PATH = pathlib.Path(__file__).resolve().parent / "prompts" / "scheme_extract.md"
PROMPT_VERSION = "scheme-extract-v1"

FIXTURE_PATH = (
    pathlib.Path(__file__).resolve().parents[4]
    / "seed"
    / "generated"
    / "batch3_scheme"
    / "extracted.json"
)

#: The shape the model must fill. Every field nullable, because for most orders the honest
#: answer is that the subject line does not say.
TOOL_SCHEMA: dict[str, Any] = {
    "name": "record_scheme_fields",
    "description": "Record scheme fields read verbatim from a Hindi government-order subject.",
    "input_schema": {
        "type": "object",
        "properties": {
            "scheme_name_hi": {
                "type": ["string", "null"],
                "description": "The scheme's own name, verbatim Hindi. Null if none is named.",
            },
            "beneficiary_hi": {
                "type": ["string", "null"],
                "description": "Who benefits, verbatim. Legal categories must be exact.",
            },
            "crops": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["Paddy", "Wheat", "Potato", "Mustard", "Guava"],
                },
                "description": "Only if an actual crop is named. Generic terms do not count.",
            },
            "financial_year": {"type": ["string", "null"]},
            "benefit_text_hi": {"type": ["string", "null"]},
            "deadline": {"type": ["string", "null"], "description": "ISO date, if stated."},
            "is_scheme_guidance": {"type": "boolean"},
            "notes_for_reviewer": {
                "type": ["string", "null"],
                "description": "What a human should check first. Be specific about doubt.",
            },
        },
        "required": ["crops", "is_scheme_guidance"],
    },
}


def load_fixture(path: pathlib.Path | None = None) -> dict[str, dict[str, Any]]:
    """Read the committed extractions, keyed by chunk dedupe identity. Absent is fine."""
    target = path or FIXTURE_PATH
    if not target.is_file():
        return {}
    payload = json.loads(target.read_text())
    entries = payload.get("extractions") or {}
    return {str(k): v for k, v in entries.items()} if isinstance(entries, dict) else {}


def apply_fixture(session: Session, path: pathlib.Path | None = None) -> int:
    """Attach committed proposals to their chunks.

    Writes ``extracted`` only. ``verification_status`` is untouched and stays ``UNVERIFIED``
    — this function cannot promote anything, by construction, which is the whole point of
    ADR-0014 being structural rather than procedural.
    """
    entries = load_fixture(path)
    if not entries:
        return 0
    updated = 0
    for chunk in session.execute(
        select(KnowledgeChunk).where(KnowledgeChunk.chunk_index == 0)
    ).scalars():
        proposal = entries.get(str(chunk.id)) or entries.get(_natural_key(chunk))
        if proposal is None or chunk.extracted is not None:
            continue
        chunk.extracted = {**proposal, "_prompt_version": PROMPT_VERSION}
        updated += 1
    session.flush()
    return updated


def _natural_key(chunk: KnowledgeChunk) -> str:
    """Identity that survives a re-seed, unlike the chunk's generated uuid.

    SHA-256 rather than ``hash()``: Python randomises string hashing per process, so a
    fixture keyed on it would match on the run that wrote it and silently match nothing
    afterwards — the failure would look like "the model extracted nothing useful".
    """
    digest = hashlib.sha256(chunk.text_hi.encode("utf-8")).hexdigest()[:16]
    return f"{chunk.source_key}:{chunk.observed_at.date().isoformat()}:{digest}"


def propose(session: Session, *, limit: int | None = None) -> dict[str, Any]:
    """Call the model over scheme-guidance chunks and return the fixture payload.

    Never called by the pipeline. Run it deliberately, read the diff, commit it.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "no ANTHROPIC api key configured — extraction is a deliberate offline batch, "
            "so set AGRI_ANTHROPIC_API_KEY and run it by hand"
        )
    import anthropic

    client = anthropic.Anthropic(
        api_key=settings.anthropic_api_key, timeout=settings.llm_timeout_seconds
    )
    system = PROMPT_PATH.read_text()

    statement = (
        select(KnowledgeChunk)
        .where(
            KnowledgeChunk.is_noise.is_(False),
            KnowledgeChunk.chunk_index == 0,
            KnowledgeChunk.source_key == "up-go-agriculture",
        )
        .order_by(KnowledgeChunk.observed_at.desc())
    )
    if limit is not None:
        statement = statement.limit(limit)

    extractions: dict[str, Any] = {}
    for chunk in session.execute(statement).scalars():
        response = client.messages.create(
            model=settings.orchestrator_model,
            max_tokens=1024,
            system=system,
            # The SDK's params are TypedDicts; the schema above is deliberately a plain
            # dict so it stays readable as a schema. Cast rather than restate it.
            tools=[cast("ToolParam", TOOL_SCHEMA)],
            tool_choice=cast("ToolChoiceToolParam", {"type": "tool", "name": TOOL_SCHEMA["name"]}),
            messages=[
                cast(
                    "MessageParam",
                    {
                        "role": "user",
                        # Fenced as data. Portal-supplied text is untrusted input to the
                        # model (NFR-405) — content to read, never instructions to follow.
                        "content": f"<ORDER>\n{chunk.text_hi}\n</ORDER>",
                    },
                )
            ],
        )
        block = next((b for b in response.content if b.type == "tool_use"), None)
        if block is None:
            log.warning("no tool call for chunk %s", chunk.id)
            continue
        extractions[_natural_key(chunk)] = dict(block.input)

    return {
        "_prompt_version": PROMPT_VERSION,
        "_model": settings.orchestrator_model,
        "_generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "_note": (
            "Proposals only. Every entry is UNVERIFIED under ADR-0014 and is capped below "
            "the orchestrator's confidence floor until a named human confirms it against "
            "the published Hindi."
        ),
        "extractions": extractions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", type=pathlib.Path, default=FIXTURE_PATH)
    args = parser.parse_args()

    from agrivardhak.db.session import session_scope

    with session_scope() as session:
        payload = propose(session, limit=args.limit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    count = len(payload["extractions"])
    print(f"wrote {count} proposals to {args.out}")
    print("Review them, then commit. Nothing is verified until a human sets verified_by.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
