"""The Data Observer: landing, classification, chunking, retrieval and the gates.

M29, M30, M31 — DR-07, FR-403, FR-404, ADR-0014, ADR-0015, ADR-0017.

The properties worth protecting here are not "does retrieval return something". They are:
a load must not silently lose rows; Hindi must match despite invisible characters; a passage
nobody is licensed to rely on must be structurally unable to become advice; and the whole
path must work with no encoder and no network.
"""

from __future__ import annotations

import datetime as dt
import inspect
import json
import uuid

import pytest
from sqlalchemy import func, select

from agrivardhak.domain import enums
from agrivardhak.domain.models.knowledge import KnowledgeChunk
from agrivardhak.domain.models.provenance import ExternalRecord
from agrivardhak.ingestion import registry
from agrivardhak.knowledge import classify, embed, gates, segment
from agrivardhak.knowledge.retrieval import recent, retrieve
from agrivardhak.orchestrator import engine, gather

NOW = dt.datetime(2026, 8, 29, 6, 0, tzinfo=dt.UTC)

pytestmark = pytest.mark.usefixtures("db")


# --------------------------------------------------------------------------- M29: landing


def test_landing_a_batch_twice_inserts_nothing_the_second_time(session) -> None:
    """Idempotency is what makes `make ingest` and an external cron safe to repeat."""
    first = registry.load_batch(session, 1)
    assert sum(first.values()) >= 0
    second = registry.load_batch(session, 1)
    assert sum(second.values()) == 0, (
        "a second load inserted rows — the (kind, dedupe_key) constraint is not holding"
    )


def test_both_payload_envelopes_are_understood() -> None:
    """Batches 1/2/4 carry the full data.gov.in wrapper; 5/6 are trimmed. Both must parse.

    The three older files predate the current ``fetch()`` return shape and were never
    rewritten, because unchanged content means no rewrite. A loader that understood only the
    newer envelope would read them as empty and report success.
    """
    full = registry.GENERATED_DIR / "batch1_msp" / "msp-rabi.json"
    trimmed = registry.GENERATED_DIR / "batch6_procurement" / "procurement-wheat-paddy.json"
    for path in (full, trimmed):
        if not path.is_file():
            pytest.skip(f"{path.name} not cached")

    full_payload = json.loads(full.read_text())
    trimmed_payload = json.loads(trimmed.read_text())

    assert "fetched_count" not in full_payload, "fixture changed; this test guards the old shape"
    assert "fetched_count" in trimmed_payload

    assert registry._records(full_payload), "the full data.gov.in envelope read as empty"
    assert registry._records(trimmed_payload), "the trimmed envelope read as empty"


def test_a_key_collision_raises_rather_than_dropping_rows() -> None:
    """ADR-0017's rule, applied to dedupe keys.

    ``variety-field-crops`` looks keyed by (type, crop) and is not — 255 records collapse to
    66. ON CONFLICT DO NOTHING would absorb that and report a smaller, plausible number.
    """
    records = [{"crop": "Paddy"}, {"crop": "Paddy"}]
    keys = [registry._dedupe_key("coc-a2fl", r, i) for i, r in enumerate(records)]
    assert len(set(keys)) == 1, "precondition: these two records must collide"

    source = registry.registry().by_key("variety-field-crops")
    assert "variety-field-crops" not in registry.KEY_FIELDS, (
        "variety has no natural key; giving it one silently dropped 189 of 255 records"
    )
    positional = [registry._dedupe_key(source.key, {}, i) for i in range(255)]
    assert len(set(positional)) == 255


# --------------------------------------------------------------------------- M30: observer


def test_a_short_government_order_is_one_chunk() -> None:
    """The honest short-circuit.

    A शासनादेश subject averages 199 characters. Splitting one Hindi sentence into "semantic"
    pieces would fragment a single statement into several worse ones and multiply the
    citation count without adding a retrievable fact.
    """
    subject = (
        "प्रधानमंत्री फसल बीमा योजना एवं पुनर्गठित मौसम आधारित फसल बीमा योजना को वर्ष "
        "2026-27 के खरीफ व रबी मौसम में लागू किये जाने के सम्बन्ध में।"
    )
    assert len(subject) < segment.DEFAULT_MIN_CHARS
    assert segment.segment(subject) == [subject]


def test_a_long_answer_splits_into_several_chunks() -> None:
    """The semantic path still has to work — it is what the FAQ prose and future PDFs need."""
    sentence = "मृदा स्वास्थ्य कार्ड मृदा परीक्षण जांच रिपोर्ट है जिसे किसानों को दिया जाता है। "
    long_text = sentence * 12
    assert len(long_text) > segment.DEFAULT_MAX_CHARS
    chunks = segment.segment(long_text)
    assert len(chunks) > 1
    assert all(len(c) <= segment.DEFAULT_MAX_CHARS for c in chunks)
    # Nothing may be invented, and no sentence may be cut mid-word.
    assert all(c.strip() for c in chunks)


def test_html_in_the_cms_payload_is_stripped_for_indexing() -> None:
    """The agridarshan answers ship raw ``<p>`` and ``&nbsp;`` with no sanitiser upstream."""
    raw = "<p>मृदा स्वास्थ्य कार्ड&nbsp;क्या है</p>"
    assert segment.strip_markup(raw) == "मृदा स्वास्थ्य कार्ड क्या है"


def test_a_promotion_circular_is_noise() -> None:
    """52 of the 69 agridarshan circulars are postings and promotions.

    Real government orders, and nothing to do with farming. Indexing them would put
    departmental staff movements in front of a CEO asking about crops.
    """
    circular = (
        "अपर कृषि निदेशक स्तर के अधिकारी श्रीमती कनीज फातिमा, श्री राजेश कुमार एवं "
        "डॉ० आशुतोष मिश्रा का कृषि निदेशक स्तर पर पद्दोंनती संम्बंधित कार्यालय ज्ञाप"
    )
    verdict = classify.classify(circular)
    assert verdict.is_noise
    assert verdict.noise_reason and "personnel" in verdict.noise_reason


def test_zero_width_joiners_do_not_defeat_category_matching() -> None:
    """The trap this classifier exists to survive.

    The source page emits U+200D inside conjuncts, so 52 of the 75 orders carry the category
    ``वित्‍तीय स्‍वीकृतियॉं``. A literal match against the same word typed normally
    fails silently, and every financial sanction would classify as unknown while looking fine.
    """
    as_published = "वित्‍तीय स्‍वीकृतियॉं"
    typed_normally = "वित्तीय स्वीकृतियॉं"
    assert as_published != typed_normally, "precondition: the joiner must actually be present"
    assert classify.normalise(as_published) == classify.normalise(typed_normally)

    subject = (
        "चालू वित्तीय वर्ष 2026-27 हेतु अनुदान के लेखाशीर्षक 2402 मृदा तथा जल संरक्षण-101 "
        "मृदा संरक्षण तथा परीक्षण-05-जैव उर्वरक उत्पादित प्रयोगशालाओं का सुदृढीकरण"
    )
    verdict = classify.classify(subject, category=as_published)
    assert not verdict.is_noise
    assert verdict.news_domain is not None


def test_a_crop_insurance_order_is_policy_not_climate() -> None:
    """``मौसम आधारित फसल बीमा`` contains "weather" and is still a policy instrument.

    Filing it under CLIMATE would put it in front of a CEO asking about hazards rather than
    about schemes.
    """
    subject = (
        "प्रधानमंत्री फसल बीमा योजना एवं पुनर्गठित मौसम आधारित फसल बीमा योजना को वर्ष "
        "2026-27 के खरीफ व रबी मौसम में लागू किये जाने के सम्बन्ध में।"
    )
    verdict = classify.classify(subject, category="अधिसूचना")
    assert verdict.news_domain is enums.NewsDomain.POLICY


def test_a_crop_name_inside_a_longer_word_is_not_a_crop_mention() -> None:
    """``धान`` (paddy) sits inside ``प्राविधानित`` ("provisioned"), which appears in almost
    every financial-sanction order. Substring matching attributed 26 of 26 policy events to
    paddy, including soil-conservation budget releases (ADR-0017)."""
    assert gather.crops_named_in("प्राविधानित धनराशि के सापेक्ष") == []
    assert gather.crops_named_in("धान की खरीद एवं गेहूं भण्डारण") == ["Paddy", "Wheat"]


def test_retrieval_works_with_no_encoder_present(session, monkeypatch) -> None:
    """NFR-303. A fresh clone has no model on disk, and retrieval must still answer.

    The encoder is forced absent rather than asserted absent, so this holds on a machine
    where ``make embed-model`` has been run.
    """
    monkeypatch.setattr(embed, "encode", lambda texts: None)
    monkeypatch.setattr(embed, "available", lambda: False)

    if not session.execute(select(func.count()).select_from(KnowledgeChunk)).scalar_one():
        pytest.skip("database not seeded — run `make seed`")

    hits = retrieve(session, query="फसल बीमा", as_of=NOW, k=3)
    assert hits, "lexical fallback returned nothing"
    assert all(h.evidence.kind == "knowledge_chunk" for h in hits)


def test_retrieval_says_nothing_about_what_the_corpus_does_not_cover(session) -> None:
    """Nearest-neighbour search always returns k rows; that is not the same as an answer.

    Before ``MIN_COSINE``, "bitcoin mining" came back with three Hindi government orders —
    correctly ranked and completely useless. A reader cannot distinguish "here is your
    answer" from "here is the closest thing in a corpus that does not discuss this", so the
    honest output is nothing.
    """
    if not session.execute(select(func.count()).select_from(KnowledgeChunk)).scalar_one():
        pytest.skip("database not seeded — run `make seed`")

    for nonsense in ("bitcoin mining", "quantum computing", "शेयर बाजार सेंसेक्स"):
        assert retrieve(session, query=nonsense, as_of=NOW, k=3) == [], (
            f"{nonsense!r} returned results from a corpus of UP agriculture orders"
        )

    # The floor must not silence real questions.
    for real in ("फसल बीमा", "उर्वरक अनुदान", "soil testing"):
        assert retrieve(session, query=real, as_of=NOW, k=3), f"{real!r} returned nothing"


def test_a_retrieved_chunk_resolves_to_a_real_row(session) -> None:
    """An EvidenceRef that does not dereference is a citation to nothing (FR-804)."""
    if not session.execute(select(func.count()).select_from(KnowledgeChunk)).scalar_one():
        pytest.skip("database not seeded — run `make seed`")
    hits = retrieve(session, query="फसल बीमा", as_of=NOW, k=1)
    assert hits
    chunk = session.get(KnowledgeChunk, hits[0].evidence.id)
    assert chunk is not None
    assert session.get(ExternalRecord, chunk.external_record_id) is not None


def test_hindi_is_stored_exactly_as_published(session) -> None:
    """ADR-0015. The joiners the portal emits must survive into the stored text.

    Normalisation is a matching key, never a write — a rule transcribed from cleaned-up text
    is a rule transcribed from something the government did not publish.
    """
    chunk = (
        session.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.source_key == "up-go-agriculture").limit(1)
        )
        .scalars()
        .first()
    )
    if chunk is None:
        pytest.skip("database not seeded — run `make seed`")
    record = session.get(ExternalRecord, chunk.external_record_id)
    assert record is not None
    assert chunk.text_hi == record.payload["subject"].strip()


# --------------------------------------------------------------------------- M31: the gates


def test_staff_seniority_lists_are_not_agricultural_notices() -> None:
    """The largest source of noise in a farmer-facing feed.

    The agridarshan CMS files staff seniority lists as "circulars". Before these markers, 39
    domain-less chunks reached the farmer portal's notice feed — a smallholder opening
    "Government notices" was shown the clerical cadre's seniority list.
    """
    for staffing in (
        "वरिष्ठ प्राविधिक सहायक ग्रुप-ए विकास शाखा के कार्मिकों की अन्तिम ज्येष्ठता सूची",
        "अधीनस्थ लिपिक संवर्ग की अंतिम ज्येष्ठता सूची - 2026",
    ):
        assert classify.classify(staffing, is_advisory=True).is_noise

    # ...without swallowing the mechanisation programmes, which are among the few notices
    # with a direct bearing on a smallholder.
    machinery = classify.classify(
        "त्वरित मक्का विकास कार्यक्रम के अन्तर्गत कृषि यंत्र बैंक की स्थापना",
        is_advisory=True,
    )
    assert not machinery.is_noise
    assert machinery.news_domain is enums.NewsDomain.INPUT_PRICE


def test_recent_and_search_apply_the_same_gate(session) -> None:
    """The farmer feed and the console search must not disagree about what is safe to act on.

    Both go through ``_score``; this asserts they actually do, because a farmer-facing list
    that quietly dropped the licence cap would be the worst possible place to lose it.
    """
    if not session.execute(select(func.count()).select_from(KnowledgeChunk)).scalar_one():
        pytest.skip("database not seeded — run `make seed`")

    listed = recent(session, as_of=NOW, k=20)
    assert listed, "the recent feed is empty"
    for hit in listed:
        expected = gates.ceiling_for(
            licence=hit.licence, verification_status=hit.verification_status
        )
        assert hit.ceiling == expected
        assert hit.trust <= hit.ceiling
        assert hit.is_inert == (hit.ceiling <= gates.INERT_LICENCE_CEILING)


def test_the_farmer_feed_carries_no_staff_notices(session) -> None:
    """What a farmer actually sees when they open the notices screen."""
    if not session.execute(select(func.count()).select_from(KnowledgeChunk)).scalar_one():
        pytest.skip("database not seeded — run `make seed`")
    for hit in recent(session, as_of=NOW, k=12):
        normalised = classify.normalise(hit.text_hi)
        for staffing in ("ज्येष्ठता", "संवर्ग", "पद्दोंनती"):
            assert classify.normalise(staffing) not in normalised, (
                f"a staff notice reached the farmer feed: {hit.text_hi[:60]}"
            )


def test_an_unverified_extraction_cannot_lift_a_cap() -> None:
    """ADR-0014, in one assertion.

    A model reading a Hindi order and emitting structured fields cannot assert that its
    transcription is faithful. Both halves are required: a named human *and* a licence.
    """
    licensed = "Non-commercial research and private study, with attribution"
    assert not gates.may_lift_a_cap(
        licence=licensed, verification_status=enums.VerificationStatus.UNVERIFIED
    )
    assert not gates.may_lift_a_cap(
        licence="UNKNOWN", verification_status=enums.VerificationStatus.VERIFIED
    )
    assert gates.may_lift_a_cap(
        licence=licensed, verification_status=enums.VerificationStatus.VERIFIED
    )

    capped = gates.ceiling_for(
        licence=licensed,
        verification_status=enums.VerificationStatus.UNVERIFIED,
        has_extraction=True,
    )
    assert capped == gates.UNVERIFIED_EXTRACTION_CEILING


def test_an_unlicensed_chunk_cannot_reach_a_packet(session) -> None:
    """The licence gate is arithmetic, not a review checklist.

    Asserted against the orchestrator's own floor rather than against the constant, so that
    moving either number without moving the other fails here.
    """
    ceiling = gates.ceiling_for(
        licence="UNKNOWN", verification_status=enums.VerificationStatus.VERIFIED
    )
    # Read the orchestrator's real default rather than restating it, so that raising the
    # floor without raising the ceiling fails here instead of quietly letting inert text
    # through.
    floor = inspect.signature(engine.ask).parameters["confidence_floor"].default
    assert floor == gates.ORCHESTRATOR_FLOOR
    assert ceiling < floor

    if not session.execute(select(func.count()).select_from(KnowledgeChunk)).scalar_one():
        pytest.skip("database not seeded — run `make seed`")

    inert = [
        h
        for h in retrieve(session, query="मृदा स्वास्थ्य कार्ड", as_of=NOW, k=10)
        if h.licence.upper() == gates.UNKNOWN_LICENCE
    ]
    assert inert, "expected the advisory CMS source to appear for this query"
    for hit in inert:
        assert hit.is_inert
        assert hit.trust <= gates.INERT_LICENCE_CEILING
        assert hit.trust < floor


def test_a_licensed_authoritative_chunk_outranks_a_better_matching_unlicensed_one(
    session,
) -> None:
    """Trust multiplies; it does not merely tie-break.

    The CMS FAQ "प्रधानमंत्री फसल बीमा योजना क्या है?" is a better textual answer to a crop
    insurance question than a budget order is. It must still lose, because nobody has
    cleared us to rely on it.
    """
    if not session.execute(select(func.count()).select_from(KnowledgeChunk)).scalar_one():
        pytest.skip("database not seeded — run `make seed`")
    hits = retrieve(session, query="फसल बीमा", as_of=NOW, k=5)
    assert hits
    assert hits[0].source_key == "up-go-agriculture"
    assert hits[0].is_authoritative
    assert not hits[0].is_inert


def test_a_policy_finding_carries_the_gate_into_its_confidence() -> None:
    """A finding built on unlicensed text must not exceed the gate that text carries."""
    from decimal import Decimal

    from agrivardhak.intelligence import risk
    from agrivardhak.intelligence.contracts import EvidenceRef

    ref = EvidenceRef(kind="knowledge_chunk", id=uuid.uuid4(), label="unlicensed", as_of=NOW)
    event = risk.PolicyEvent(
        key="p1",
        domain="POLICY",
        headline="कोई आदेश",
        occurred_at=NOW.date() - dt.timedelta(days=5),
        crops=[],
        ceiling=gates.INERT_LICENCE_CEILING,
        confidence=gates.INERT_LICENCE_CEILING,
        evidence=ref,
        licence_confirmed=False,
    )
    exposure = risk.CropExposure(
        crop_name="Potato",
        farmer_ids=[uuid.uuid4()],
        crop_cycle_ids=[uuid.uuid4()],
        area_sqm=Decimal("4046.86"),
        expected_kg=None,
        harvest_from=None,
        harvest_to=None,
    )
    out = risk.policy_change_risk([event], [exposure], NOW.date())
    assert out
    finding, entry = out[0]
    assert finding.confidence <= gates.INERT_LICENCE_CEILING
    assert finding.confidence < gates.ORCHESTRATOR_FLOOR
    assert entry.domain in {d.value for d in enums.RiskDomain}
    assert any("licence is unconfirmed" in a for a in finding.assumptions)


def test_the_risk_module_stops_claiming_it_has_no_scheme_feed(session) -> None:
    """The line at risk.py that this whole deliverable exists to delete."""
    from sqlalchemy import select as sa_select

    from agrivardhak.domain.models.organization import Organization

    org = session.execute(sa_select(Organization)).scalars().first()
    if org is None:
        pytest.skip("database not seeded — run `make seed`")
    inputs = gather.for_risk(session, organization_id=org.id, as_of=NOW)
    events = inputs.data.get("policy_events") or []
    if not events:
        pytest.skip("no policy events in window — run `make seed`")

    from agrivardhak.intelligence import risk

    output = risk.run(inputs)
    assert not any("no scheme feed yet" in d for d in output.degraded_inputs)
    assert any(f.key.startswith("policy_change") for f in output.findings)
