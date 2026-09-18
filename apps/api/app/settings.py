"""Validated application settings loaded from the environment."""

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the API process.

    The database URL is optional at process start so `/health` remains useful
    during installation. `/ready` reports a dependency failure until the
    owner-configured PostgreSQL target is reachable.
    """

    service_name: str = "ebook-factory-api"
    version: str = "0.1.0"
    environment: str = "local"
    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("EBOOK_FACTORY_DATABASE_URL", "DATABASE_URL"),
    )
    artifact_root: Path = Path("var/artifacts")
    worker_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("EBOOK_FACTORY_WORKER_TOKEN", "WORKER_TOKEN"),
    )
    telegram_bot_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("EBOOK_FACTORY_TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"),
    )
    telegram_allowed_chat_ids: str = Field(
        default="",
        validation_alias=AliasChoices("EBOOK_FACTORY_TELEGRAM_ALLOWED_CHAT_IDS", "TELEGRAM_ALLOWED_CHAT_IDS"),
    )
    telegram_allowed_sender_ids: str = Field(
        default="",
        validation_alias=AliasChoices("EBOOK_FACTORY_TELEGRAM_ALLOWED_SENDER_IDS", "TELEGRAM_ALLOWED_SENDER_IDS"),
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )
