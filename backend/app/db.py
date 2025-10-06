from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any, Optional

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import settings


# ---------- Declarative Base & metadata ----------
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Базовый класс для всех моделей (SQLAlchemy 2.0 Declarative)."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# ---------- Engine & Session factory ----------

def _make_engine(url: Optional[str] = None) -> AsyncEngine:
    # echo только в режиме отладки
    echo = bool(settings.debug)
    return create_async_engine(
        url or settings.database_url,
        echo=echo,
        pool_pre_ping=True,
        # Параметры пула — по умолчанию безопасны. В проде можно вынести в конфиг.
        # pool_size=getattr(settings, "db_pool_size", 5),
        # max_overflow=getattr(settings, "db_max_overflow", 10),
        # connect_args={"server_settings": {"application_name": "algobench-backend"}},
    )


engine: AsyncEngine = _make_engine()

# expire_on_commit=False — объекты остаются валидными после commit
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: выдать асинхронную сессию и корректно закрыть её."""
    async with AsyncSessionLocal() as session:
        yield session


# ---------- Healthcheck ----------

async def check_database(timeout: float = 2.0) -> bool:
    """Простой ping БД (используется в /healthz) с таймаутом."""
    async def _ping() -> None:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(_ping(), timeout=timeout)
        return True
    except Exception:
        return False


# ---------- Utilities for Alembic and lifecycle ----------

def get_engine() -> AsyncEngine:
    """Возвращает текущий AsyncEngine (для Alembic env.py)."""
    return engine


def get_base() -> type[Base]:
    """Возвращает Declarative Base (для автогенерации миграций)."""
    return Base


async def shutdown_engine() -> None:
    """Закрыть пул соединений (вызывать на остановке приложения)."""
    await engine.dispose()


async def reset_engine(new_url: Optional[str] = None) -> None:
    """
    Пересоздать engine (полезно в тестах или при смене конфига).
    Пример:
        await reset_engine("postgresql+asyncpg://user:pass@localhost:5432/testdb")
    """
    global engine, AsyncSessionLocal  # noqa: PLW0603
    await engine.dispose()
    engine = _make_engine(new_url)
    AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
