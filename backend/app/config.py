from __future__ import annotations

from functools import lru_cache
from typing import List, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ----- Pydantic / Settings config (v2 style) -----
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,   # ENV и env считаем одинаковыми
        extra="ignore",         # не падать от лишних переменных в .env
    )

    # ----- Core -----
    env: Literal["dev", "prod", "test"] = Field(
        default="dev", validation_alias="ENV"
    )
    debug: bool = Field(default=True, validation_alias="DEBUG")
    log_level: Literal["debug", "info", "warning", "error", "critical"] = Field(
        default="info", validation_alias="LOG_LEVEL"
    )

    # ----- Database -----
    database_url: str = Field(
        default="postgresql+asyncpg://algobench:algobench@db:5432/algobench",
        validation_alias="DATABASE_URL",
    )

    # ----- JWT / Security -----
    jwt_secret: SecretStr = Field(
        ..., validation_alias="JWT_SECRET"
    )
    jwt_algorithm: Literal["HS256", "RS256"] = Field(
        default="HS256", validation_alias="JWT_ALGORITHM"
    )
    access_token_expire_minutes: int = Field(
        default=60, validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES", ge=1, le=24 * 60
    )

    # ----- CORS -----
    # В .env храним CSV: "https://foo.com,https://bar.com" или "*"
    cors_allow_origins: List[str] = Field(
        default_factory=lambda: ["*"], validation_alias="CORS_ALLOW_ORIGINS"
    )

    # ----- Rate limiting (placeholder) -----
    rate_limit_per_minute: int = Field(
        default=120, validation_alias="RATE_LIMIT_PER_MINUTE", ge=1
    )

    # ---------- Validators ----------
    @field_validator("database_url")
    @classmethod
    def _check_db_scheme(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL должен начинаться с 'postgresql+asyncpg://'")
        return v

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _parse_cors_csv(cls, v):
        # допускаем уже-список или строку CSV
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            v = v.strip()
            if v == "*":
                return ["*"]
            # разбиваем по запятым и убираем пустые
            return [x.strip() for x in v.split(",") if x.strip()]
        return ["*"]


@lru_cache
def get_settings() -> Settings:
    """Возвращает закэшированный экземпляр настроек приложения."""
    return Settings()


# Удобные помощники для тестов/локальной перезагрузки
def reload_settings() -> Settings:
    """Сбрасывает кэш и перечитывает .env."""
    get_settings.cache_clear()  # type: ignore[attr-defined]
    return get_settings()


settings = get_settings()
