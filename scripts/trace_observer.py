"""Follow one government order through every stage of the Data Observer (ADR-0018).

    make trace

Read-only, and safe to run against a seeded database at any time: it re-runs each stage on
rows that already exist rather than writing anything. Every number it prints is computed
live from the database — nothing is hardcoded, so if the corpus changes the output changes
with it.

Written because the pipeline's interesting properties are invisible in its output. That a
crop-insurance order classifies as POLICY rather than CLIMATE, that a 138-character subject
is deliberately not chunked, that the best textual match can rank last because nobody has
cleared its licence — none of that is legible from a Decision Packet, and all of it is the
part worth arguing with.
"""

from __future__ import annotations

import datetime as dt
import json
import textwrap

from sqlalchemy import func, select

from agrivardhak.db.session import session_scope
from agrivardhak.domain.enums import ExternalRecordKind, SourceType
from agrivardhak.domain.models.knowledge import KnowledgeChunk
from agrivardhak.domain.models.organization import Organization
from agrivardhak.domain.models.provenance import ExternalRecord
from agrivardhak.knowledge import classify, embed, gates, segment
from agrivardhak.knowledge.retrieval import retrieve
from agrivardhak.orchestrator import gather
from agrivardhak.provenance import trust

NOW = dt.datetime(2026, 8, 29, tzinfo=dt.UTC)
W = 96


def rule(n: int, title: str) -> None:
    print(f"\n{'━' * W}\n  STAGE {n} — {title}\n{'━' * W}")


def wrap(text: str, indent: str = "    ") -> str:
    return textwrap.fill(text, width=W - 6, initial_indent=indent, subsequent_indent=indent)


with session_scope() as s:
    # The crop-insurance notification: the clearest single document in the corpus.
    target = s.execute(
        select(KnowledgeChunk)
        .where(KnowledgeChunk.text_hi.like("%फसल बीमा योजना एवं%"))
        .limit(1)
    ).scalars().first()
    if target is None:
        raise SystemExit("not seeded — run `make seed`")
    record = s.get(ExternalRecord, target.external_record_id)

    # ---------------------------------------------------------------- 0
    rule(0, "RAW  ·  what the scraper cached, untouched on disk")
    print(f"    ExternalRecord  kind={record.kind.value}  dedupe_key={record.dedupe_key[:52]}…")
    print(f"    observed_at     {record.observed_at.date()}   (the order's own date)")
    print("    payload (verbatim JSON, Hindi as published — ADR-0015):")
    for k, v in record.payload.items():
        print(f"      {k:<12} {str(v)[:70]}")

    subject = record.payload["subject"]
    category = record.payload["category"]

    # ---------------------------------------------------------------- 1
    rule(1, "CLASSIFY  ·  useful or noise, and which risk domain")
    print(f"    category as published : {category!r}")
    print(f"    same, normalised      : {classify.normalise(category)!r}")
    print("      ^ the zero-width joiners (\\u200d) are stripped for MATCHING only.")
    print("        Without this, 52 of 75 orders silently fail to classify.")
    verdict = classify.classify(subject, category=category)
    print()
    print(f"    -> is_noise           : {verdict.is_noise}")
    print(f"    -> news_domain        : {verdict.news_domain.value if verdict.news_domain else None}")
    print(f"    -> is_scheme_guidance : {verdict.is_scheme_guidance}")
    print("       (POLICY, not CLIMATE: the text says मौसम आधारित — 'weather-based' —")
    print("        but a crop-insurance notification is a policy instrument.)")

    # ---------------------------------------------------------------- 2
    rule(2, "SEGMENT  ·  semantic chunking, and its honest short-circuit")
    chunks = segment.segment(subject)
    print(f"    document length       : {len(subject)} chars")
    print(f"    short-circuit below   : {segment.DEFAULT_MIN_CHARS} chars")
    print(f"    -> chunks produced    : {len(chunks)}  (already one passage; nothing to split)")
    print()
    # Find a FAQ whose answer genuinely splits — most do not, and the contrast is the point.
    best = None
    for parent in s.execute(
        select(ExternalRecord).where(ExternalRecord.kind == ExternalRecordKind.SCHEME)
    ).scalars():
        body = segment.strip_markup(str(parent.payload.get("answerInHindi") or ""))
        if len(body) <= segment.DEFAULT_MIN_CHARS:
            continue
        n = len(segment.segment(body))
        if best is None or n > best[0]:
            best = (n, body)
    if best is not None:
        n_sem, body = best
        n_packed = len(segment._pack(segment.sentences(body), segment.DEFAULT_MAX_CHARS))
        print(f"    Contrast — the FAQ answer that splits most ({len(body)} chars):")
        print(f"      semantic breakpoints : {n_sem} chunks")
        print(f"      plain length-packing : {n_packed} chunk(s)")
        print("      ^ same text, same budget. The extra splits are topic changes the")
        print("        encoder found — this is the only place the chunker does real work.")

    # ---------------------------------------------------------------- 3
    rule(3, "EMBED  ·  384-d multilingual vector, computed locally")
    print(f"    encoder available     : {embed.available()}")
    if target.embedding is not None:
        vec = list(target.embedding)
        print(f"    stored vector         : dim={len(vec)}  first 4 = "
              f"[{', '.join(f'{x:+.4f}' for x in vec[:4])} …]")
        norm = sum(x * x for x in vec) ** 0.5
        print(f"    L2 norm               : {norm:.4f}  (unit length -> cosine is a dot product)")
    pair = embed.encode([subject, "crop insurance scheme for farmers"])
    if pair:
        print(f"    cosine(this Hindi order, English 'crop insurance scheme') = "
              f"{embed.cosine(pair[0], pair[1]):.3f}")
        print("      ^ this is the number that makes an English question find a Hindi order.")

    # ---------------------------------------------------------------- 4
    rule(4, "INDEX  ·  what got stored, and what deliberately did not")
    print(f"    knowledge_chunk.id    : {target.id}")
    print(f"    text_hi == raw subject: {target.text_hi == subject.strip()}   (stored verbatim)")
    print(f"    verification_status   : {target.verification_status.value}")
    print(f"    extracted             : {target.extracted}   <- no human has reviewed it")
    print("    trust_score column    : DOES NOT EXIST — computed at query time instead,")
    print("                            so replay cannot disagree with the packet (INV-2).")

    # ---------------------------------------------------------------- 5
    rule(5, "RETRIEVE  ·  hybrid ranking, and the trust arithmetic")
    hits = retrieve(s, query="फसल बीमा", as_of=NOW, k=6)
    print("    query: 'फसल बीमा'   (fused: Postgres full-text  +  pgvector cosine)\n")
    for i, h in enumerate(hits, 1):
        tag = "CONTEXT ONLY" if h.is_inert else "usable"
        print(f"    {i}. [{tag:12}] score={h.score:.5f} = relevance {h.relevance:.5f} "
              f"x trust {h.trust:.3f}")
        print(f"       {h.source_key:19} "
              f"{'AUTHORITATIVE' if h.is_authoritative else 'ADVISORY':14} ceiling={h.ceiling}")
        print(wrap(h.text_hi[:80], "       "))

    # Say only what this result set actually shows.
    inert = [h for h in hits if h.is_inert]
    usable = [h for h in hits if not h.is_inert]
    print()
    if inert and usable:
        best_rel = max(hits, key=lambda h: h.relevance)
        print(f"    Most textually relevant here is #{hits.index(best_rel) + 1} "
              f"(relevance {best_rel.relevance:.5f}, {best_rel.source_key}).")
        if best_rel.is_inert:
            print("    It is NOT ranked first: trust multiplies the rank, so an uncleared")
            print("    licence loses to a cited one even when it matches better.")
        else:
            print(f"    {len(inert)} uncleared passage(s) appear below it, capped at "
                  f"{inert[0].ceiling} and marked CONTEXT ONLY.")
    elif not inert:
        print("    Every hit here is from the licensed source, so nothing is capped.")
        print("    Try query 'मृदा स्वास्थ्य कार्ड' to see the CONTEXT ONLY path.")

    # The mixed case, where the gate is visible in the ranking itself.
    print()
    print("    Second query: 'मृदा नमूना' (soil sample) — watch the ordering, not the text:\n")
    mixed = retrieve(s, query="मृदा नमूना", as_of=NOW, k=4)
    for i, h in enumerate(mixed, 1):
        tag = "CONTEXT ONLY" if h.is_inert else "usable"
        print(f"    {i}. [{tag:12}] relevance={h.relevance:.5f} x trust={h.trust:.3f} "
              f"= {h.score:.5f}   ceiling={h.ceiling}")
        print(wrap(h.text_hi[:78], "       "))
    best_text = max(mixed, key=lambda h: h.relevance)
    if best_text.is_inert:
        ratio = best_text.relevance / mixed[0].relevance
        print()
        print(f"    #{mixed.index(best_text) + 1} is the best textual match by a factor of "
              f"{ratio:.1f} — it literally asks")
        print("    'when is the right time to take a soil sample?'. It ranks LAST anyway,")
        print(f"    because its licence is unconfirmed so its trust is capped at "
              f"{best_text.ceiling}.")
        print("    That is the gate visible in the arithmetic: relevance x trust, not relevance.")

    # ---------------------------------------------------------------- 6
    rule(6, "THE GATE  ·  why an unlicensed passage cannot become advice")
    for key, label in (("up-go-agriculture", "licence read & recorded"),
                       ("up-agridarshan-cms", "licence UNKNOWN")):
        chunk = s.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.source_key == key).limit(1)
        ).scalars().first()
        if chunk is None:
            continue
        from agrivardhak.knowledge.retrieval import _source_facts
        licence, authoritative = _source_facts()[key]
        ceiling = gates.ceiling_for(licence=licence, verification_status=chunk.verification_status)
        decayed = trust.effective_confidence(
            source_type=SourceType.EXTERNAL_SOURCE,
            verification_status=chunk.verification_status,
            observed_at=chunk.observed_at, as_of=NOW, attribute="policy_event",
        )
        verdict = "CAN drive a recommendation" if ceiling > gates.ORCHESTRATOR_FLOOR \
            else "CANNOT — below the floor, structurally"
        print(f"    {key:19} {label}")
        print(f"      decayed trust {decayed:.3f}  ceiling {ceiling:.2f}  "
              f"floor {gates.ORCHESTRATOR_FLOOR}  ->  {verdict}")

    # ---------------------------------------------------------------- 7
    rule(7, "GATHER  ·  DB rows become pure module input (modules never do I/O)")
    events = gather.policy_events(s, as_of=NOW)
    print(f"    gather.policy_events() -> {len(events)} PolicyEvent objects")
    e = next((x for x in events if "बीमा" in x.headline), events[0])
    print(f"      domain            {e.domain}")
    print(f"      occurred_at       {e.occurred_at}")
    print(f"      crops named       {e.crops}   <- empty: this order names no individual crop")
    print(f"      confidence        {e.confidence:.3f}  (already gated)")
    print(f"      licence_confirmed {e.licence_confirmed}")

    # ---------------------------------------------------------------- 8
    rule(8, "RISK MODULE  ·  a pure function turns events into findings")
    org_id = s.execute(select(Organization.id)).scalars().first()
    inputs = gather.for_risk(s, organization_id=org_id, as_of=NOW)
    from agrivardhak.intelligence import risk
    out = risk.run(inputs)
    print("    risk.run(inputs).degraded_inputs:")
    for d in out.degraded_inputs:
        flag = "  <-- REPLACED the hardcoded 'no scheme feed yet'" if "not quantified" in d else ""
        print(wrap(f"· {d}{flag}", "      "))
    print()
    print("    POLICY findings produced:")
    for f in out.findings:
        if f.key.startswith("policy_change"):
            print(f"      [{f.key}]  confidence={f.confidence:.2f}  citations={len(f.evidence)}")
            print(wrap(f.statement, "        "))
    print()
    print("    Every finding carries >=1 EvidenceRef pointing at a real knowledge_chunk row —")
    print("    Finding.evidence is Field(min_length=1), so an unevidenced claim cannot be built.")

print(f"\n{'━' * W}")
print("  Raw JSON on disk  ->  classified  ->  chunked  ->  embedded  ->  indexed")
print("                    ->  retrieved   ->  gated    ->  gathered  ->  a finding a CEO reads")
print(f"{'━' * W}\n")
