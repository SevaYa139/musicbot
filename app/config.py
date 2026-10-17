"""Конфигурация приложения.

Все секреты — только через переменные окружения / .env.
При старте выполняется валидация обязательных полей.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    bot_token: str = Field(default="", validation_alias="BOT_TOKEN")
    admin_ids: list[int] = Field(default_factory=list, validation_alias="ADMIN_IDS")

    database_url: str = Field(
        default="sqlite+aiosqlite:///" + str(BASE_DIR / "data" / "musicbot.db"),
        validation_alias="DATABASE_URL",
    )
    redis_url: str | None = Field(default=None, validation_alias="REDIS_URL")

    temp_dir: Path = Field(
        default=Path("/tmp/musicbot"),  # noqa: S108
        validation_alias="TEMP_DIR",
    )
    max_file_size_mb: int = Field(default=1900, validation_alias="MAX_FILE_SIZE_MB")
    max_video_duration_seconds: int = Field(
        default=7200, validation_alias="MAX_VIDEO_DURATION_SECONDS"
    )
    max_concurrent_jobs: int = Field(default=3, validation_alias="MAX_CONCURRENT_JOBS")
    job_timeout_seconds: int = Field(default=1800, validation_alias="JOB_TIMEOUT_SECONDS")
    rate_limit_per_minute: int = Field(default=12, validation_alias="RATE_LIMIT_PER_MINUTE")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    ytdlp_proxy: str | None = Field(
        default=None,
        validation_alias="YTDLP_PROXY",
        description=(
            "Прокси для yt-dlp (например socks5://ip:port) — нужен для TikTok, "
            "если IP сервера заблокирован."
        ),
    )

    custom_emoji_music: str | None = Field(
        default=None, validation_alias="CUSTOM_EMOJI_MUSIC"
    )
    custom_emoji_video: str | None = Field(
        default=None, validation_alias="CUSTOM_EMOJI_VIDEO"
    )
    custom_emoji_download: str | None = Field(
        default=None, validation_alias="CUSTOM_EMOJI_DOWNLOAD"
    )
    custom_emoji_search: str | None = Field(
        default=None, validation_alias="CUSTOM_EMOJI_SEARCH"
    )
    custom_emoji_gear: str | None = Field(
        default=None, validation_alias="CUSTOM_EMOJI_GEAR"
    )
    custom_emoji_upload: str | None = Field(
        default=None, validation_alias="CUSTOM_EMOJI_UPLOAD"
    )
    custom_emoji_inbox: str | None = Field(
        default=None, validation_alias="CUSTOM_EMOJI_INBOX"
    )
    custom_emoji_check: str | None = Field(
        default=None, validation_alias="CUSTOM_EMOJI_CHECK"
    )
    custom_emoji_cross: str | None = Field(
        default=None, validation_alias="CUSTOM_EMOJI_CROSS"
    )
    custom_emoji_chart: str | None = Field(
        default=None, validation_alias="CUSTOM_EMOJI_CHART"
    )
    custom_emoji_link: str | None = Field(
        default=None, validation_alias="CUSTOM_EMOJI_LINK"
    )
    custom_emoji_play: str | None = Field(
        default=None, validation_alias="CUSTOM_EMOJI_PLAY"
    )

    spotify_client_id: str | None = Field(
        default=None, validation_alias="SPOTIFY_CLIENT_ID"
    )
    spotify_client_secret: str | None = Field(
        default=None, validation_alias="SPOTIFY_CLIENT_SECRET"
    )
    yandex_token: str | None = Field(default=None, validation_alias="YANDEX_TOKEN")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, value: object) -> object:
        if isinstance(value, int):
            return [value]
        if isinstance(value, str):
            return [int(v.strip()) for v in value.split(",") if v.strip()]
        return value

    def validate_or_raise(self) -> None:
        """Проверка обязательных настроек с понятными сообщениями об ошибках."""
        missing: list[str] = []
        if not self.bot_token:
            missing.append("BOT_TOKEN")
        if missing:
            raise ConfigError(
                "Отсутствуют обязательные переменные окружения: "
                + ", ".join(missing)
                + ". Заполните их в .env (см. .env.example)."
            )
        if self.max_file_size_mb > 2048:
            raise ConfigError("MAX_FILE_SIZE_MB не должен превышать 2048 (лимит Bot API).")


class ConfigError(Exception):
    """Ошибка конфигурации, показываемая при старте."""


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_or_raise()
    return settings
