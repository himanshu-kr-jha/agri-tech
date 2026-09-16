"""Application settings. Secrets come from the environment, never the repository (NFR-403)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

#: Resolved against the package rather than the working directory. A bare ``".env"`` is read
#: relative to CWD, so the same settings loaded fine under ``make dev`` (which cds into
#: apps/api) and silently found no key under any script run from the repo root — the kind of
#: difference that looks like "the model is not working" rather than like a path bug.
_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_prefix="AGRI_", extra="ignore")

    environment: str = "local"
    debug: bool = True

    database_url: str = "postgresql+psycopg://agrivardhak:agrivardhak@localhost:5433/agrivardhak"

    jwt_secret: str = "dev-only-not-a-real-secret"
    jwt_algorithm: str = "HS256"
    jwt_ttl_seconds: int = 60 * 60 * 12

    anthropic_api_key: str | None = None
    orchestrator_model: str = "claude-sonnet-5"

    # ------------------------------------------------------------- assistant routing
    #: Which provider backs the intent router and the relevance selector. ``"none"``
    #: disables both, and the assistant degrades to keyword routing with unfiltered
    #: packets rather than failing — see orchestrator/llm.py (NFR-303).
    llm_provider: str = "sarvam"

    #: Both providers wired in here expose an OpenAI-compatible /chat/completions. We call
    #: it over httpx rather than adding a provider SDK: two call sites do not justify a
    #: dependency.
    nvidia_api_key: str | None = None
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    #: Sarvam's chat-completions endpoint accepts the same Bearer auth and the same
    #: response_format (json_schema, then json_object) ladder as NVIDIA NIM, so it plugs into
    #: the same request path in orchestrator/llm.py with no header or parsing changes.
    sarvam_api_key: str | None = None
    sarvam_base_url: str = "https://api.sarvam.ai/v1"
    #: A small/fast instruct model, deliberately. The router picks one item from a closed
    #: enum — a task that does not need a frontier model, and a router slower than the work
    #: it schedules is worse than the keyword planner it replaces. Measured in docs/adr/0020;
    #: the original llama-3.1-8b choice and its spike are in docs/adr/0011.
    #:
    #: This value has an expiry the code cannot see, whichever provider it names: NVIDIA
    #: retired the whole Llama family on 2026-08-26 and served 410 to every routing call,
    #: which does not raise — it falls back to keywords, and every question silently became
    #: a Decision Packet. If routing looks wrong, check `fell_back` on the routing event
    #: before suspecting the prompt. Re-run `make routing-eval` after any provider or model
    #: change here — do not trust it un-measured (ADR-0011, ADR-0020).
    router_model: str = "sarvam-105b"

    #: Shorter than the narrator's budget on purpose. The narrator runs after the answer
    #: exists, so it can afford to be slow; the router runs before any work starts, and a
    #: slow classification is worse than the keyword one it falls back to.
    router_timeout_seconds: float = 8.0

    #: NFR-302: below this, we return deterministic module output without narrative
    #: synthesis rather than an error page.
    llm_timeout_seconds: float = 30.0

    #: FR-813: below this the orchestrator states its uncertainty and says what data
    #: would raise it, instead of producing a confident-sounding answer.
    confidence_floor: float = 0.45

    #: FR-524: no diagnosis is asserted when the top two candidates are this close.
    diagnostic_margin: float = 0.15

    #: Offline demo mode: an LLM kill-switch. When true, ``orchestrator/llm.py`` reports no
    #: model available, so the intent router falls back to keyword routing and the narrator
    #: returns packets unrewritten (NFR-303) — deterministic module output, no network.
    #:
    #: It does **not** switch the ingestion adapters. They read committed files from
    #: ``seed/generated`` unconditionally (ingestion/weather.py, ingestion/agmarknet.py), so
    #: external data is already fixture-backed whatever this is set to. A deployment wanting
    #: a live assistant over committed data therefore wants ``false``, not ``true``.
    use_fixtures: bool = False

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
