from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_access_token
from app.models.entities import User, UserObjectAccess
from app.models.enums import UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Недействительный токен")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь не найден или отключён")
    return user


def require_role(*roles: UserRole):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
        return user

    return checker


def get_accessible_object_ids(user: User, db: Session) -> set[int] | None:
    """Минимальная матрица доступа по объектам (раздел 12 плана реализации — полная
    матрица с подразделениями отложена как требование будущего пилота, см. `backend/README.md`).

    Возвращает None, если ограничение не действует (полный доступ): у администратора —
    всегда, у остальных ролей — если для пользователя явно не назначено ни одного объекта
    (`user_object_access` пуст). Это сознательное упрощение MVP: включённое по умолчанию
    ограничение сломало бы демонстрацию для пользователей, которым ещё не настроили доступ,
    а назначение объектов — отдельное административное действие
    (`POST /access/users/{user_id}/objects`), не связанное с ролью самой по себе.
    """
    if user.role == UserRole.admin:
        return None
    ids = set(db.scalars(select(UserObjectAccess.object_id).where(UserObjectAccess.user_id == user.id)))
    return ids or None


def check_object_access(object_id: int | None, user: User, db: Session) -> None:
    accessible = get_accessible_object_ids(user, db)
    if accessible is not None and (object_id is None or object_id not in accessible):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к этому объекту")
