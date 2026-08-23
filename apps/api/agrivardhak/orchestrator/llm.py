"""The single place the assistant talks to a language model.

Two callers only — :mod:`agrivardhak.orchestrator.router` and
:mod:`agrivardhak.orchestrator.review` — and both use the same entry point:
``structured(system, user, schema) -> dict | None``.

Three rules give this module its shape.

**It never raises into a request.** Every failure — no key, a timeout, a 500, a refusal,
malformed JSON, a schema mismatch — returns ``None``. The caller then falls back to
deterministic behaviour. A model being slow must never be the reason a CEO sees an error
page (NFR-302).

**It never returns free text.** Callers get a parsed ``dict`` or nothing. Prose parsing is
how a system starts trusting whatever a model happened to say; every response here is JSON
that survived ``json.loads`` and the caller's own Pydantic validation on top.

**It degrades in three steps, not one.** NVIDIA NIM exposes an OpenAI-compatible endpoint,
but ``response_format`` support varies by model. So we ask for a JSON schema, fall back to
JSON mode, then to plain prompting with extraction — rather than assuming a capability and
discovering at demo time that this particular model does not have it.

We call the endpoint over ``httpx``, already a first-class dependency, instead of adding the
OpenAI SDK. Two call sites do not justify a dependency.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from agrivardhak.config import get_settings

log = logging.getLogger(__name__)

#: Deterministic sampling. The router is a classifier and the selector is a ranker; neither
#: benefits from variety, and both are easier to reason about when the same question routes
#: the same way twice.
TEMPERATURE = 0.0
MAX_TOKENS = 900


def available() -> bool:
    """Whether a model can be reached at all.

    Checked before work begins so a caller can go straight to its deterministic path rather
    than burning a timeout discovering the same thing.
    """
    settings = get_settings()
    if settings.use_fixtures:
        return False
    provider = (settings.llm_provider or "none").lower()
    if provider == "nvidia":
        return bool(settings.nvidia_api_key)
    if provider == "anthropic":
        return bool(settings.anthropic_api_key)
    return False


def structured(
    *, system: str, user: str, schema: dict[str, Any], schema_name: str = "response"
) -> dict[str, Any] | None:
    """Ask for one JSON object matching ``schema``. ``None`` on any failure whatsoever."""
    if not available():
        return None
    settings = get_settings()
    provider = (settings.llm_provider or "none").lower()
    if provider != "nvidia":
        log.warning("llm provider %r has no adapter; falling back", provider)
        return None

    payloads = _payload_ladder(settings.router_model, system, user, schema, schema_name)
    url = f"{settings.nvidia_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.nvidia_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    for attempt, payload in enumerate(payloads):
        try:
            with httpx.Client(timeout=settings.router_timeout_seconds) as client:
                response = client.post(url, headers=headers, json=payload)
            if response.status_code >= 400:
                # A 4xx on the early rungs usually means this model does not accept the
                # response_format we asked for, which is worth another rung. A 4xx on the
                # last rung is a real error and there is nothing left to try.
                log.warning(
                    "llm attempt %d rejected: %s %s",
                    attempt,
                    response.status_code,
                    response.text[:200],
                )
                continue
            parsed = _extract(response.json())
            if parsed is not None:
                return parsed
        except Exception as exc:  # timeouts, transport errors, malformed bodies
            log.warning("llm attempt %d failed: %s", attempt, exc)
            continue

    log.warning("llm produced no usable JSON in %d attempts; caller falls back", len(payloads))
    return None


def _payload_ladder(
    model: str, system: str, user: str, schema: dict[str, Any], schema_name: str
) -> list[dict[str, Any]]:
    """Three requests, most-constrained first.

    Rung 1 asks the server to enforce the schema. Rung 2 asks only for valid JSON. Rung 3
    asks for nothing and relies on the prompt plus extraction. Every rung is validated by
    the caller regardless, so a weaker rung is slower to trust, not unsafe.
    """
    base: dict[str, Any] = {
        "model": model,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }

    schema_rung = dict(base)
    schema_rung["response_format"] = {
        "type": "json_schema",
        "json_schema": {"name": schema_name, "schema": schema, "strict": True},
    }

    # response_format=json_object guarantees *valid* JSON and says nothing about shape, so
    # the schema has to travel in the prompt. Measured: without this the model returns a
    # well-formed object with entirely invented keys.
    json_rung = dict(base)
    json_rung["response_format"] = {"type": "json_object"}
    json_rung["messages"] = [
        {"role": "system", "content": system},
        {"role": "user", "content": _with_schema(user, schema)},
    ]

    plain_rung = dict(base)
    plain_rung["messages"] = [
        {"role": "system", "content": system},
        {"role": "user", "content": _with_schema(user, schema)},
    ]
    return [schema_rung, json_rung, plain_rung]


def _with_schema(user: str, schema: dict[str, Any]) -> str:
    """Prompt-side schema, with an explicit guard against the failure it actually produces.

    A small model asked to "reply matching this schema" will, a fair fraction of the time,
    reply *with* the schema — echoing the definition back as its answer. Naming that failure
    is worth more than another sentence of politeness.
    """
    return (
        f"{user}\n\nReply with one JSON object that is an *instance* of this schema — the "
        f"filled-in answer, never the schema definition itself. No prose, no code fence.\n"
        f"{json.dumps(schema)}"
    )


def _extract(body: dict[str, Any]) -> dict[str, Any] | None:
    """Pull the first JSON object out of a chat-completions body.

    Tolerant of the two things models do even when told not to: wrapping the object in a
    code fence, and prefacing it with a sentence. Anything that is not a JSON *object* is
    rejected — a bare list or a string is not what any caller here asked for.
    """
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(content, str):
        return None
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or _is_schema_echo(parsed):
        return None
    return parsed


def _is_schema_echo(parsed: dict[str, Any]) -> bool:
    """Did the model hand back the schema instead of an answer?

    A small model asked to "reply matching this schema" replies *with* the schema a fair
    fraction of the time, and the echo is valid JSON — so it passed the parser and reached
    the caller, which then rejected it as an unusable plan and fell back. Catching it here
    lets the ladder try the next rung instead, which is what the rungs are for.

    Recognised structurally rather than by key names alone: an answer object could legitimately
    contain a field called ``type``, but not one called ``type`` set to ``"object"`` alongside
    a ``properties`` mapping.
    """
    if parsed.get("type") == "object" and isinstance(parsed.get("properties"), dict):
        return True
    # The other shape it takes: every field wrapped as {"value": ...}.
    values = list(parsed.values())
    return bool(values) and all(isinstance(v, dict) and set(v.keys()) == {"value"} for v in values)
