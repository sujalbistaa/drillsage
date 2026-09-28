"""Application settings, loaded once from the environment (and `.env` in development).

Every variable is documented in the repository's `.env.example`.
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[5]

VOLVE_ATTRIBUTION = (
    "Contains data from the Volve field dataset, released by Equinor and the Volve "
    "licence partners under CC BY-NC-SA 4.0."
)
"""Required by the Volve licence wherever its data is shown."""


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DRILLSAGE_",
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "DrillSage"
    environment: Environment = Environment.DEVELOPMENT
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = False

    database_url: PostgresDsn = Field(
        default=PostgresDsn("postgresql+asyncpg://drillsage:drillsage@localhost:5433/drillsage"),
    )
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_connect_timeout_s: float = Field(default=3.0, gt=0)

    cors_origins: list[str] = ["http://localhost:3000"]

    data_dir: Path = REPO_ROOT / "data"
    basin_pack: str = "north_sea"

    local_only: bool = False
    llm_budget_usd: float = Field(default=25.0, ge=0)
    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    llm_provider: Literal["gemini", "anthropic"] = "gemini"
    """Gemini free tier by default (demo); Anthropic stays available (CLAUDE.md §5)."""
    gemini_api_key: SecretStr | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    llm_fallback_models: list[str] = ["gemini-3.5-flash-lite", "gemini-flash-lite-latest"]
    """Tried in order when the primary model is overloaded or retired (Gemini only)."""
    llm_min_interval_s: float = Field(default=6.0, ge=0)
    """Pause between calls to stay under free-tier requests-per-minute limits."""
    llm_model_extract: str = "gemini-3.8-flash"
    llm_effort_extract: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    """Starting point for extraction; tune on the gold set before changing (CLAUDE.md §5)."""
    llm_max_tokens_extract: int = Field(default=16_000, ge=1_024)
    llm_refusal_fallback: bool = True
    """Server-side `fallbacks: "default"` on online calls (not available on the Batches API)."""

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton. Tests override via FastAPI dependency overrides."""
    return Settings()
