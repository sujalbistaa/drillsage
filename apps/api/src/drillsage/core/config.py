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

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton. Tests override via FastAPI dependency overrides."""
    return Settings()
