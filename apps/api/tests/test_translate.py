"""Page translation — UI-11, NFR-304, NFR-505, ADR-0023.

What is worth protecting:
- a string over Sarvam's 2,000-character limit is split, never rejected;
- the response has the same length and order as the request, whatever failed;
- memory is consulted before Sarvam, and a human row is never overwritten by a machine one;
- anonymous callers cannot spend unbounded provider calls;
- no key, a 5xx, or the offline switch leaves the source text in place.

The Sarvam HTTP boundary is replaced with ``httpx.MockTransport``; nothing here touches the
network. Tests that need Postgres skip without it, like the rest of the suite.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from agrivardhak.api import translate as translate_api
from agrivardhak.api.main import app
from agrivardhak.config import get_settings
from agrivardhak.db.session import get_session
from agrivardhak.domain.models.translation import TranslationMemory
from agrivardhak.translation import glossary, sarvam, service

# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    s = get_settings()
    monkeypatch.setattr(s, "sarvam_api_key", "test-key")
    monkeypatch.setattr(s, "use_fixtures", False)
    monkeypatch.setattr(sarvam, "_BACKOFF_SECONDS", (0.0, 0.0))
    yield s


def fake_sarvam(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[dict[str, object]], httpx.Response]
) -> list[dict[str, object]]:
    """Route every Sarvam call through ``handler``; return the list of request bodies seen."""
    seen: list[dict[str, object]] = []

    def transport(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        assert request.headers["api-subscription-key"] == "test-key"
        return handler(body)

    real_client = httpx.Client

    def client_factory(*args: object, **kwargs: object) -> httpx.Client:
        kwargs["transport"] = httpx.MockTransport(transport)
        return real_client(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sarvam.httpx, "Client", client_factory)
    return seen


def echo_hindi(body: dict[str, object]) -> httpx.Response:
    return httpx.Response(200, json={"translated_text": f"हिन्दी अनुवाद:{body['input']}"})


class MemoryStub:
    """Stands in for the translation_memory table in the tests that do not need Postgres."""

    def __init__(self, rows: dict[tuple[str, str, str], str] | None = None) -> None:
        self.rows = dict(rows or {})
        self.stored: list[tuple[str, str, service.Pair, str]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def lookup(_s: object, source: str, target: str, texts: list[str]) -> dict[str, str]:
            return {
                t: self.rows[(source, target, t)] for t in texts if (source, target, t) in self.rows
            }

        def store(
            _s: object, source: str, target: str, pairs: list[service.Pair], **kw: object
        ) -> None:
            for pair in pairs:
                self.stored.append((source, target, pair, str(kw["origin"])))

        monkeypatch.setattr(service, "lookup", lookup)
        monkeypatch.setattr(service, "store", store)


class NullSession:
    def commit(self) -> None: ...

    def rollback(self) -> None: ...


# --------------------------------------------------------------------------- pure pieces


def test_short_text_is_one_piece() -> None:
    assert sarvam.split("Crop health") == ["Crop health"]


def test_long_text_splits_at_sentence_ends_including_the_danda() -> None:
    sentence_hi = "यह विभाग की सामान्य जानकारी है। "
    sentence_en = "This is general guidance from the department. "
    text = (sentence_hi + sentence_en) * 60
    pieces = sarvam.split(text, limit=500)

    assert all(len(p) <= 500 for p in pieces)
    assert len(pieces) > 1
    # Every break falls after a sentence end, so no sentence is cut in half.
    assert all(p.rstrip().endswith(("।", ".")) for p in pieces[:-1])
    assert " ".join(pieces).split() == text.split()


def test_a_single_sentence_longer_than_the_limit_is_cut_at_a_space() -> None:
    text = "word " * 1000
    pieces = sarvam.split(text.strip(), limit=2000)
    assert all(len(p) <= 2000 for p in pieces)
    assert all(not p.startswith(" ") and "wor d" not in p for p in pieces)


def test_detect_reads_the_script_and_ignores_numbers() -> None:
    assert service.detect("My crops") == "en-IN"
    assert service.detect("मेरी फ़सल") == "hi-IN"
    assert service.detect("82% · 12.5") is None
    # A Hindi sentence naming the product is still Hindi.
    assert service.detect("AgriVardhak सुझाव देता है।") == "hi-IN"


def test_normalise_collapses_whitespace_for_hashing() -> None:
    assert service.content_hash("  My\n   crops ") == service.content_hash("My crops")


# --------------------------------------------------------------------------- Sarvam client


def test_a_retryable_error_is_retried_then_succeeds(settings, monkeypatch) -> None:
    calls = {"n": 0}

    def flaky(body: dict[str, object]) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429) if calls["n"] == 1 else echo_hindi(body)

    fake_sarvam(monkeypatch, flaky)
    assert sarvam.translate_many(["Seed"], "en-IN", "hi-IN") == {"Seed": "हिन्दी अनुवाद:Seed"}
    assert calls["n"] == 2


def test_a_rejected_request_is_not_retried_and_yields_nothing(settings, monkeypatch) -> None:
    seen = fake_sarvam(monkeypatch, lambda _b: httpx.Response(400, json={"error": "bad"}))
    assert sarvam.translate_many(["Seed"], "en-IN", "hi-IN") == {}
    assert len(seen) == 1


def test_international_numerals_are_requested(settings, monkeypatch) -> None:
    seen = fake_sarvam(monkeypatch, echo_hindi)
    sarvam.translate_many(["Harvest on 12 October"], "en-IN", "hi-IN")
    assert seen[0]["numerals_format"] == "international"
    assert seen[0]["model"] == get_settings().sarvam_translate_model


def test_offline_switch_makes_no_call(settings, monkeypatch) -> None:
    monkeypatch.setattr(settings, "use_fixtures", True)
    seen = fake_sarvam(monkeypatch, echo_hindi)
    assert sarvam.translate_many(["Seed"], "en-IN", "hi-IN") == {}
    assert seen == []


# --------------------------------------------------------------------------- service


def test_response_keeps_order_and_length_and_deduplicates(settings, monkeypatch) -> None:
    MemoryStub().install(monkeypatch)
    seen = fake_sarvam(monkeypatch, echo_hindi)

    result = service.translate(
        NullSession(),  # type: ignore[arg-type]
        ["Seed", "मेरी फ़सल", "Seed", "42", "Market"],
        "hi-IN",
        machine_budget=None,
    )

    assert result.translations == [
        "हिन्दी अनुवाद:Seed",
        "मेरी फ़सल",
        "हिन्दी अनुवाद:Seed",
        "42",
        "हिन्दी अनुवाद:Market",
    ]
    # "Seed" once, "Market" once; Hindi and numbers never leave the process.
    assert sorted(b["input"] for b in seen) == ["Market", "Seed"]
    assert result.machine_calls == 2


def test_memory_hits_skip_sarvam(settings, monkeypatch) -> None:
    MemoryStub({("en-IN", "hi-IN", "Seed"): "बीज"}).install(monkeypatch)
    seen = fake_sarvam(monkeypatch, echo_hindi)

    result = service.translate(NullSession(), ["Seed"], "hi-IN", machine_budget=None)  # type: ignore[arg-type]

    assert result.translations == ["बीज"]
    assert seen == []


def test_hindi_to_english_uses_hindi_as_the_source(settings, monkeypatch) -> None:
    MemoryStub().install(monkeypatch)
    seen = fake_sarvam(
        monkeypatch, lambda b: httpx.Response(200, json={"translated_text": "Crop insurance"})
    )
    result = service.translate(NullSession(), ["फसल बीमा"], "en-IN", machine_budget=None)  # type: ignore[arg-type]
    assert result.translations == ["Crop insurance"]
    assert seen[0]["source_language_code"] == "hi-IN"
    assert seen[0]["target_language_code"] == "en-IN"


def test_machine_results_are_stored_as_machine(settings, monkeypatch) -> None:
    memory = MemoryStub()
    memory.install(monkeypatch)
    fake_sarvam(monkeypatch, echo_hindi)
    service.translate(NullSession(), ["Seed"], "hi-IN", machine_budget=None)  # type: ignore[arg-type]
    assert [(s, t, p.translated, o) for s, t, p, o in memory.stored] == [
        ("en-IN", "hi-IN", "हिन्दी अनुवाद:Seed", "MACHINE")
    ]


def test_budget_caps_provider_calls_and_the_rest_come_back_as_source(settings, monkeypatch) -> None:
    MemoryStub().install(monkeypatch)
    seen = fake_sarvam(monkeypatch, echo_hindi)
    result = service.translate(
        NullSession(),
        ["Alpha", "Beta", "Gamma"],
        "hi-IN",
        machine_budget=1,  # type: ignore[arg-type]
    )
    assert len(seen) == 1
    assert result.machine_calls == 1
    assert sum(t.startswith("हिन्दी अनुवाद:") for t in result.translations) == 1


def test_no_key_returns_source_text(settings, monkeypatch) -> None:
    monkeypatch.setattr(settings, "sarvam_api_key", None)
    MemoryStub().install(monkeypatch)
    seen = fake_sarvam(monkeypatch, echo_hindi)
    result = service.translate(NullSession(), ["Seed"], "hi-IN", machine_budget=None)  # type: ignore[arg-type]
    assert result.translations == ["Seed"]
    assert result.machine_calls == 0
    assert seen == []


def test_a_5xx_that_never_recovers_returns_source_text(settings, monkeypatch) -> None:
    MemoryStub().install(monkeypatch)
    fake_sarvam(monkeypatch, lambda _b: httpx.Response(503))
    result = service.translate(NullSession(), ["Seed"], "hi-IN", machine_budget=None)  # type: ignore[arg-type]
    assert result.translations == ["Seed"]


# --------------------------------------------------------------------------- endpoint


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: NullSession()
    yield TestClient(app)
    app.dependency_overrides.pop(get_session, None)


def test_endpoint_refuses_requests_over_the_caps(client, settings, monkeypatch) -> None:
    monkeypatch.setattr(settings, "translate_max_texts_per_request", 2)
    response = client.post("/api/v1/translate", json={"target": "hi-IN", "texts": ["a", "b", "c"]})
    assert response.status_code == 413

    monkeypatch.setattr(settings, "translate_max_texts_per_request", 100)
    monkeypatch.setattr(settings, "translate_max_chars_per_request", 10)
    response = client.post("/api/v1/translate", json={"target": "hi-IN", "texts": ["x" * 11]})
    assert response.status_code == 413


def test_endpoint_rejects_an_unsupported_language(client) -> None:
    response = client.post("/api/v1/translate", json={"target": "fr-FR", "texts": ["Seed"]})
    assert response.status_code == 422


def test_anonymous_callers_share_a_bounded_budget(client, settings, monkeypatch) -> None:
    MemoryStub().install(monkeypatch)
    seen = fake_sarvam(monkeypatch, echo_hindi)
    monkeypatch.setattr(settings, "translate_anonymous_budget_per_hour", 2)
    monkeypatch.setattr(translate_api, "anonymous_budget", translate_api._SharedBudget())

    first = client.post(
        "/api/v1/translate", json={"target": "hi-IN", "texts": ["One", "Two", "Three"]}
    )
    second = client.post("/api/v1/translate", json={"target": "hi-IN", "texts": ["Four"]})

    assert first.status_code == 200 and second.status_code == 200
    assert len(seen) == 2
    assert second.json()["translations"] == ["Four"]


def test_an_invalid_token_is_anonymous_not_401(client, settings, monkeypatch) -> None:
    MemoryStub().install(monkeypatch)
    fake_sarvam(monkeypatch, echo_hindi)
    response = client.post(
        "/api/v1/translate",
        json={"target": "hi-IN", "texts": ["Seed"]},
        headers={"Authorization": "Bearer not-a-token"},
    )
    assert response.status_code == 200


def test_budget_refunds_what_was_not_spent() -> None:
    budget = translate_api._SharedBudget()
    assert budget.take(5, per_hour=5) == 5
    budget.refund(3)
    assert budget.take(5, per_hour=5) == 3


# --------------------------------------------------------------------------- Postgres


@pytest.mark.usefixtures("db")
def test_machine_write_never_overwrites_a_human_row(session: Session) -> None:
    service.seed_human(session, [("Crop health", "फ़सल की स्थिति")])
    service.store(
        session,
        "en-IN",
        "hi-IN",
        [service.Pair("Crop health", "फसल स्वास्थ्य")],
        origin="MACHINE",
        provider="sarvam",
        model="sarvam-translate:v1",
    )
    session.flush()
    row = session.execute(
        select(TranslationMemory).where(
            TranslationMemory.source_hash == service.content_hash("Crop health"),
            TranslationMemory.target_lang == "hi-IN",
        )
    ).scalar_one()
    assert (row.origin, row.translated_text) == ("HUMAN", "फ़सल की स्थिति")


@pytest.mark.usefixtures("db")
def test_human_seed_writes_both_directions_and_lookup_finds_them(session: Session) -> None:
    service.seed_human(session, [("Sign in", "साइन इन करें")])
    session.flush()
    assert service.lookup(session, "en-IN", "hi-IN", ["Sign in"]) == {"Sign in": "साइन इन करें"}
    assert service.lookup(session, "hi-IN", "en-IN", ["साइन इन करें"]) == {"साइन इन करें": "Sign in"}


@pytest.mark.usefixtures("db")
def test_a_machine_row_is_refreshed_by_a_later_machine_write(session: Session) -> None:
    for text in ("पहला", "दूसरा"):
        service.store(
            session,
            "en-IN",
            "hi-IN",
            [service.Pair("Refresh me", text)],
            origin="MACHINE",
            provider="sarvam",
            model="sarvam-translate:v1",
        )
    session.flush()
    assert service.lookup(session, "en-IN", "hi-IN", ["Refresh me"]) == {"Refresh me": "दूसरा"}


def test_the_static_dictionary_loads(tmp_path) -> None:
    from agrivardhak.translation.__main__ import STRINGS, load_entries

    entries = load_entries(STRINGS)
    assert len(entries) >= 60
    assert ("Sign in", "साइन इन करें") in entries


@pytest.mark.usefixtures("db")
def test_when_two_entries_share_a_translation_the_first_wins_like_the_browser(
    session: Session,
) -> None:
    service.seed_human(session, [("Notices", "सूचनाएँ"), ("notices", "सूचनाएँ")])
    session.flush()
    assert service.lookup(session, "hi-IN", "en-IN", ["सूचनाएँ"]) == {"सूचनाएँ": "Notices"}


# --------------------------------------------------------------------------- number guard


def test_if_numbers_cannot_be_kept_the_source_stands_unresolved(settings, monkeypatch) -> None:
    """The whole string loses its number, and the fragment retry fails: show the source."""
    memory = MemoryStub()
    memory.install(monkeypatch)

    def model(body: dict[str, object]) -> httpx.Response:
        if body["input"] == "Given 205 kg of seed":
            return httpx.Response(200, json={"translated_text": "बीस किलो बीज दिया"})
        return httpx.Response(503)

    fake_sarvam(monkeypatch, model)
    result = service.translate(
        NullSession(),  # type: ignore[arg-type]
        ["Given 205 kg of seed"],
        "hi-IN",
        machine_budget=None,
    )
    assert result.translations == ["Given 205 kg of seed"]
    assert result.resolved == [False]
    assert memory.stored == []


def test_resolved_distinguishes_no_translation_needed_from_failure(settings, monkeypatch) -> None:
    MemoryStub().install(monkeypatch)
    fake_sarvam(monkeypatch, lambda _b: httpx.Response(503))
    result = service.translate(
        NullSession(),  # type: ignore[arg-type]
        ["मेरी फ़सल", "42", "Seed"],
        "hi-IN",
        machine_budget=None,
    )
    assert result.resolved == [True, True, False]


def test_numbers_kept() -> None:
    assert service.numbers_kept("Harvest 4.2 t from 2.5 acres", "2.5 एकड़ से 4.2 टन")
    assert not service.numbers_kept("205 kg", "बीस किलो")


def test_fallback_translates_words_glued_to_numbers(settings, monkeypatch) -> None:
    """Order titles glue words to numbers: "संख्या-11", "2401-फसल". None of it may stay Hindi."""
    MemoryStub().install(monkeypatch)
    words = {"अनुदान संख्या-": "grant number-", "-फसल": "-crop"}

    def model(body: dict[str, object]) -> httpx.Response:
        text = str(body["input"])
        if text in words:
            return httpx.Response(200, json={"translated_text": words[text]})
        return httpx.Response(200, json={"translated_text": "grant number eleven, crop"})

    fake_sarvam(monkeypatch, model)
    result = service.translate(
        NullSession(),  # type: ignore[arg-type]
        ["अनुदान संख्या-11 2401-फसल"],
        "en-IN",
        machine_budget=None,
    )
    assert result.translations == ["grant number-11 2401-crop"]
    assert service.detect(result.translations[0]) == "en-IN"


def test_a_memory_row_still_in_the_source_language_is_not_served(settings, monkeypatch) -> None:
    MemoryStub({("hi-IN", "en-IN", "अनुदान संख्या-11"): "In grant संख्या-11"}).install(monkeypatch)
    fake_sarvam(
        monkeypatch, lambda _b: httpx.Response(200, json={"translated_text": "Grant number-11"})
    )
    result = service.translate(NullSession(), ["अनुदान संख्या-11"], "en-IN", machine_budget=None)  # type: ignore[arg-type]
    assert result.translations == ["Grant number-11"]


def test_retry_after_is_honoured_and_capped(monkeypatch) -> None:
    waits: list[float] = []
    monkeypatch.setattr(sarvam.time, "sleep", waits.append)
    monkeypatch.setattr(sarvam, "_BACKOFF_SECONDS", (1.0, 2.0))
    assert sarvam._retry_delay(httpx.Response(429, headers={"Retry-After": "3"}), 1.0) == 3.0
    assert sarvam._retry_delay(httpx.Response(429, headers={"Retry-After": "600"}), 1.0) == 10.0
    assert sarvam._retry_delay(httpx.Response(429, headers={"Retry-After": "soon"}), 2.0) == 2.0
    assert sarvam._retry_delay(None, 4.0) == 4.0


def test_calls_share_one_process_wide_ceiling(settings, monkeypatch) -> None:
    """Concurrency is bounded across requests, not per request — Sarvam limits the key."""
    import threading

    peak = {"now": 0, "max": 0}
    lock = threading.Lock()

    def slow(body: dict[str, object]) -> httpx.Response:
        with lock:
            peak["now"] += 1
            peak["max"] = max(peak["max"], peak["now"])
        threading.Event().wait(0.02)
        with lock:
            peak["now"] -= 1
        return echo_hindi(body)

    fake_sarvam(monkeypatch, slow)
    batches = [[f"Seed lot {c}{i}" for i in range(6)] for c in "abc"]
    threads = [
        threading.Thread(target=sarvam.translate_many, args=(b, "en-IN", "hi-IN")) for b in batches
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert 1 < peak["max"] <= sarvam.MAX_PARALLEL


def test_a_translation_that_changes_a_number_is_rebuilt_around_the_numbers(
    settings, monkeypatch
) -> None:
    """Measured 2026-09-17: mayura:v1 rendered "205 kg" as "बीस किलो" (twenty kg)."""
    MemoryStub().install(monkeypatch)
    replies = {
        "Given 205 bags of seed": "बीस बोरी बीज दिया",
        "Given": "दिया",
        "bags of seed": "बोरी बीज",
    }

    def model(body: dict[str, object]) -> httpx.Response:
        return httpx.Response(200, json={"translated_text": replies[str(body["input"])]})

    seen = fake_sarvam(monkeypatch, model)
    result = service.translate(
        NullSession(),  # type: ignore[arg-type]
        ["Given 205 bags of seed"],
        "hi-IN",
        machine_budget=None,
    )

    assert result.translations == ["दिया 205 बोरी बीज"]
    assert result.resolved == [True]
    assert [b["input"] for b in seen] == ["Given 205 bags of seed", "Given", "bags of seed"]


def test_a_bad_memory_row_is_ignored_and_replaced(settings, monkeypatch) -> None:
    MemoryStub({("en-IN", "hi-IN", "Potato yield 13.8"): "आलू तेरह"}).install(monkeypatch)
    fake_sarvam(
        monkeypatch, lambda b: httpx.Response(200, json={"translated_text": "[T1] उपज 13.8"})
    )
    result = service.translate(
        NullSession(),  # type: ignore[arg-type]
        ["Potato yield 13.8"],
        "hi-IN",
        machine_budget=None,
    )
    assert result.translations == ["आलू उपज 13.8"]


def test_english_output_with_hindi_left_in_it_is_rejected_hindi_with_latin_is_not() -> None:
    order = "अनुदान संख्या-11 के लेखाशीर्षक 2401-फसल कृषि कर्म"
    assert not service.acceptable(order, "In grant संख्या-11 Title 2401-फसल Krishi कर्म", "en-IN")
    assert service.acceptable(order, "Grant number 11, account head 2401 crop farming", "en-IN")
    assert service.acceptable("Apply 50 kg of DAP", "50 किलोग्राम DAP डालें", "hi-IN")


# --------------------------------------------------------------------------- glossary


def test_units_and_terms_alone_resolve_without_the_model(settings, monkeypatch) -> None:
    """ac/t/kg are fixed: "13.8 t" once became kilograms, "ac" became "ए.सी.". No API call."""
    MemoryStub().install(monkeypatch)
    seen = fake_sarvam(monkeypatch, echo_hindi)
    result = service.translate(
        NullSession(),  # type: ignore[arg-type]
        ["1.48 ac", "ac", "13.8 t", "205 kg", "FPO", "Paddy 1,832 ac, Guava 9 ac", "5 bx"],
        "hi-IN",
        machine_budget=None,
    )
    assert result.translations == [
        "1.48 एकड़",
        "एकड़",
        "13.8 टन",
        "205 किलोग्राम",
        "किसान उत्पादक संगठन",
        "धान 1,832 एकड़, अमरूद 9 एकड़",
        "5 bx",  # a unit the glossary does not know: left as written, never guessed
    ]
    assert all(result.resolved)
    assert seen == []


def test_fpo_ceo_is_never_left_to_the_model(settings, monkeypatch) -> None:
    """Sarvam rendered "FPO CEO" as "महिला आरक्षण आयोग की अध्यक्ष"."""
    MemoryStub(
        {("en-IN", "hi-IN", "Ramesh Verma — FPO CEO"): "रमेश वर्मा — महिला आरक्षण आयोग की अध्यक्ष"}
    ).install(monkeypatch)
    seen = fake_sarvam(
        monkeypatch,
        lambda b: httpx.Response(200, json={"translated_text": "रमेश वर्मा — [T1]"}),
    )
    result = service.translate(
        NullSession(),  # type: ignore[arg-type]
        ["Ramesh Verma — FPO CEO"],
        "hi-IN",
        machine_budget=None,
    )
    assert seen[0]["input"] == "Ramesh Verma — [T1]"
    assert result.translations == ["रमेश वर्मा — किसान उत्पादक संगठन के मुख्य कार्यकारी अधिकारी"]
    assert "महिला" not in result.translations[0]


def test_the_collective_keeps_its_article_and_its_meaning(settings, monkeypatch) -> None:
    """ "Runs the collective" became "सामूहिक रूप से चलता है" (runs collectively)."""
    MemoryStub().install(monkeypatch)
    seen = fake_sarvam(
        monkeypatch, lambda b: httpx.Response(200, json={"translated_text": "[T1] को चलाता है।"})
    )
    result = service.translate(
        NullSession(),  # type: ignore[arg-type]
        ["Runs the collective."],
        "hi-IN",
        machine_budget=None,
    )
    # The article stays in the sentence the model sees: "Runs [T1]" was rendered "दौड़ [T1]".
    assert seen[0]["input"] == "Runs the [T1]."
    assert result.translations == ["संगठन को चलाता है।"]
    assert not service.acceptable("Runs the collective.", "सामूहिक रूप से चलता है।", "hi-IN")


def test_a_dropped_placeholder_falls_back_to_translating_around_the_terms(
    settings, monkeypatch
) -> None:
    """Measured: "[T1] 1,832 [T2], [T3] 9 [T2]" came back with [T3] missing."""
    MemoryStub().install(monkeypatch)
    replies = {
        "Sow [T1] on [T2] and [T3] on [T4]": "[T2] पर [T1] और [T4] पर बोएं",
        "Sow": "बोएं",
        "on": "पर",
        "and": "और",
    }
    fake_sarvam(
        monkeypatch,
        lambda b: httpx.Response(200, json={"translated_text": replies[str(b["input"])]}),
    )
    result = service.translate(
        NullSession(),  # type: ignore[arg-type]
        ["Sow Mustard on 857 acres and Guava on 9 ac"],
        "hi-IN",
        machine_budget=None,
    )
    assert result.translations == ["बोएं सरसों पर 857 एकड़ और अमरूद पर 9 एकड़"]


def test_hindi_terms_map_back_to_canonical_english(settings, monkeypatch) -> None:
    MemoryStub().install(monkeypatch)
    seen = fake_sarvam(
        monkeypatch,
        lambda b: httpx.Response(200, json={"translated_text": "What has the [T1] told members?"}),
    )
    result = service.translate(
        NullSession(),  # type: ignore[arg-type]
        ["एफ.पी.ओ. ने सदस्यों को क्या बताया है?"],
        "en-IN",
        machine_budget=None,
    )
    assert seen[0]["input"] == "[T1] ने सदस्यों को क्या बताया है?"
    assert result.translations == ["What has the FPO told members?"]


def test_the_hand_written_dictionary_uses_the_glossary() -> None:
    """The stored corpus and the glossary must agree, or the same word reads two ways."""
    from agrivardhak.translation.__main__ import STRINGS, load_entries

    offenders = [
        (en, hi)
        for en, hi in load_entries(STRINGS)
        if not glossary.load().compliant(en, hi, "en-IN", "hi-IN")
    ]
    assert offenders == []


def test_glossary_patterns_compile_and_terms_are_unique() -> None:
    terms = glossary.load().terms
    assert len({t.id for t in terms}) == len(terms)
    assert all(t.en_patterns for t in terms)


@pytest.mark.usefixtures("db")
def test_a_machine_row_from_an_older_glossary_is_not_served_if_it_has_terms(
    session: Session,
) -> None:
    """ "Runs the collective. Sees the whole organization." was stored as "सामूहिक रूप से
    चलता है। पूरे संगठन को…" — संगठन present, for the wrong word, so a presence check passed."""
    from sqlalchemy import update

    source = "Runs the collective. Sees the whole organization."
    plain = "Sees the whole organization."
    for text, rendering in (
        (source, "सामूहिक रूप से चलता है। पूरे संगठन को देखता है।"),
        (plain, "पूरे संगठन को देखता है।"),
    ):
        service.store(
            session,
            "en-IN",
            "hi-IN",
            [service.Pair(text, rendering)],
            origin="MACHINE",
            provider="sarvam",
            model="mayura:v1",
        )
    session.execute(
        update(TranslationMemory)
        .where(
            TranslationMemory.source_hash.in_(
                [service.content_hash(source), service.content_hash(plain)]
            )
        )
        .values(corpus_version="old")
    )
    session.flush()

    hits = service.lookup(session, "en-IN", "hi-IN", [source, plain])
    # The row with a glossary term is stale; the row without one is still good.
    assert source not in hits
    assert hits[plain] == "पूरे संगठन को देखता है।"


@pytest.mark.usefixtures("db")
def test_machine_rows_record_the_glossary_version(session: Session) -> None:
    service.store(
        session,
        "en-IN",
        "hi-IN",
        [service.Pair("Sow the FPO plot", "किसान उत्पादक संगठन का प्लॉट बोएं")],
        origin="MACHINE",
        provider="sarvam",
        model="mayura:v1",
    )
    session.flush()
    row = session.execute(
        select(TranslationMemory).where(
            TranslationMemory.source_hash == service.content_hash("Sow the FPO plot")
        )
    ).scalar_one()
    assert row.corpus_version == glossary.load().version
    assert service.lookup(session, "en-IN", "hi-IN", ["Sow the FPO plot"])


def test_compliance_counts_occurrences() -> None:
    g = glossary.load()
    assert not g.compliant("the FPO and the FPO", "किसान उत्पादक संगठन और वह", "en-IN", "hi-IN")
    assert g.compliant(
        "the FPO and the FPO", "किसान उत्पादक संगठन और किसान उत्पादक संगठन", "en-IN", "hi-IN"
    )


def test_table_headers_keep_their_administrative_meaning() -> None:
    """ "Village" was rendered मोहल्ला (neighbourhood) and "Tract" लेख (article)."""
    for header, hindi in (("Village", "गाँव"), ("Block", "विकास खंड"), ("Tract", "क्षेत्र")):
        masked, terms = glossary.mask(header, "en-IN")
        assert masked == "[T1]" and terms[0].hi == hindi
    assert glossary.mask("Contact your block office", "en-IN")[0] == "Contact your [T1] office"
    assert glossary.mask("Block the sale until prices rise", "en-IN")[0] == (
        "Block the sale until prices rise"
    )


def test_version_endpoint_reports_the_glossary_version(client) -> None:
    response = client.get("/api/v1/translate/version")
    assert response.status_code == 200
    assert response.json() == {"corpus_version": glossary.load().version}


def test_tract_names_are_fixed_regions(settings, monkeypatch) -> None:
    """ "Doab" was rendered दोहा (Doha)."""
    MemoryStub().install(monkeypatch)
    seen = fake_sarvam(monkeypatch, echo_hindi)
    result = service.translate(
        NullSession(),  # type: ignore[arg-type]
        ["Doab", "Ganga-Par", "Yamuna Par"],
        "hi-IN",
        machine_budget=None,
    )
    assert result.translations == ["दोआब", "गंगा-पार", "यमुना-पार"]
    assert seen == []


def test_a_quantity_is_one_placeholder_so_the_number_stays_with_its_unit() -> None:
    """ "on 857 [T3]" came back "857 सरसों पर [T3]": the number drifted from its unit."""
    masked, terms = glossary.mask("Doab: lead with Mustard on 857 acres", "en-IN")
    assert masked == "[T1]: lead with [T2] on [T3]"
    assert [t.hi for t in terms] == ["दोआब", "सरसों", "857 एकड़"]
    masked, terms = glossary.mask("Paddy 1,832 ac, Guava 9ac", "en-IN")
    assert masked == "[T1] [T2], [T3] [T4]"
    assert [t.hi for t in terms] == ["धान", "1,832 एकड़", "अमरूद", "9 एकड़"]
