"""Application settings. Secrets come from the environment, never the repository (NFR-403)."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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
    llm_provider: str = "nvidia"

    #: NVIDIA NIM exposes an OpenAI-compatible /chat/completions. We call it over httpx
    #: rather than adding the OpenAI SDK: two call sites do not justify a dependency.
    nvidia_api_key: str | None = None
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    #: A small instruct model, deliberately. The router picks one item from a closed enum —
    #: a task that does not need a frontier model, and a router slower than the work it
    #: schedules is worse than the keyword planner it replaces. Measured in docs/adr/0020;
    #: the original llama-3.1-8b choice and its spike are in docs/adr/0011.
    #:
    #: This value has an expiry the code cannot see: NVIDIA retired the whole Llama family
    #: on 2026-08-26 and served 410 to every routing call, which does not raise — it falls
    #: back to keywords, and every question silently became a Decision Packet. If routing
    #: looks wrong, check `fell_back` on the routing event before suspecting the prompt.
    router_model: str = "openai/gpt-oss-20b"

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

    #: ``NoDecode`` because pydantic-settings JSON-decodes a complex field inside the
    #: *source*, before any field validator can see it. Without it the validator below
    #: never runs and the process dies at import.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("database_url", mode="before")
    @classmethod
    def _name_the_driver(cls, value: object) -> object:
        """Accept the URL a hosting provider hands you, not just SQLAlchemy's spelling.

        Supabase, Render and Neon all give out ``postgresql://…``. SQLAlchemy reads a bare
        ``postgresql://`` as "use psycopg2", which is not a dependency here and never has
        been — ``pyproject.toml`` pins ``psycopg[binary]`` (v3), addressed as
        ``postgresql+psycopg://``. So the pasted URL fails at import with
        ``ModuleNotFoundError: No module named 'psycopg2'``, which points at a package nobody
        asked for rather than at the string that is actually wrong.

        Since psycopg2 cannot be present, rewriting the prefix has no ambiguity to resolve:
        the bare form has exactly one correct meaning in this application. An explicit
        ``+driver`` of any kind is left alone.
        """
        if isinstance(value, str):
            for bare in ("postgresql://", "postgres://"):
                if value.startswith(bare):
                    return "postgresql+psycopg://" + value[len(bare) :]
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _accept_a_plain_list(cls, value: object) -> object:
        """Accept ``a,b`` as well as ``["a","b"]`` from the environment.

        By default pydantic-settings parses a complex field from an env var as JSON, so the
        obvious ``AGRI_CORS_ORIGINS=https://app.vercel.app`` raised ``SettingsError`` and the
        process exited before serving anything. On a platform where environment variables are
        typed into a web form that is a genuinely bad failure: the health check never goes
        green, and the error names a JSON parser rather than the variable anyone would suspect.

        A comma-separated list is what a person types into that form, so accept it — and keep
        accepting JSON, which is what an existing deployment may already be setting.
        """
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                import json

                return json.loads(text)
            return [origin.strip() for origin in text.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
