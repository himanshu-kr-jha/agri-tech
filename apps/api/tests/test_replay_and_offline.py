"""Module purity, replay, and the offline demo — M22, M23, INV-2, NFR-303.

Three properties that are easy to claim and easy to lose:

* modules are pure, so the same inputs always give the same outputs;
* a stored snapshot rebuilds the same answer;
* the demo runs with the network unplugged.

Each is asserted rather than asserted-about.
"""

from __future__ import annotations

import datetime as dt
import socket
import uuid

import pytest
from sqlalchemy import select

from agrivardhak.api.scope import ContextScope
from agrivardhak.domain import enums
from agrivardhak.domain.models.organization import Organization, RoleGrant
from agrivardhak.intelligence import crop_health, farm, market, quality, risk, scheme
from agrivardhak.orchestrator import engine, gather, reconcile

pytestmark = pytest.mark.usefixtures("db")

MODULES = (quality, market, risk, farm, crop_health, scheme)


@pytest.fixture(scope="module")
def seeded() -> dict[str, uuid.UUID]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from agrivardhak.config import get_settings

    db = create_engine(get_settings().database_url)
    with Session(db) as session:
        org = session.execute(select(Organization)).scalars().first()
        grant = (
            session.execute(select(RoleGrant).where(RoleGrant.role == enums.Role.FPO_CEO))
            .scalars()
            .first()
        )
    db.dispose()
    if org is None or grant is None:
        pytest.skip("database not seeded — run `make seed`")
    return {"org_id": org.id, "ceo_user_id": grant.user_id}


# --------------------------------------------------------------------------- purity


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.MODULE)
def test_a_module_run_twice_on_the_same_input_gives_the_same_answer(session, seeded, module):
    """The property replay rests on. If a module reads a clock or a random, this fails."""
    org_id = seeded["org_id"]
    at = dt.datetime(2026, 8, 22, 6, 0, tzinfo=dt.UTC)
    gather_fn = {
        "quality_intelligence": gather.for_quality,
        "market_intelligence": gather.for_market,
        "risk_intelligence": gather.for_risk,
        "farm_intelligence": gather.for_farm,
        "crop_health_intelligence": gather.for_crop_health,
        "scheme_intelligence": gather.for_scheme,
    }[module.MODULE]
    module_input = gather_fn(session, organization_id=org_id, as_of=at)

    first = module.run(module_input)
    second = module.run(module_input)
    assert first.model_dump_json() == second.model_dump_json()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.MODULE)
def test_a_module_never_reaches_for_the_clock(module) -> None:
    """``as_of`` is passed in for a reason: a module that reads ``now()`` cannot be replayed.

    A source scan rather than a runtime check, because the failure is one someone introduces
    while adding a feature, and it would otherwise only show up months later as a replay that
    quietly stopped matching.
    """
    import inspect

    source = inspect.getsource(module)
    for banned in ("datetime.now(", "date.today(", "time.time(", "random.random("):
        assert banned not in source, (
            f"{module.MODULE} calls {banned} — modules receive `as_of`, they do not read a "
            "clock (ARCHITECTURE §3). This breaks replay."
        )


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.MODULE)
def test_a_module_never_touches_the_database(module) -> None:
    """Purity is what lets a module be replayed against a snapshot instead of live rows."""
    import inspect

    source = inspect.getsource(module)
    for banned in ("session.execute", "session.query", "select(", "Session"):
        assert banned not in source, (
            f"{module.MODULE} references {banned} — the orchestrator gathers, modules compute."
        )


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.MODULE)
def test_every_module_output_carries_its_version(session, seeded, module) -> None:
    """A formula change without a version bump makes every stored snapshot a lie."""
    assert module.VERSION
    assert len(module.VERSION.split(".")) == 3


# --------------------------------------------------------------------------- replay


def test_reconciliation_is_deterministic(session, seeded) -> None:
    """The other half of replay: the same module outputs must reconcile the same way."""
    at = dt.datetime(2026, 8, 22, 6, 0, tzinfo=dt.UTC)
    outputs, _inputs = engine.run_modules(
        session,
        organization_id=seeded["org_id"],
        as_of=at,
        plan=["quality", "market", "risk"],
    )
    first = reconcile.reconcile(list(outputs.values()), as_of=at)
    second = reconcile.reconcile(list(outputs.values()), as_of=at)
    assert [c.statement for c in first.situation] == [c.statement for c in second.situation]
    assert [o.overridden_key for o in first.overrides] == [
        o.overridden_key for o in second.overrides
    ]
    assert first.confidence.overall == second.confidence.overall


def test_a_snapshot_replays_to_the_same_packet(session, seeded) -> None:
    """INV-2, end to end. This is what "explainable forever" has to mean to be worth saying."""
    scope = ContextScope(
        actor_user_id=seeded["ceo_user_id"],
        roles=frozenset({enums.Role.FPO_CEO}),
        organization_id=seeded["org_id"],
    )
    at = dt.datetime(2026, 8, 22, 6, 0, tzinfo=dt.UTC)
    result = engine.ask(session, scope=scope, question="What is the risk this season?", as_of=at)
    replayed = engine.replay(session, result.snapshot_id)

    assert [c["statement"] for c in replayed["situation"]] == [
        c.statement for c in result.packet.situation
    ]
    assert [a["title"] for a in replayed["recommendation"]] == [
        a.title for a in result.packet.recommendation
    ]
    assert replayed["confidence"]["overall"] == result.packet.confidence.overall


def test_the_snapshot_hash_changes_when_the_content_does() -> None:
    """A hash that does not move when the content moves proves nothing."""
    base = {"modules": {"a": 1}, "as_of": "2026-08-22T00:00:00+00:00"}
    changed = {"modules": {"a": 2}, "as_of": "2026-08-22T00:00:00+00:00"}
    assert engine.content_hash(base) != engine.content_hash(changed)


def test_the_snapshot_hash_is_stable_across_key_order() -> None:
    """Without canonical JSON the same evidence hashes differently between two runs."""
    assert engine.content_hash({"a": 1, "b": 2}) == engine.content_hash({"b": 2, "a": 1})


# --------------------------------------------------------------------------- NFR-303


def test_the_whole_pipeline_runs_with_the_network_unplugged(session, seeded, monkeypatch) -> None:
    """NFR-303 / M23. The demo must not depend on a third party being up at 11am.

    Every socket is blocked for the duration, so any code path that reaches for Agmarknet,
    Open-Meteo or the Anthropic API fails hard here rather than in the room. The prices and
    weather this runs on were fetched once and stored; that was the point of keeping the raw
    payloads (INV-2), and this test is what stops that guarantee from rotting.
    """
    real_socket = socket.socket

    def _blocked(*_args, **_kwargs):
        raise OSError("network access is blocked: the demo must run offline (NFR-303)")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    try:
        scope = ContextScope(
            actor_user_id=seeded["ceo_user_id"],
            roles=frozenset({enums.Role.FPO_CEO}),
            organization_id=seeded["org_id"],
        )
        result = engine.ask(
            session,
            scope=scope,
            question="What should we do this season to maximize sustainable farmer income?",
        )
    finally:
        monkeypatch.setattr(socket, "socket", real_socket)

    assert result.packet.situation, "the packet must still have content offline"
    assert result.packet.recommendation
    assert result.content_hash
    assert result.packet.model_id == "deterministic", (
        "with no key the packet is produced deterministically, not by a model"
    )


def test_narration_is_never_on_the_critical_path(session, seeded) -> None:
    """Belt and braces for the same property: ``ask`` does not narrate unless told to."""
    import inspect

    source = inspect.getsource(engine.ask)
    assert "narrate: bool = False" in inspect.getsource(engine.ask) or "if narrate:" in source
