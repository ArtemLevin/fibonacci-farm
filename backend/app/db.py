from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings


# ---- SQLAlchemy Base & metadata ----
class Base(DeclarativeBase):
    """Базовый класс для всех моделей (SQLAlchemy 2.0 Declarative)."""

    # Можно настроить соглашения именования, если понадобятся миграции с предсказуемыми именами
    # metadata = MetaData(
    #     naming_convention={
    #         "ix": "ix_%(column_0_label)s",
    #         "uq": "uq_%(table_name)s_%(column_0_name)s",
    #         "ck": "ck_%(table_name)s_%(constraint_name)s",
    #         "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    #         "pk": "pk_%(table_name)s",
    #     }
    # )
    pass


# ---- Engine & Session ----
def _make_engine() -> AsyncEngine:
    # В dev можно включать echo для отладки SQL
    echo = settings.debug
    return create_async_engine(
        settings.database_url,
        echo=echo,
        pool_pre_ping=True,
        # Параметры пула задаем осторожно: asyncpg сам эффективно управляет соединениями
        # pool_size и max_overflow применимы, но оставим дефолты, чтобы не навредить в контейнерах
        future=True,
    )


engine: AsyncEngine = _make_engine()

# expire_on_commit=False — чтобы объекты оставались валидными после commit в обработчиках
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: выдать асинхронную сессию и корректно закрыть её."""
    async with AsyncSessionLocal() as session:
        yield session


# ---- Healthcheck helper ----
async def check_database() -> bool:
    """Простой ping БД, используется /healthz."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


# ---- Alembic hooks (удобно импортировать из env.py) ----
def get_engine() -> AsyncEngine:
    """Возвращает текущий AsyncEngine (для Alembic env.py)."""
    return engine


def get_base() -> type[Base]:
    """Возвращает Declarative Base (для автогенерации миграций)."""
    return Base
