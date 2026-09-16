"""The Sarvam ``/translate`` adapter.

Measured on 2026-09-16 rather than read from docs: both models take one string per call and
reject over-long input with a 400 — 2,000 characters for ``sarvam-translate:v1``, 1,000 for
``mayura:v1``. So long text is split on sentence boundaries here, and distinct strings are
sent in parallel. Which model is the default, and why, is in ADR-0023.

**It never raises to the caller.** A translation that fails returns ``None`` and the page
keeps the source text. A button that turns the page blank or throws is a worse failure than
a sentence left in English — the same rule as NFR-303 for the router.

The auth header is ``api-subscription-key``, not the Bearer header the chat-completions
endpoint in ``orchestrator/llm.py`` accepts. Same key, different spelling.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from agrivardhak.config import get_settings

log = logging.getLogger(__name__)

#: Sarvam's per-input limits, measured: over them the API answers 400, not a truncation.
INPUT_LIMITS = {"sarvam-translate:v1": 2000, "mayura:v1": 1000}
#: For a model not in the table, the stricter of the two.
MAX_INPUT_CHARS = min(INPUT_LIMITS.values())


def input_limit(model: str) -> int:
    return INPUT_LIMITS.get(model, MAX_INPUT_CHARS)


#: How many Sarvam calls may be in flight across the whole process, not per request. The key
#: is rate-limited on a rolling window: 12 concurrent calls succeed on a quiet key, but right
#: after one uncached Decision Packet page (100+ strings, fanned out 3 batches x 5 calls) every
#: call in a burst of 15 came back 429 (measured 2026-09-17). A shared ceiling keeps one busy
#: page from exhausting the window for every other reader.
MAX_PARALLEL = 4
_in_flight = threading.BoundedSemaphore(MAX_PARALLEL)

_RETRY_STATUSES = {429, 500, 502, 503, 504}
#: Long enough to outlast a rate-limit window's edge; Retry-After wins when Sarvam sends one.
_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
_MAX_RETRY_AFTER_SECONDS = 10.0

#: A sentence ends at the Devanagari danda or Latin terminal punctuation, or at a newline.
_SENTENCE_END = re.compile(r"(?<=[।.?!\n])\s+")


def available() -> bool:
    """A key is set and the offline kill-switch is off (``use_fixtures``, NFR-303)."""
    settings = get_settings()
    return bool(settings.sarvam_api_key) and not settings.use_fixtures


def split(text: str, limit: int = MAX_INPUT_CHARS) -> list[str]:
    """Pieces of ``text``, each at most ``limit`` characters, broken at sentence ends.

    A single sentence longer than the limit is broken at the last space before it, and a
    run with no space at all is cut hard — rare in prose, and better than a 400.
    """
    if len(text) <= limit:
        return [text]

    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(text):
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        candidate = f"{current} {sentence}" if current else sentence
        if len(candidate) <= limit:
            current = candidate
        else:
            pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    return [p for p in pieces if p]


def _call(client: httpx.Client, text: str, source: str, target: str) -> str | None:
    settings = get_settings()
    payload = {
        "input": text,
        "source_language_code": source,
        "target_language_code": target,
        "model": settings.sarvam_translate_model,
        # Keep 0-9. Devanagari digits would change what a number looks like next to a unit
        # and a confidence chip that did not change.
        "numerals_format": "international",
    }
    headers = {
        "api-subscription-key": settings.sarvam_api_key or "",
        "Content-Type": "application/json",
    }
    for attempt in range(len(_BACKOFF_SECONDS) + 1):
        try:
            with _in_flight:
                response = client.post(settings.sarvam_translate_url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            log.warning("sarvam translate transport error: %s", exc)
            response = None
        if response is not None and response.status_code < 400:
            try:
                translated = response.json().get("translated_text")
            except ValueError:
                translated = None
            if isinstance(translated, str) and translated.strip():
                return translated
            log.warning("sarvam translate returned no text")
            return None
        if response is not None and response.status_code not in _RETRY_STATUSES:
            log.warning(
                "sarvam translate rejected: %s %s", response.status_code, response.text[:200]
            )
            return None
        if attempt < len(_BACKOFF_SECONDS):
            time.sleep(_retry_delay(response, _BACKOFF_SECONDS[attempt]))
    return None


def _retry_delay(response: httpx.Response | None, default: float) -> float:
    header = response.headers.get("retry-after") if response is not None else None
    try:
        return min(float(header), _MAX_RETRY_AFTER_SECONDS) if header else default
    except ValueError:
        return default


def translate_one(client: httpx.Client, text: str, source: str, target: str) -> str | None:
    """Translate one string, splitting it if it exceeds the input limit."""
    parts = split(text, input_limit(get_settings().sarvam_translate_model))
    translated: list[str] = []
    for part in parts:
        result = _call(client, part, source, target)
        if result is None:
            return None
        translated.append(result)
    return " ".join(translated)


def translate_many(texts: list[str], source: str, target: str) -> dict[str, str]:
    """Translate distinct strings in parallel. Returns only the ones that succeeded."""
    if not texts or not available():
        return {}
    settings = get_settings()
    results: dict[str, str] = {}
    with (
        httpx.Client(timeout=settings.translate_timeout_seconds) as client,
        ThreadPoolExecutor(max_workers=min(MAX_PARALLEL, len(texts))) as pool,
    ):
        futures = {text: pool.submit(translate_one, client, text, source, target) for text in texts}
        for text, future in futures.items():
            try:
                translated = future.result()
            except Exception as exc:  # pragma: no cover - translate_one does not raise
                log.warning("sarvam translate failed: %s", exc)
                continue
            if translated is not None:
                results[text] = translated
    return results
