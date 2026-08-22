"""Application settings. Secrets come from the environment, never the repository (NFR-403)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AGRI_", extra="ignore")

    environment: str = "local"
    debug: bool = True

    database_url: str = "postgresql+psycopg://agrivardhak:agrivardhak@localhost:5433/agrivardhak"

    jwt_secret: str = "dev-only-not-a-real-secret"
    jwt_algorithm: str = "HS256"
    jwt_ttl_seconds: int = 60 * 60 * 12

    anthropic_api_key: str | None = None
    orchestrator_model: str = "claude-sonnet-5"

    #: NFR-302: below this, we return deterministic module output without narrative
    #: synthesis rather than an error page.
    llm_timeout_seconds: float = 30.0

    #: FR-813: below this the orchestrator states its uncertainty and says what data
    #: would raise it, instead of producing a confident-sounding answer.
    confidence_floor: float = 0.45

    #: FR-524: no diagnosis is asserted when the top two candidates are this close.
    diagnostic_margin: float = 0.15

    #: Offline demo mode — every adapter uses its fixture (NFR-303).
    use_fixtures: bool = False

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
