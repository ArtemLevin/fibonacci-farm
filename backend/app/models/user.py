from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Literal

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, validates

from ..db import Base


class UserRole(str, Enum):
    user = "user"
    admin = "admin"


class User(Base):
    """
    Пользователь системы.

    Требования:
      - id: UUID primary key
      - email: уникальный, индексируемый, храним в нижнем регистре
      - hashed_password: bcrypt-хэш
      - role: 'user' | 'admin' (default='user')
      - is_active: bool (default=True)
      - created_at: timestamptz (server_default=now())
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[Literal["user", "admin"]] = mapped_column(
        SAEnum(UserRole, name="user_role"), nullable=False, default=UserRole.user
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    # Функциональный уникальный индекс по lower(email)
    __table_args__ = (
        Index("uq_users_email_lower", func.lower(email), unique=True),
    )

    @validates("email")
    def _lower_email(self, key: str, value: str) -> str:  # noqa: ARG002
        # Нормализуем email к нижнему регистру
        return value.strip().lower()

    def __repr__(self) -> str:  # pragma: no cover - для удобства отладки
        return f"<User id={self.id} email={self.email} role={self.role}>"
