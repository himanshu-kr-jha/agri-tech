"""LLM narration — M13c, NFR-302, NFR-303, NFR-405.

The narrator's whole design is about what happens when it does not work. A packet that is
slightly drier is a fine outcome; a request that 500s because a third-party API was slow is
not, and a demo that needs a network is a demo that fails in the room.
"""

from __future__ import annotations

import datetime as dt
import uuid

from agrivardhak.intelligence.contracts import EvidenceRef
from agrivardhak.orchestrator import narrator
from agrivardhak.orchestrator.packet import (
    Claim,
    ConfidenceBlock,
    DecisionPacket,
    PacketScope,
)

NOW = dt.datetime(2026, 1, 20, tzinfo=dt.UTC)


def _packet() -> DecisionPacket:
    ref = EvidenceRef(kind="observation", id=uuid.uuid4(), label="obs", as_of=NOW)
    return DecisionPacket(
        question="What should we do this season?",
        scope=PacketScope(organization_id=uuid.uuid4(), audience="FPO"),
        situation=[
            Claim(
                statement="Paddy harvests into its annual price trough.",
                magnitude=None,
                unit=None,
                confidence=0.7,
                evidence=[ref],
            )
        ],
        impact=[Claim(statement="1,868 t are exposed.", confidence=0.58, evidence=[ref])],
        confidence=ConfidenceBlock(overall=0.7),
        generated_at=NOW,
        snapshot_id=uuid.uuid4(),
        prompt_version="packet-v1",
        model_id="deterministic",
    )


def test_narration_failure_returns_the_packet_unchanged(monkeypatch) -> None:
    """NFR-302. Any failure at all — key, timeout, refusal, bad JSON — degrades to silence."""

    def _explode(*_args, **_kwargs):
        raise TimeoutError("the model took too long")

    monkeypatch.setattr(narrator, "_call", _explode)
    monkeypatch.setattr(
        narrator,
        "get_settings",
        lambda: type(
            "S",
            (),
            {
                "anthropic_api_key": "sk-test",
                "use_fixtures": False,
                "orchestrator_model": "claude-sonnet-5",
                "llm_timeout_seconds": 30.0,
            },
        )(),
    )
    original = _packet()
    assert narrator.narrate(original, {}) is original


def test_no_api_key_skips_narration_rather_than_erroring(monkeypatch) -> None:
    """NFR-303. The offline demo path must be the default, not a fallback nobody tested."""
    monkeypatch.setattr(
        narrator,
        "get_settings",
        lambda: type(
            "S",
            (),
            {
                "anthropic_api_key": None,
                "use_fixtures": False,
                "orchestrator_model": "claude-sonnet-5",
                "llm_timeout_seconds": 30.0,
            },
        )(),
    )
    original = _packet()
    assert narrator.narrate(original, {}) is original


def test_narration_may_change_prose_but_not_a_single_number(monkeypatch) -> None:
    """The containment property (NFR-405).

    The model is handed only statements and returns only statements. Magnitudes,
    confidences and evidence refs are re-asserted from the original object, so even a model
    that returned extra fields — or one steered by injected text — cannot move a number or
    detach a claim from its evidence.
    """
    original = _packet()
    merged = narrator._merge(
        original,
        {
            "0": "The paddy harvest lands when prices are at their lowest.",
            "1": "Nearly 1,900 tonnes are affected.",
        },
    )
    assert merged.situation[0].statement != original.situation[0].statement
    assert merged.situation[0].confidence == original.situation[0].confidence
    assert merged.situation[0].evidence == original.situation[0].evidence
    assert merged.impact[0].confidence == original.impact[0].confidence
    assert merged.confidence.overall == original.confidence.overall


def test_a_missing_rewrite_keeps_the_deterministic_wording(monkeypatch) -> None:
    """A partial response must not blank a claim."""
    original = _packet()
    merged = narrator._merge(original, {"0": "   "})
    assert merged.situation[0].statement == original.situation[0].statement


def test_the_system_prompt_forbids_inventing_numbers() -> None:
    """Cheap to assert, and it is the instruction the whole containment story rests on."""
    lowered = narrator.SYSTEM.lower()
    assert "never introduce a number" in lowered
    assert "untrusted" in lowered
    assert "never remove a number" in lowered
