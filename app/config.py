"""Application settings, read from environment variables (and a local .env)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every setting can be overridden by the environment variable of the same name."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # `model_name` is a plain setting, not a Pydantic protected name.
        protected_namespaces=(),
    )

    # --- Agno model provider -------------------------------------------------
    agno_model_provider: str = "openai"
    model_name: str = "gpt-4o-mini"
    openai_api_key: str | None = None
    openai_base_url: str | None = None

    # --- Postgres ------------------------------------------------------------
    postgres_user: str = "agno"
    postgres_password: str = "agno"
    postgres_db: str = "agno"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    # Optional full URL; when set it wins over the parts above.
    database_url: str | None = None

    @property
    def sqlalchemy_url(self) -> str:
        """The SQLAlchemy URL to dial."""
        if self.database_url:
            return self.database_url
        return (
            "postgresql+psycopg://"
            f"{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
