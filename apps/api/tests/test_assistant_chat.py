"""The conversational assistant — routing, the review gate, and the boundary.

These tests are arranged around the things that would be *silently* wrong rather than loudly
broken: a farmer reaching organization data, a relevance filter quietly deleting an override,
a follow-up answered by re-running the pipeline instead of reading frozen bytes.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid

import pytest
from sqlalchemy import func, select

from agrivardhak.api.scope import ContextScope
from agrivardhak.domain import enums, irrigation
from agrivardhak.domain.models.land import Farm
from agrivardhak.domain.models.organization import Announcement, Farmer, Organization, RoleGrant
from agrivardhak.intelligence.contracts import EvidenceRef, Finding, ProposedAction
from agrivardhak.orchestrator import chat, reconcile, review, router
from agrivardhak.orchestrator.assistant_contracts import (
    FARMER_LOOKUPS,
    FPO_LOOKUPS,
    PROTECTED_SECTIONS,
    AssistantRequest,
    LookupKey,
    ResponseShape,
    lookups_for,
)
from agrivardhak.orchestrator.lookups import farmer as farmer_lookups
from agrivardhak.orchestrator.lookups import fpo as fpo_lookups
from agrivardhak.orchestrator.packet import Claim
from agrivardhak.seed.generator import _seed_announcements

pytestmark = pytest.mark.usefixtures("db")


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
        farmer = (
            session.execute(
                select(Farmer).join(Farm, Farm.operator_farmer_id == Farmer.id).limit(1)
            )
            .scalars()
            .first()
        )
    db.dispose()
    if org is None or grant is None or farmer is None:
        pytest.skip("database not seeded — run `make seed`")
    return {"org_id": org.id, "ceo_user_id": grant.user_id, "farmer_id": farmer.id}


@pytest.fixture
def no_model(monkeypatch):
    """Force the no-provider condition instead of assuming the environment has none.

    The first version of this asserted that no key was configured, which passed on a laptop
    with an empty ``.env`` and failed the moment someone added a real one — testing the
    developer's environment rather than the property. NFR-303 is a claim about the software:
    it must hold whether or not a key exists, so the test creates the condition it tests.
    """
    from agrivardhak.config import get_settings

    monkeypatch.setenv("AGRI_LLM_PROVIDER", "none")
    monkeypatch.setenv("AGRI_NVIDIA_API_KEY", "")
    monkeypatch.setenv("AGRI_ANTHROPIC_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def ceo(seeded) -> ContextScope:
    return ContextScope(
        actor_user_id=seeded["ceo_user_id"],
        roles=frozenset({enums.Role.FPO_CEO}),
        organization_id=seeded["org_id"],
    )


@pytest.fixture
def member(seeded) -> ContextScope:
    return ContextScope(
        actor_user_id=seeded["ceo_user_id"],
        roles=frozenset({enums.Role.FARMER}),
        organization_id=seeded["org_id"],
        farmer_id=seeded["farmer_id"],
    )


# --------------------------------------------------------------------------- the boundary


def test_a_farmer_can_never_be_routed_to_an_organization_lookup() -> None:
    """INV-5 must not depend on the model behaving.

    The vocabularies are disjoint and the router validates its own output against the
    audience's set, so a model that asks for an organization lookup on a farmer turn is
    refused rather than obeyed.
    """
    assert not (FPO_LOOKUPS & FARMER_LOOKUPS)
    for key in FPO_LOOKUPS:
        rejected = router._validate(
            {
                "shape": "LOOKUP",
                "lookup": key.value,
                "modules": [],
                "rationale": "",
                "router_confidence": 1.0,
            },
            audience="FARMER",
            has_anchor=False,
        )
        assert rejected is None, f"{key.value} must not be reachable from a farmer turn"


def test_a_farmer_is_never_routed_to_a_decision() -> None:
    """Decision Packets are organization-scoped by construction; a farmer has no such path."""
    assert (
        router._validate(
            {
                "shape": "DECISION",
                "lookup": None,
                "modules": ["quality"],
                "rationale": "",
                "router_confidence": 1.0,
            },
            audience="FARMER",
            has_anchor=False,
        )
        is None
    )
    assert "DECISION" not in router._shapes_for("FARMER")
    assert "DECISION" in router._shapes_for("FPO")


def test_internal_announcements_never_reach_a_farmer(session, seeded) -> None:
    """The only mechanism for information to cross is an announcement someone shared."""
    _seed_announcements(session, session.get(Organization, seeded["org_id"]))
    session.flush()
    internal = [
        row.title
        for row in session.execute(
            select(Announcement).where(
                Announcement.visibility == enums.VisibilityScope.ORG_INTERNAL
            )
        ).scalars()
    ]
    assert internal, "the fixture must actually hold something internal, or this proves nothing"

    claims = farmer_lookups.run(
        session,
        key=LookupKey.MY_ANNOUNCEMENTS,
        farmer_id=seeded["farmer_id"],
        as_of=dt.datetime.now(dt.UTC),
    )
    rendered = " ".join(c.statement for c in claims)
    for title in internal:
        assert title not in rendered


def test_the_farmer_module_exposes_no_organization_query() -> None:
    """The separation is structural, not conventional.

    Asserted on the import graph rather than on the text, so a docstring that *mentions* the
    organization module does not fail while an actual import would pass. What must hold is
    that no organization query is reachable from farmer code — if someone later adds a shared
    helper "just for one lookup", this is the test that objects.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(farmer_lookups))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
            imported.add(node.module)
    assert not any("lookups.fpo" in name or name.endswith(".fpo") for name in imported), (
        f"farmer lookups must not import organization queries; found {sorted(imported)}"
    )


# --------------------------------------------------------------------------- the review gate


def test_grounding_rejects_a_claim_that_cites_evidence_nobody_produced() -> None:
    """The last barrier between a plausible sentence and a screen (FR-804)."""
    real = Claim(
        statement="Paddy is 99% of operated area.",
        confidence=0.9,
        evidence=[
            EvidenceRef(
                kind="domain_row", id=uuid.uuid4(), label="cycle", as_of=dt.datetime.now(dt.UTC)
            )
        ],
    )
    fabricated = Claim(
        statement="Paddy is 99% of operated area.",
        confidence=0.9,
        evidence=[
            EvidenceRef(
                kind="domain_row", id=uuid.uuid4(), label="invented", as_of=dt.datetime.now(dt.UTC)
            )
        ],
    )
    assert review.grounded([real], [real])
    assert not review.grounded([fabricated], [real])


def test_grounding_rejects_a_statement_that_was_never_produced() -> None:
    real = Claim(
        statement="Real claim.",
        confidence=0.9,
        evidence=[
            EvidenceRef(
                kind="domain_row", id=uuid.uuid4(), label="x", as_of=dt.datetime.now(dt.UTC)
            )
        ],
    )
    invented = real.model_copy(update={"statement": "A sentence the modules never emitted."})
    assert not review.grounded([invented], [real])


def test_the_selector_cannot_drop_a_protected_section(session, seeded, ceo) -> None:
    """A silent override is a trust failure (FR-802) — and so is a silently dropped one.

    Driven through the real selector with whatever provider is configured. Under the offline
    fallback it returns everything, which also satisfies the property; the point is that no
    configuration produces a packet missing its overrides or its confidence block.
    """
    from agrivardhak.orchestrator import engine

    result = engine.ask(
        session, scope=ceo, question="What should we do this season to maximize farmer income?"
    )
    sections = review.select_sections("who should we sell to", result.packet)
    populated = {name for name in result.packet.SECTION_ORDER if getattr(result.packet, name, None)}
    if result.packet.overrides:
        populated.add("overrides")
    assert (PROTECTED_SECTIONS & populated) <= set(sections)
    assert set(sections) <= populated, "the selector may not invent a section"


# --------------------------------------------------------------------------- offline


def test_the_whole_chat_works_with_no_model_configured(session, ceo, member, no_model) -> None:
    """NFR-303. Degraded to keyword routing, but functional — the demo survives bad wifi."""
    from agrivardhak.orchestrator import llm

    assert not llm.available()

    staff = chat.answer(session, scope=ceo, request=AssistantRequest(question="what is the risk"))
    assert staff.plan.fell_back
    assert staff.shape is ResponseShape.DECISION
    assert staff.packet is not None

    own = chat.answer(
        session, scope=member, request=AssistantRequest(question="what schemes apply to me")
    )
    assert own.plan.fell_back
    assert own.shape is ResponseShape.LOOKUP
    assert (
        own.lookup_or_none()
        if hasattr(own, "lookup_or_none")
        else own.plan.lookup in FARMER_LOOKUPS
    )
    assert own.claims


def test_every_turn_is_recorded_whatever_shape_it_took(session, member) -> None:
    """FR-709: a system that logs its decisions but not its answers has a hole in the trail."""
    from agrivardhak.domain.models.operations import ConversationTurn

    conversation = uuid.uuid4()
    chat.answer(
        session,
        scope=member,
        request=AssistantRequest(question="what should I do today", conversation_id=conversation),
    )
    session.flush()
    turns = list(
        session.execute(
            select(ConversationTurn).where(ConversationTurn.conversation_id == conversation)
        ).scalars()
    )
    assert len(turns) == 1
    assert turns[0].shape == ResponseShape.LOOKUP.value
    assert turns[0].farmer_id is not None


# --------------------------------------------------------------------------- lookups


def test_every_lookup_key_is_answerable(session, seeded) -> None:
    """A key the router can choose but nothing can answer is a dead end the model will find."""
    now = dt.datetime.now(dt.UTC)
    for key in FPO_LOOKUPS:
        claims = fpo_lookups.run(session, key=key, organization_id=seeded["org_id"], as_of=now)
        assert claims, f"{key.value} returned nothing"
    for key in FARMER_LOOKUPS:
        claims = farmer_lookups.run(session, key=key, farmer_id=seeded["farmer_id"], as_of=now)
        assert claims, f"{key.value} returned nothing"


def test_every_claim_carries_evidence(session, seeded) -> None:
    """Enforced by the schema, asserted here because it is the property everything rests on."""
    now = dt.datetime.now(dt.UTC)
    for key in FPO_LOOKUPS:
        for claim in fpo_lookups.run(session, key=key, organization_id=seeded["org_id"], as_of=now):
            assert claim.evidence, f"{key.value} produced an unevidenced claim"


def test_the_lookup_vocabulary_covers_both_audiences_and_nothing_else() -> None:
    assert lookups_for("FARMER") == FARMER_LOOKUPS
    assert lookups_for("FPO") == FPO_LOOKUPS
    assert set(LookupKey) == FPO_LOOKUPS | FARMER_LOOKUPS


# --------------------------------------------------------------------------- crop focus


def test_a_question_naming_a_crop_extracts_it() -> None:
    """The crop is a closed vocabulary too: one we grow, or none at all."""
    plan = router._validate(
        {
            "shape": "DECISION",
            "lookup": None,
            "modules": ["market"],
            "named_crop_text": "Guava",
            "horizon_days": 365,
            "rationale": "",
            "router_confidence": 0.9,
        },
        audience="FPO",
        has_anchor=False,
    )
    assert plan is not None
    assert plan.entities["crop"] == "Guava"
    assert plan.entities["horizon_days"] == 365

    invented = router._validate(
        {
            "shape": "DECISION",
            "lookup": None,
            "modules": [],
            "named_crop_text": "Dragonfruit",
            "horizon_days": None,
            "rationale": "",
            "router_confidence": 0.9,
        },
        audience="FPO",
        has_anchor=False,
    )
    assert invented is not None
    assert "crop" not in invented.entities, "a crop we do not grow must never become a focus"
    assert invented.entities["unknown_crop"] == "Dragonfruit"


def test_focus_reorders_without_amputating() -> None:
    """Boost the named subject, demote other named ones, leave cross-cutting findings alone.

    Demoted rather than dropped on purpose: that guava is 0.5% of operated area is context
    the answer needs, not noise to hide.
    """

    def finding(key: str) -> Finding:
        return Finding(
            key=key,
            statement="x",
            confidence=0.8,
            evidence=[
                EvidenceRef(
                    kind="domain_row", id=uuid.uuid4(), label="e", as_of=dt.datetime.now(dt.UTC)
                )
            ],
        )

    assert reconcile.focus_weight(finding("price_trough.guava"), "Guava") == reconcile.FOCUS_BOOST
    assert reconcile.focus_weight(finding("price_trough.paddy"), "Guava") == reconcile.FOCUS_DEMOTE
    assert reconcile.focus_weight(finding("close_capital_gap"), "Guava") == 1.0
    assert reconcile.focus_weight(finding("price_trough.paddy"), None) == 1.0


def test_an_action_is_matched_by_key_or_title() -> None:
    """The regression that produced the bug: market keys its actions by lot id, not by crop.

    ``stagger_sale.paddy`` carries the crop in the key; ``sell.<uuid>`` carries it only in the
    title. Matching on the key alone silently excluded every sale action from every focused
    question — so "how will we increase guava sales" could not reach the guava buyer.
    """

    def action(key: str, title: str) -> ProposedAction:
        return ProposedAction(
            key=key,
            title=title,
            rationale="r",
            recommendation_type="BUYER_SELECTION",
            target_type="lot",
            confidence=0.7,
            evidence=[
                EvidenceRef(
                    kind="domain_row", id=uuid.uuid4(), label="e", as_of=dt.datetime.now(dt.UTC)
                )
            ],
        )

    by_key = action("stagger_sale.paddy", "Stagger the Paddy sale")
    by_title = action("sell.01a02e1c-0f20-72c3-9e17-0be485d2b26c", "Sell 223,039 kg Guava to X")
    assert reconcile._action_is_about(by_key, "Paddy")
    assert reconcile._action_is_about(by_title, "Guava")
    assert not reconcile._action_is_about(by_title, "Paddy")


def test_a_crop_question_is_not_answered_with_another_crops_action(session, ceo) -> None:
    """The reported bug, end to end: guava must not be answered with the paddy plan."""
    from agrivardhak.orchestrator import engine

    guava = engine.ask(
        session,
        scope=ceo,
        question="how will we increase guava sales this year",
        focus_subject="Guava",
    )
    titles = " ".join(a.title.lower() for a in guava.packet.recommendation)
    assert "paddy" not in titles, f"a guava question proposed a paddy action: {titles}"
    if guava.packet.recommendation:
        assert "guava" in titles

    unfocused = engine.ask(
        session, scope=ceo, question="what should we do this season to maximize farmer income"
    )
    assert unfocused.packet.recommendation, "an unfocused question must still get the full plan"


def test_a_focused_packet_still_replays_identically(session, ceo) -> None:
    """INV-2 survives the focus.

    The focus changes the ranking, so it is part of what produced the answer and has to be
    frozen with everything else. If it were not, a focused packet would replay through an
    unfocused reconciler and diverge — the exact failure the replay endpoint exists to catch.
    """
    from agrivardhak.orchestrator import engine

    result = engine.ask(
        session,
        scope=ceo,
        question="how will we increase guava sales this year",
        focus_subject="Guava",
    )
    session.flush()
    replayed = engine.replay(session, result.snapshot_id)
    original = json.loads(result.packet.model_dump_json())
    for section in ("situation", "impact", "recommendation", "overrides"):
        assert replayed[section] == original[section], f"{section} diverged on replay"


# --------------------------------------------------------------------------- plain facts


def test_a_plain_count_question_has_somewhere_to_go() -> None:
    """The gap that produced "how many farmers do we have?" -> a season-long crop plan.

    The vocabulary had been designed around decisions and omitted plain facts, so the router
    correctly reported that no key fitted, validation rejected the empty lookup, and the
    question fell through to a full Decision Packet. Coverage is the fix; this asserts the
    keys exist and are audience-correct.
    """
    assert LookupKey.MEMBERSHIP_SUMMARY in FPO_LOOKUPS
    assert LookupKey.LAND_SUMMARY in FPO_LOOKUPS
    assert LookupKey.MY_FARM_PROFILE in FARMER_LOOKUPS
    for key in (LookupKey.MEMBERSHIP_SUMMARY, LookupKey.LAND_SUMMARY):
        assert key not in FARMER_LOOKUPS, "a member cannot ask for the whole register"


def test_membership_summary_counts_the_members(session, seeded) -> None:
    from agrivardhak.domain.models.organization import Membership

    expected = session.execute(
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.organization_id == seeded["org_id"],
            Membership.status == enums.MembershipStatus.ACTIVE,
        )
    ).scalar_one()
    claims = fpo_lookups.run(
        session,
        key=LookupKey.MEMBERSHIP_SUMMARY,
        organization_id=seeded["org_id"],
        as_of=dt.datetime.now(dt.UTC),
    )
    assert f"{expected:,}" in claims[0].statement
    assert float(claims[0].magnitude) == expected


def test_a_synthetic_register_says_so(session, seeded) -> None:
    """CLAUDE.md §5. A membership count is exactly the number someone quotes in a pitch."""
    claims = fpo_lookups.run(
        session,
        key=LookupKey.MEMBERSHIP_SUMMARY,
        organization_id=seeded["org_id"],
        as_of=dt.datetime.now(dt.UTC),
    )
    assert any("SYNTHETIC — DEMO ONLY" in c.statement for c in claims)


# --------------------------------------------------------------------------- irrigation


def test_rain_fed_plots_are_not_counted_as_irrigated() -> None:
    """The spelling bug that silently inflated every production forecast.

    Five call sites each hand-wrote ``.upper() not in ("", "RAINFED")`` while the seed
    records ``"Rain-fed"``. Upper-cased that is ``"RAIN-FED"``, which does not match, so all
    510 rain-fed plots were treated as having assured water — a 1.0 water factor instead of
    0.72 across a third of the collective's land.
    """
    for rainfed in ("Rain-fed", "RAIN-FED", "rain fed", "  rainfed ", "", None, "None"):
        assert not irrigation.water_assured(rainfed), f"{rainfed!r} must not count as irrigated"
    for assured in ("Canal", "Borewell", "Tubewell", "canal"):
        assert irrigation.water_assured(assured)


def test_the_seeded_collective_is_not_entirely_irrigated(session, seeded) -> None:
    """A whole-number sanity check the unit test above cannot give.

    The demo turns on Yamuna-Par being water-constrained. "100% irrigated" is the shape this
    bug took in the answer, so the assertion is on the answer, not only on the predicate.
    """
    claims = fpo_lookups.run(
        session,
        key=LookupKey.LAND_SUMMARY,
        organization_id=seeded["org_id"],
        as_of=dt.datetime.now(dt.UTC),
    )
    rendered = " ".join(c.statement for c in claims)
    assert "100% irrigated" not in rendered

    # Against the database, not against the prose. The first version of this asserted
    # `"0 are rain-fed" not in rendered`, which passes trivially — and wrongly — because
    # "0 are rain-fed" is a substring of "510 are rain-fed".
    from agrivardhak.domain.models.land import Farm, Plot
    from agrivardhak.domain.models.organization import Membership

    sources = session.execute(
        select(Plot.irrigation_source)
        .join(Farm, Plot.farm_id == Farm.id)
        .join(Farmer, Farm.operator_farmer_id == Farmer.id)
        .join(Membership, Membership.farmer_id == Farmer.id)
        .where(Membership.organization_id == seeded["org_id"])
    ).scalars()
    rainfed = sum(1 for src in sources if not irrigation.water_assured(src))
    assert rainfed > 0, "the seed must contain rain-fed plots or this proves nothing"
    assert f"{rainfed:,} are rain-fed" in rendered


def test_the_quality_module_sees_the_rain_fed_plots(session, seeded) -> None:
    """The bug's real cost was here: a yield factor of 1.0 where it should be 0.72."""
    from agrivardhak.orchestrator import gather

    module_input = gather.for_quality(
        session, organization_id=seeded["org_id"], as_of=dt.datetime.now(dt.UTC)
    )
    cycles = module_input.data["cycles"]
    assert cycles
    assert any(not c.water_assured for c in cycles), (
        "no cycle is rain-fed — the irrigation predicate has regressed"
    )


# --------------------------------------------------------------------------- unknown crops


def test_a_crop_we_do_not_grow_is_recognised_as_unknown() -> None:
    """The enum was the hallucination vector, so the enum is gone.

    Offered ``{Potato, Wheat, Paddy, Mustard, Guava}`` or null and asked about tomato, the
    model answered "Paddy" — a valid enum value and an entirely invented one. The packet then
    claimed to be focused on a crop nobody had mentioned, which is worse than no focus at
    all. The router now reports the crop as free text and the match happens here.
    """
    known = router._validate(
        {
            "shape": "DECISION",
            "lookup": None,
            "modules": [],
            "named_crop_text": "guava",
            "horizon_days": None,
            "rationale": "",
            "router_confidence": 0.9,
        },
        audience="FPO",
        has_anchor=False,
    )
    assert known is not None and known.entities["crop"] == "Guava"

    unknown = router._validate(
        {
            "shape": "DECISION",
            "lookup": None,
            "modules": [],
            "named_crop_text": "grapes",
            "horizon_days": None,
            "rationale": "",
            "router_confidence": 0.9,
        },
        audience="FPO",
        has_anchor=False,
    )
    assert unknown is not None
    assert unknown.entities.get("unknown_crop") == "grapes"
    assert "crop" not in unknown.entities, "an unknown crop must never become a focus"


def test_crop_names_match_across_the_plural() -> None:
    """A person types "grapes" and "tomatoes"; the question is whether we hold data, not
    whether they matched our spelling."""
    assert router._known_crop("guava") == "Guava"
    assert router._known_crop("Potatoes") == "Potato"
    assert router._known_crop("PADDY") == "Paddy"
    assert router._known_crop("grapes") is None
    assert router._known_crop("tomato") is None


def test_crop_text_from_a_model_is_bounded() -> None:
    """It is compared against our list and echoed into a sentence; it is not a free channel."""
    assert router._clean_crop_text("  Guava ") == "Guava"
    assert router._clean_crop_text("x" * 200) is None
    assert router._clean_crop_text("<script>alert(1)</script>") is None
    assert router._clean_crop_text("") is None
    assert router._clean_crop_text(None) is None
    assert router._clean_crop_text(42) is None


def test_asking_about_a_crop_we_do_not_grow_says_so(session, ceo) -> None:
    """The reported bug: "how grapes production be increased" answered about paddy.

    Silently widening to the collective is the same failure as answering a guava question
    with a paddy plan — the reader has no way to tell they were answered about something
    else. A named data gap is a real answer; a substituted one is not.
    """
    from agrivardhak.orchestrator.assistant_contracts import IntentPlan

    plan = IntentPlan(
        shape=ResponseShape.DECISION,
        modules=["market"],
        entities={"unknown_crop": "grapes"},
        rationale="",
    )
    answer = chat.answer(
        session,
        scope=ceo,
        request=AssistantRequest(question="how grapes production be increased"),
        plan=plan,
    )
    assert answer.shape is ResponseShape.REFUSE
    assert answer.packet is None, "an unknown crop must not produce a Decision Packet"
    assert "grapes" in (answer.refusal or "")
    # Naming what *is* grown turns a dead end into a next question.
    for crop in ("Paddy", "Guava"):
        assert crop in (answer.refusal or "")
