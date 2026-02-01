"""Configuration management for the investment agents."""

import logging
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Discord settings
    discord_bot_token: str = Field(default="", description="Discord bot token")
    discord_webhook_url: str = Field(default="", description="Discord webhook URL")
    discord_channel_id: int = Field(default=0, description="Default channel ID")
    discord_watchlist_channel_id: int | None = Field(default=None)
    discord_alerts_channel_id: int | None = Field(default=None)

    # Scheduling settings
    daily_update_time: str = Field(default="09:00", description="Daily update time")
    timezone: str = Field(default="America/New_York", description="Timezone")

    # Logging settings
    log_level: str = Field(default="INFO", description="Logging level")

    @property
    def daily_update_hour(self) -> int:
        try:
            return int(self.daily_update_time.split(":")[0])
        except (ValueError, IndexError):
            return 9

    @property
    def daily_update_minute(self) -> int:
        try:
            return int(self.daily_update_time.split(":")[1])
        except (ValueError, IndexError):
            return 0


@lru_cache
def get_settings() -> Settings:
    return Settings()


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logger.info(f"Logging configured at {level} level")
