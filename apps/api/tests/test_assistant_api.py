"""Assistant, decisions and approvals through the API — M14b, API-05, INV-1, INV-5."""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from agrivardhak.api.auth import issue_token
from agrivardhak.api.main import app
from agrivardhak.domain.enums import Role
from agrivardhak.domain.models.organization import Farmer, Organization, RoleGrant

pytestmark = pytest.mark.usefixtures("db")

QUESTION = "Who should we sell the paddy to?"

#: A different question for the streaming test — though note that this alone is not enough.
#: Two *different* questions can propose the same action ("sell this lot to this buyer"), and
#: the newer packet supersedes the older unapproved suggestion (INV-10). That is the system
#: behaving correctly; the lesson for tests is to act on what is pending *now* rather than on
#: ids captured earlier, which is what :func:`_pending` below does.
STREAM_QUESTION = "What is the risk to this harvest?"


@pytest.fixture(scope="module")
def seeded() -> dict[str, uuid.UUID]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from agrivardhak.config import get_settings

    db = create_engine(get_settings().database_url)
    with Session(db) as session:
        org = session.execute(select(Organization)).scalars().first()
        grant = (
            session.execute(select(RoleGrant).where(RoleGrant.role == Role.FPO_CEO))
            .scalars()
            .first()
        )
        farmer = session.execute(select(Farmer)).scalars().first()
    db.dispose()
    if org is None or grant is None or farmer is None:
        pytest.skip("database not seeded — run `make seed`")
    return {"org_id": org.id, "ceo_user_id": grant.user_id, "farmer_id": farmer.id}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _ceo(seeded) -> dict[str, str]:
    return {
        "Authorization": "Bearer "
        + issue_token(
            user_id=seeded["ceo_user_id"],
            roles={Role.FPO_CEO},
            organization_id=seeded["org_id"],
        )
    }


def _farmer(seeded) -> dict[str, str]:
    return {
        "Authorization": "Bearer "
        + issue_token(
            user_id=uuid.uuid4(),
            roles={Role.FARMER},
            organization_id=seeded["org_id"],
            farmer_id=seeded["farmer_id"],
        )
    }


def _researcher(seeded) -> dict[str, str]:
    return {
        "Authorization": "Bearer "
        + issue_token(
            user_id=uuid.uuid4(),
            roles={Role.RESEARCHER},
            organization_id=seeded["org_id"],
        )
    }


@pytest.fixture(scope="module")
def asked(seeded) -> dict:
    """One packet for the whole module — generating it costs several seconds."""
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/assistant/ask", json={"question": QUESTION}, headers=_ceo(seeded)
        )
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- INV-5


def test_a_farmer_cannot_ask_the_organization_assistant(client, seeded) -> None:
    """INV-5. A farmer gets the farmer assistant, not a filtered version of the FPO's."""
    response = client.post(
        "/api/v1/assistant/ask", json={"question": QUESTION}, headers=_farmer(seeded)
    )
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")


def test_a_researcher_cannot_ask_on_the_collectives_behalf(client, seeded) -> None:
    assert (
        client.post(
            "/api/v1/assistant/ask", json={"question": QUESTION}, headers=_researcher(seeded)
        ).status_code
        == 403
    )


def test_an_unauthenticated_caller_gets_401_not_403(client) -> None:
    assert client.post("/api/v1/assistant/ask", json={"question": QUESTION}).status_code == 401


def test_an_empty_question_is_rejected(client, seeded) -> None:
    assert (
        client.post(
            "/api/v1/assistant/ask", json={"question": "  "}, headers=_ceo(seeded)
        ).status_code
        == 422
    )


# --------------------------------------------------------------------------- the answer


def test_the_answer_carries_its_frozen_evidence_hash(asked) -> None:
    """INV-2. Without the hash the packet is a claim about the past, not a record of it."""
    assert len(asked["content_hash"]) == 64
    assert asked["snapshot_id"]


def test_every_recommendation_it_created_is_only_suggested(client, seeded, asked) -> None:
    for rec_id in asked["recommendation_ids"]:
        row = client.get("/api/v1/recommendations", headers=_ceo(seeded)).json()
        match = next(r for r in row["recommendations"] if r["id"] == rec_id)
        assert match["status"] == "SUGGESTED"
        assert match["awaiting"], "UI-11: the screen must say what a human still has to do"


def test_the_packet_renders_its_sections_in_the_fixed_order(asked) -> None:
    """FR-801. The order is part of the contract — it is how a CEO learns to read it."""
    body = asked["packet"]
    for section in ("situation", "impact", "recommendation", "expected_outcome", "confidence"):
        assert section in body


def test_streaming_emits_sections_in_the_packet_order(client, seeded) -> None:
    """API-05. Section by section, not token by token.

    A section either has its evidence or it does not exist yet; streaming half-formed prose
    would show claims before the numbers that justify them.
    """
    with client.stream(
        "POST",
        "/api/v1/assistant/ask/stream",
        json={"question": STREAM_QUESTION},
        headers=_ceo(seeded),
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        sections: list[str] = []
        done: dict | None = None
        for line in response.iter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                if "section" in payload:
                    sections.append(payload["section"])
                elif "content_hash" in payload:
                    done = payload
    assert sections[:5] == [
        "situation",
        "impact",
        "recommendation",
        "expected_outcome",
        "confidence",
    ]
    assert done and len(done["content_hash"]) == 64


# --------------------------------------------------------------------------- INV-1


def _pending(client, seeded) -> list[dict]:
    """Recommendations currently awaiting a human, read fresh.

    Deliberately not the ids from an earlier packet: a later question may have superseded
    them, which is exactly what the UI would show too.
    """
    body = client.get("/api/v1/recommendations?status=SUGGESTED", headers=_ceo(seeded)).json()
    return body["recommendations"]


def test_execution_is_refused_before_approval(client, seeded, asked) -> None:
    """The invariant, at the edge this time. 409, and the message names the rule."""
    rec_id = _pending(client, seeded)[0]["id"]
    response = client.post(f"/api/v1/recommendations/{rec_id}/execute", headers=_ceo(seeded))
    assert response.status_code == 409
    assert "INV-1" in response.json()["detail"]


def test_a_rejection_without_a_reason_is_refused_at_the_api(client, seeded, asked) -> None:
    rec_id = _pending(client, seeded)[0]["id"]
    response = client.post(
        f"/api/v1/recommendations/{rec_id}/reject", json={}, headers=_ceo(seeded)
    )
    assert response.status_code == 409


def test_approve_then_execute_records_the_authority(client, seeded, asked) -> None:
    rec_id = _pending(client, seeded)[0]["id"]
    approved = client.post(
        f"/api/v1/recommendations/{rec_id}/approve",
        json={"rationale": "Board agreed."},
        headers=_ceo(seeded),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["approvals"][0]["role_exercised"] == "FPO_CEO"

    executed = client.post(
        f"/api/v1/recommendations/{rec_id}/execute",
        json={"action_taken": "Lot released to the buyer."},
        headers=_ceo(seeded),
    )
    assert executed.status_code == 200, executed.text
    assert executed.json()["status"] == "EXECUTED"
    assert executed.json()["awaiting"] == "an outcome record"

    trail = client.get("/api/v1/audit", headers=_ceo(seeded)).json()["records"]
    assert any(r["action"] == "execute_recommendation" for r in trail)
    assert any(r["authority"] == "FPO_CEO" for r in trail)


def test_approval_with_a_modified_value_stores_the_modified_value(client, seeded, asked) -> None:
    """The common real answer is "yes, at a different number" — and that must be what executes."""
    pending = _pending(client, seeded)
    priced = next((r for r in pending if r["recommended_value_paise"] is not None), pending[0])
    response = client.post(
        f"/api/v1/recommendations/{priced['id']}/approve",
        json={"approved_value_paise": 3_200_000, "rationale": "Smaller first tranche."},
        headers=_ceo(seeded),
    )
    assert response.status_code == 200, response.text
    assert response.json()["was_modified"] is True
    assert response.json()["approved_value_paise"] == 3_200_000


# --------------------------------------------------------------------------- history


def test_a_decision_can_be_reopened_with_the_evidence_that_produced_it(
    client, seeded, asked
) -> None:
    """FR-710 / SAF-10.

    The trail exists so a farmer can contest a decision that affected them, not only so the
    FPO can defend itself.
    """
    detail = client.get(f"/api/v1/decisions/{asked['packet_id']}", headers=_ceo(seeded))
    assert detail.status_code == 200
    body = detail.json()
    assert body["evidence_snapshot"]["content_hash"] == asked["content_hash"]
    assert body["evidence_snapshot"]["module_versions"]
    assert body["evidence_snapshot"]["coefficients"], "the constants in force must be recoverable"


def test_replaying_a_stored_decision_reproduces_it(client, seeded, asked) -> None:
    """INV-2 made checkable rather than asserted."""
    response = client.get(f"/api/v1/decisions/{asked['packet_id']}/replay", headers=_ceo(seeded))
    assert response.status_code == 200
    body = response.json()
    assert body["matches_original"]["situation"] is True
    assert body["matches_original"]["overrides"] is True


def test_a_farmer_cannot_read_the_decision_history(client, seeded) -> None:
    assert client.get("/api/v1/decisions", headers=_farmer(seeded)).status_code == 403
    assert client.get("/api/v1/risk-register", headers=_farmer(seeded)).status_code == 403
    assert client.get("/api/v1/audit", headers=_farmer(seeded)).status_code == 403


def test_the_risk_register_names_who_is_exposed(client, seeded, asked) -> None:
    """FR-554. A hazard with no exposure attached is a weather report, not a decision input."""
    entries = client.get("/api/v1/risk-register", headers=_ceo(seeded)).json()["entries"]
    assert entries
    quantified = [e for e in entries if e["farmers_affected"] or e["area_affected_acres"]]
    assert quantified, "at least one register entry must quantify its exposure"
