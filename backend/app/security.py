from __future__ import annotations  # Разрешает использовать подсказки типов "из будущего"

from datetime import datetime, timedelta, timezone  # Для срока жизни токена (exp)
from typing import Annotated, Optional  # Annotated для FastAPI Depends

from fastapi import Depends, HTTPException, status  # Исключения и зависимости FastAPI
from fastapi.security import OAuth2PasswordBearer  # Способ достать токен из заголовка Authorization
from jose import JWTError, jwt  # Библиотека для кодирования/декодирования JWT
from passlib.context import CryptContext  # Удобная обёртка для bcrypt/argon2 и т.д.

from .config import settings  # Наши настройки (.env → Settings)
from .db import get_session  # Зависимость, которая отдаёт асинхронную сессию БД
from .models.user import User, UserRole  # Модель пользователя + enum ролей
from .repositories.user_repo import UserRepository  # Репозиторий для работы с User

# ---------- Password hashing (хеширование пароля) ----------
# Создаём контекст — как "ящик с инструментами" для хеширования
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Сравниваем "сырой" пароль с сохранённым хешем.
    Представь: мы не храним пароль, мы храним "отпечаток".
    Тут мы проверяем, совпадает ли отпечаток.
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Делаем bcrypt-хеш из пароля.
    Это как превратить пароль в "кашу", из которой нельзя обратно получить исходный текст.
    """
    return pwd_context.hash(password)


# ---------- JWT helpers (создание и разбор токена) ----------
def create_access_token(
    subject: str,  # Кого "представляет" токен — обычно email или user_id
    expires_delta: Optional[timedelta] = None,  # Через сколько протухнет токен
) -> str:
    """
    Создаём JWT-токен: кладём в него "sub" (субъект) и "exp" (срок годности).
    Подписываем секретным ключом, чтобы нельзя было подделать.
    """
    # Берём текущее время в UTC
    now = datetime.now(timezone.utc)
    # Если срок не передали — берём из настроек (например, 60 минут)
    expire = now + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))

    # Полезная нагрузка токена (минимум: sub, exp)
    to_encode = {"sub": subject, "exp": expire}

    # Кодируем и подписываем токен нашим секретом
    return jwt.encode(
        claims=to_encode,
        key=settings.jwt_secret.get_secret_value(),  # SecretStr → достаём скрытое значение
        algorithm=settings.jwt_algorithm,            # Например, "HS256"
    )


def decode_access_token(token: str, *, leeway_seconds: int = 10) -> str:
    """
    Декодируем токен и достаём "sub" (например, email).
    Добавляем небольшую "поблажку" по времени (leeway), чтобы часы не подвели.
    """
    try:
        # Разбираем и проверяем подпись + срок годности
        payload = jwt.decode(
            token=token,
            key=settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],  # Важно: список допустимых алгоритмов
            options={"verify_exp": True},         # Явно говорим: проверяй истечение
            leeway=leeway_seconds,                # Допускаем маленькую рассинхронизацию времени
        )
        email = payload.get("sub")  # Достаём "кто это" из токена
        if not email:
            # Если в токене нет "sub", считаем его некорректным
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
        return email
    except JWTError as exc:
        # Любая ошибка подписи/срока/формата → не пускаем
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        ) from exc


# ---------- OAuth2 dependency (как доставать токен из запроса) ----------
# Эта зависимость говорит FastAPI: "Ищи токен в заголовке Authorization: Bearer <token>"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


# ---------- Current user helpers (получение текущего пользователя) ----------
async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],  # Берём токен через зависимость
    session=Depends(get_session),                   # Получаем сессию БД корректно (контекст, закрытие)
) -> User:
    """
    Находим текущего пользователя по токену.
    1) Разобрали токен → получили email
    2) Сходили в БД → нашли пользователя
    3) Проверили, что он активен
    """
    email = decode_access_token(token)

    # Работаем через репозиторий — он умеет ходить в БД
    repo = UserRepository(session)
    user = await repo.get_by_email(email)

    if not user:
        # Если пользователь не найден — токен невалиден/устарел
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        # Пользователь заблокирован/деактивирован
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )

    return user


async def get_current_admin(
    current_user: Annotated[User, Depends(get_current_user)],  # Сначала получаем обычного пользователя
) -> User:
    """
    Проверяем, что текущий пользователь — администратор.
    Если нет — возвращаем 403 (нельзя).
    """
    # Сравниваем с enum, а не со строкой — так безопаснее и предсказуемее
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user
